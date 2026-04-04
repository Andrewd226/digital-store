"""
suppliers/service/sync.py

Сервисы синхронизации каталогов поставщиков.
Реализует потоковую обработку, кеширование справочников и пакетную запись.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Iterator

from django.utils import timezone
from httpx import Client

from helpers.arithmetic import round_decimal
from catalogue.dao import ProductDAO
from core.dao import CurrencyDAO
from suppliers.models import (
    Supplier,
    SupplierCatalogSync,
    SupplierStockHistory,
    SupplierStockRecord,
)
from suppliers.service.base import BaseService
from suppliers.service.dao import (
    SupplierCatalogSyncDAO,
    SupplierDAO,
    SupplierStockHistoryDAO,
    SupplierStockRecordDAO,
)
from suppliers.service.dto import SupplierProductDTO, SyncResultDTO

logger = logging.getLogger(__name__)


class BaseSupplierSyncService(BaseService[SupplierProductDTO, SyncResultDTO]):
    """Базовый сервис синхронизации с оптимизацией N+1 и защитой от устаревших данных."""

    def __init__(self, supplier: Supplier):
        super().__init__(supplier)
        self._currency_cache: dict[str, Any] = {}
        self._product_cache: dict[str | None, Any] = {}
        self._buffer_records_to_update: list[Any] = []
        self._buffer_records_to_create: list[Any] = []
        self._buffer_history_to_create: list[SupplierStockHistory] = []

    def _flush_buffers(self) -> None:
        """Пакетная запись накопленных изменений в БД."""
        if self._buffer_records_to_create:
            SupplierStockRecord.objects.bulk_create(self._buffer_records_to_create)
            self._buffer_records_to_create.clear()
            
        if self._buffer_records_to_update:
            SupplierStockRecordDAO.bulk_update_records(
                self._buffer_records_to_update,
                ["price", "supplier_sku", "num_in_stock", "currency", "is_active", "last_supplier_updated_at"],
            )
            self._buffer_records_to_update.clear()

        if self._buffer_history_to_create:
            SupplierStockHistoryDAO.bulk_create_history(self._buffer_history_to_create)
            self._buffer_history_to_create.clear()

    def _get_currency(self, code: str):
        if code not in self._currency_cache:
            self._currency_cache[code] = CurrencyDAO.get_by_code(code)
        return self._currency_cache[code]

    def _get_product(self, upc: str | None):
        if upc not in self._product_cache:
            self._product_cache[upc] = ProductDAO.get_by_upc(upc)
        return self._product_cache[upc]

    def process_item(self, item: SupplierProductDTO) -> SyncResultDTO:
        result = SyncResultDTO(supplier_sku=item.supplier_sku)

        currency = self._get_currency(item.currency_code)
        if currency is None:
            result.failed = True
            result.error_message = f"Валюта не найдена: {item.currency_code}"
            return result

        product = self._get_product(item.product_upc)
        if product is None:
            result.skipped = True
            result.skipped_reason = "product_not_found"
            return result

        price = round_decimal(item.price, 25)
        stock_record = SupplierStockRecordDAO.get_by_supplier_product(self.supplier, product)

        # Пункт 2: Защита от перезаписи новых данных старыми
        if stock_record and stock_record.last_supplier_updated_at and item.source_updated_at:
            if item.source_updated_at <= stock_record.last_supplier_updated_at:
                result.skipped = True
                result.skipped_reason = "stale_data"
                return result

        if stock_record:
            # Пункт 3: Сохраняем СТАРЫЕ значения ДО мутации объекта!
            price_before = stock_record.price
            stock_before = stock_record.num_in_stock
            
            price_changed = stock_record.price != price
            stock_changed = stock_record.num_in_stock != item.num_in_stock

            if price_changed or stock_changed:
                # Обновляем объект в памяти
                stock_record.price = price
                stock_record.supplier_sku = item.supplier_sku
                stock_record.num_in_stock = item.num_in_stock
                stock_record.currency = currency
                stock_record.is_active = True
                stock_record.last_supplier_updated_at = item.source_updated_at or timezone.now()
                self._buffer_records_to_update.append(stock_record)

                # ✅ Добавляем историю с корректными price_before/after
                self._buffer_history_to_create.append(
                    SupplierStockHistory(
                        stock_record=stock_record,
                        sync=self.sync_record,
                        snapshot_supplier_name=self.supplier.name,
                        snapshot_product_title=product.title,
                        snapshot_product_upc=product.upc or "",
                        snapshot_supplier_sku=item.supplier_sku,
                        snapshot_currency_code=currency.currency_code,
                        price_before=price_before,  # ✅ Старая цена (сохранена до мутации)
                        price_after=price,          # ✅ Новая цена
                        num_in_stock_before=stock_before,
                        num_in_stock_after=item.num_in_stock,
                        change_type=self._determine_change_type(price_changed, stock_changed),
                    )
                )

                result.updated = True
                result.price_changed = price_changed
                result.stock_changed = stock_changed
                result.price_before = price_before
                result.price_after = price
            else:
                result.skipped = True
        else:
            # Создание новой записи
            now = timezone.now()
            new_record = SupplierStockRecord(
                supplier=self.supplier,
                product=product,
                supplier_sku=item.supplier_sku,
                price=price,
                currency=currency,
                num_in_stock=item.num_in_stock,
                is_active=True,
                last_supplier_updated_at=item.source_updated_at or now,
                created_at=now,
                updated_at=now,
            )
            self._buffer_records_to_create.append(new_record)
            
            self._buffer_history_to_create.append(
                SupplierStockHistory(
                    stock_record=new_record,
                    sync=self.sync_record,
                    snapshot_supplier_name=self.supplier.name,
                    snapshot_product_title=product.title,
                    snapshot_product_upc=product.upc or "",
                    snapshot_supplier_sku=item.supplier_sku,
                    snapshot_currency_code=currency.currency_code,
                    price_before=None,
                    price_after=price,
                    num_in_stock_before=None,
                    num_in_stock_after=item.num_in_stock,
                    change_type=SupplierStockHistory.ChangeType.CREATED,
                )
            )
            result.created = True

        # Периодический сброс буферов
        if len(self._buffer_history_to_create) >= 500:
            self._flush_buffers()

        return result

    def _determine_change_type(self, pc: bool, sc: bool) -> str:
        if pc and sc:
            return SupplierStockHistory.ChangeType.BOTH_CHANGED
        if pc:
            return SupplierStockHistory.ChangeType.PRICE_CHANGED
        return SupplierStockHistory.ChangeType.STOCK_CHANGED

    def sync(self, triggered_by: str = "celery") -> SupplierCatalogSync:
        # ✅ Пункт 3: Очистка зависших задач перед запуском новой
        SupplierCatalogSyncDAO.recover_stale_syncs()

        try:
            self.start_sync(triggered_by=triggered_by)
            items_iter = self.fetch_data()

            for item in items_iter:
                try:
                    result = self.process_item(item)
                    self._update_stats(result)

                    if result.failed and result.error_message:
                        error_msg = f"{item.supplier_sku}: {result.error_message}"
                        self.errors.append(error_msg)
                        logger.error("Ошибка обработки элемента: %s", error_msg)
                except Exception as e:
                    self.stats.failed += 1
                    error_msg = f"{getattr(item, 'supplier_sku', 'unknown')}: {e}"
                    self.errors.append(error_msg)
                    logger.error("Исключение при обработке элемента: %s", error_msg)

            # Финальный сброс остатков в буфере
            self._flush_buffers()
            self.complete_sync(error_log="\n".join(self.errors[:1000]))
        except Exception as e:
            logger.exception("Критическая ошибка синхронизации: %s", e)
            self.complete_sync(status=SupplierCatalogSync.Status.FAILED, error_log=f"CRITICAL: {e}")
            raise
        return self.sync_record


class APISupplierSyncService(BaseSupplierSyncService):
    def fetch_data(self) -> Iterator[SupplierProductDTO]:
        if not self.supplier.api_url:
            raise ValueError(f"API URL не настроен для поставщика {self.supplier.name}")

        credential = SupplierDAO.get_credential(self.supplier)
        headers: dict[str, str] = {}
        if credential and credential.api_key:
            headers["Authorization"] = f"Bearer {credential.api_key}"

        timeout = int(self.supplier.api_extra_config.get("timeout", 30))
        current_url = self.supplier.api_url

        with Client(timeout=timeout) as client:
            page = 1
            while True:
                resp = client.get(current_url, headers=headers, params={"page": page, "limit": 200})
                resp.raise_for_status()
                data = resp.json()
                
                yield from self._parse_api_response(data)
                
                if not data.get("next"):
                    break
                current_url = data.get("next")
                page += 1

    def _parse_api_response(self, raw: dict[str, Any]) -> Iterator[SupplierProductDTO]:
        for item in raw.get("items", []):
            yield SupplierProductDTO(
                supplier_sku=str(item.get("sku")),
                price=Decimal(str(item.get("price", 0))),
                currency_code=item.get("currency", self.supplier.default_currency.currency_code),
                num_in_stock=int(item.get("stock", 0)),
                product_upc=item.get("upc"),
                product_title=item.get("title"),
                config=item,
                source_updated_at=item.get("updated_at"),
            )


class ManualSupplierSyncService(BaseSupplierSyncService):
    """Сервис ручной синхронизации."""
    def __init__(self, supplier: Supplier, products_ list[SupplierProductDTO]):
        super().__init__(supplier)
        self.products_data = products_data

    def fetch_data(self) -> Iterator[SupplierProductDTO]:
        yield from self.products_data


def get_sync_service(
    supplier: Supplier,
    products_ list[SupplierProductDTO] | None = None,
) -> BaseSupplierSyncService:
    """Фабричный метод для выбора стратегии синхронизации."""
    if supplier.sync_method == Supplier.SyncMethod.API:
        return APISupplierSyncService(supplier)
    if supplier.sync_method == Supplier.SyncMethod.MANUAL:
        if products_data is None:
            raise ValueError("Для ручной синхронизации необходимо передать products_data")
        return ManualSupplierSyncService(supplier, products_data)
    raise NotImplementedError(f"Метод синхронизации {supplier.sync_method} ещё не реализован")


def sync_supplier(supplier_id: int, triggered_by: str = "celery") -> SupplierCatalogSync:
    """Утилита для запуска синхронизации одного поставщика по ID."""
    supplier = SupplierDAO.get_by_id(supplier_id)
    if supplier is None:
        raise ValueError(f"Поставщик с ID {supplier_id} не найден")
    if not supplier.supplier_is_active:
        raise ValueError(f"Поставщик {supplier.name} отключён")
    service = get_sync_service(supplier)
    return service.sync(triggered_by=triggered_by)


def sync_all_active_suppliers(triggered_by: str = "celery") -> list[SupplierCatalogSync]:
    """Запускает синхронизацию всех активных поставщиков."""
    suppliers = SupplierDAO.get_active_suppliers()
    results = []
    for supplier in suppliers:
        try:
            sync_record = sync_supplier(supplier.id, triggered_by=triggered_by)
            results.append(sync_record)
        except Exception as e:
            logger.error("Ошибка синхронизации %s: %s", supplier.name, e)
    return results
