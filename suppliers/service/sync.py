"""
suppliers/service/sync.py

Сервисы синхронизации каталогов поставщиков.
"""

import logging
from decimal import Decimal
from typing import Any

import httpx

from helpers.arithmetic import round_decimal
from suppliers.models import (
    Supplier,
    SupplierCatalogSync,
    SupplierStockHistory,
)
from suppliers.service.base import BaseService
from suppliers.service.dao import (
    CurrencyDAO,
    ProductDAO,
    SupplierDAO,
    SupplierStockHistoryDAO,
    SupplierStockRecordDAO,
)
from suppliers.service.dto import SupplierProductDTO, SyncResultDTO

logger = logging.getLogger(__name__)


# ─── Base Sync Service ────────────────────────────────────────────────────────


class BaseSupplierSyncService(BaseService[SupplierProductDTO, SyncResultDTO]):
    """
    Базовый сервис синхронизации поставщиков.
    Реализует общую логику обработки товаров.
    """

    def process_item(self, item: SupplierProductDTO) -> SyncResultDTO:
        """
        Обрабатывает один товар: создаёт или обновляет запись, ведёт историю.
        """
        result = SyncResultDTO(supplier_sku=item.supplier_sku)

        currency = CurrencyDAO.get_by_code(item.currency_code)
        if currency is None:
            result.failed = True
            result.error_message = f"Валюта не найдена: {item.currency_code}"
            return result

        product = ProductDAO.get_by_upc(item.product_upc)
        if product is None:
            result.skipped = True
            return result

        price = round_decimal(item.price, 25)

        stock_record, created = SupplierStockRecordDAO.get_or_create(
            supplier=self.supplier,
            product=product,
            defaults={
                "supplier_sku": item.supplier_sku,
                "price": price,
                "currency": currency,
                "num_in_stock": item.num_in_stock,
                "is_active": True,
            },
        )

        if created:
            result.created = True
            result.price_after = price
            result.stock_after = item.num_in_stock
            SupplierStockHistoryDAO.create(
                stock_record=stock_record,
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
        else:
            price_changed = stock_record.price != price
            stock_changed = stock_record.num_in_stock != item.num_in_stock

            if price_changed or stock_changed:
                price_before = stock_record.price
                stock_before = stock_record.num_in_stock

                SupplierStockRecordDAO.update(
                    stock_record=stock_record,
                    price=price,
                    supplier_sku=item.supplier_sku,
                    num_in_stock=item.num_in_stock,
                    currency=currency,
                )

                result.updated = True
                result.price_changed = price_changed
                result.stock_changed = stock_changed
                result.price_before = price_before
                result.price_after = price
                result.stock_before = stock_before
                result.stock_after = item.num_in_stock

                SupplierStockHistoryDAO.create(
                    stock_record=stock_record,
                    sync=self.sync_record,
                    snapshot_supplier_name=self.supplier.name,
                    snapshot_product_title=product.title,
                    snapshot_product_upc=product.upc or "",
                    snapshot_supplier_sku=item.supplier_sku,
                    snapshot_currency_code=currency.currency_code,
                    price_before=price_before,
                    price_after=price,
                    num_in_stock_before=stock_before,
                    num_in_stock_after=item.num_in_stock,
                    change_type=self._determine_change_type(price_changed, stock_changed),
                )
            else:
                result.skipped = True

        return result

    def _determine_change_type(self, price_changed: bool, stock_changed: bool) -> str:
        """Определяет тип изменения для истории."""
        if price_changed and stock_changed:
            return SupplierStockHistory.ChangeType.BOTH_CHANGED
        elif price_changed:
            return SupplierStockHistory.ChangeType.PRICE_CHANGED
        else:
            return SupplierStockHistory.ChangeType.STOCK_CHANGED


# ─── API Sync Service ─────────────────────────────────────────────────────────


class APISupplierSyncService(BaseSupplierSyncService):
    """
    Сервис синхронизации через REST API.
    """

    def fetch_data(self) -> list[SupplierProductDTO]:
        """Загружает данные через HTTP API."""
        if not self.supplier.api_url:
            raise ValueError(f"API URL не настроен для поставщика {self.supplier.name}")

        credential = SupplierDAO.get_credential(self.supplier)
        headers: dict[str, str] = {}

        if credential:
            if credential.api_key:
                headers["Authorization"] = f"Bearer {credential.api_key}"
            if credential.extra:
                headers.update(credential.extra.get("headers", {}))

        if self.supplier.api_extra_config.get("headers"):
            headers.update(self.supplier.api_extra_config["headers"])

        timeout = self.supplier.api_extra_config.get("timeout", 30)

        with httpx.Client(timeout=timeout) as client:
            response = client.get(self.supplier.api_url, headers=headers)
            response.raise_for_status()
            data = response.json()

        return self._parse_api_response(data)

    def _parse_api_response(self, data: dict[str, Any]) -> list[SupplierProductDTO]:
        """Парсит ответ API в список DTO."""
        products = []
        items = data.get("items", data.get("products", []))
        field_mapping = self.supplier.api_extra_config.get("field_mapping", {})

        for item in items:
            products.append(
                SupplierProductDTO(
                    supplier_sku=str(item.get(field_mapping.get("sku", "sku"), "")),
                    price=Decimal(str(item.get(field_mapping.get("price", "price"), "0"))),
                    currency_code=item.get(
                        field_mapping.get("currency", "currency"),
                        self.supplier.default_currency.currency_code,
                    ),
                    num_in_stock=int(item.get(field_mapping.get("stock", "stock"), 0)),
                    product_upc=item.get(field_mapping.get("upc", "upc")),
                    product_title=item.get(field_mapping.get("title", "title")),
                    extra_data=item,
                )
            )

        return products


# ─── Manual Sync Service ──────────────────────────────────────────────────────


class ManualSupplierSyncService(BaseSupplierSyncService):
    """
    Сервис ручной синхронизации.
    Данные передаются напрямую в конструктор.
    """

    def __init__(self, supplier: Supplier, products_data: list[SupplierProductDTO]):
        super().__init__(supplier)
        self.products_data = products_data

    def fetch_data(self) -> list[SupplierProductDTO]:
        """Возвращает заранее подготовленные данные."""
        return self.products_data


# ─── Factory ──────────────────────────────────────────────────────────────────


def get_sync_service(
    supplier: Supplier,
    products_data: list[SupplierProductDTO] | None = None,
) -> BaseSupplierSyncService:
    """
    Фабричный метод для создания сервиса синхронизации.
    """
    if supplier.sync_method == Supplier.SyncMethod.API:
        return APISupplierSyncService(supplier)
    elif supplier.sync_method == Supplier.SyncMethod.MANUAL:
        if products_data is None:
            raise ValueError("Для ручной синхронизации необходимо передать products_data")
        return ManualSupplierSyncService(supplier, products_data)
    else:
        raise NotImplementedError(
            f"Метод синхронизации {supplier.sync_method} ещё не реализован"
        )


# ─── Helper Functions ─────────────────────────────────────────────────────────


def sync_supplier(supplier_id: int, triggered_by: str = "celery") -> SupplierCatalogSync:
    """Утилита для запуска синхронизации поставщика по ID."""
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
