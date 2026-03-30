"""
suppliers/services/sync.py

Сервисы синхронизации каталогов поставщиков.
"""

import logging
from typing import Any, Dict, List, Optional

from django.db import transaction
from decimal import Decimal

from helpers.arithmetic import round_decimal
from suppliers.dto import SupplierProductDTO, SyncResultDTO
from suppliers.services.base import BaseService
from suppliers.models import (
    Supplier,
    SupplierStockRecord,
    SupplierStockHistory,
    SupplierCatalogSync,
)

logger = logging.getLogger(__name__)


# ─── Base Sync Service ────────────────────────────────────────────────────────


class BaseSupplierSyncService(BaseService[SupplierProductDTO, SyncResultDTO]):
    """
    Базовый сервис синхронизации поставщиков.
    Реализует общую логику обработки товаров.
    """

    def process_item(self,  SupplierProductDTO) -> SyncResultDTO:
        """
        Обрабатывает один товар: создаёт или обновляет запись, ведёт историю.
        """
        from core.models import Currency
        from catalogue.models import Product

        result = SyncResultDTO(supplier_sku=product_data.supplier_sku)

        # Получаем валюту
        currency = self._get_currency(product_data.currency_code)
        if currency is None:
            result.failed = True
            result.error_message = f"Валюта не найдена: {product_data.currency_code}"
            return result

        # Находим товар по UPC
        product = self._get_product(product_data.product_upc)
        if product is None:
            result.skipped = True
            return result

        # Округляем цену
        price = round_decimal(product_data.price, 25)

        # Находим или создаём запись остатка
        stock_record, created = self._get_or_create_stock_record(
            product=product,
            supplier_sku=product_data.supplier_sku,
            price=price,
            currency=currency,
            num_in_stock=product_data.num_in_stock,
        )

        if created:
            result.created = True
            result.price_after = price
            result.stock_after = product_data.num_in_stock
            self._create_history_record(
                stock_record=stock_record,
                change_type=SupplierStockHistory.ChangeType.CREATED,
                price_before=None,
                price_after=price,
                stock_before=None,
                stock_after=product_data.num_in_stock,
            )
        else:
            # Проверяем изменения
            price_changed = stock_record.price != price
            stock_changed = stock_record.num_in_stock != product_data.num_in_stock

            if price_changed or stock_changed:
                price_before = stock_record.price
                stock_before = stock_record.num_in_stock

                self._update_stock_record(
                    stock_record=stock_record,
                    price=price,
                    supplier_sku=product_data.supplier_sku,
                    num_in_stock=product_data.num_in_stock,
                    currency=currency,
                )

                result.updated = True
                result.price_changed = price_changed
                result.stock_changed = stock_changed
                result.price_before = price_before
                result.price_after = price
                result.stock_before = stock_before
                result.stock_after = product_data.num_in_stock

                change_type = self._determine_change_type(price_changed, stock_changed)

                self._create_history_record(
                    stock_record=stock_record,
                    change_type=change_type,
                    price_before=price_before,
                    price_after=price,
                    stock_before=stock_before,
                    stock_after=product_data.num_in_stock,
                )
            else:
                result.skipped = True

        return result

    def _get_currency(self, currency_code: str) -> Optional[Currency]:
        """Получает валюту по коду."""
        try:
            return Currency.objects.get(currency_code=currency_code)
        except Currency.DoesNotExist:
            logger.warning(f"Валюта не найдена: {currency_code}")
            return None

    def _get_product(self, upc: Optional[str]) -> Optional[Product]:
        """Получает товар по UPC."""
        if not upc:
            return None
        return Product.objects.filter(upc=upc).first()

    def _get_or_create_stock_record(
        self,
        product: Any,
        supplier_sku: str,
        price: Decimal,
        currency: Any,
        num_in_stock: int,
    ):
        """Находит или создаёт запись остатка."""
        return SupplierStockRecord.objects.get_or_create(
            supplier=self.supplier,
            product=product,
            defaults={
                "supplier_sku": supplier_sku,
                "price": price,
                "currency": currency,
                "num_in_stock": num_in_stock,
                "is_active": True,
            },
        )

    def _update_stock_record(
        self,
        stock_record: SupplierStockRecord,
        price: Decimal,
        supplier_sku: str,
        num_in_stock: int,
        currency: Any,
    ) -> None:
        """Обновляет запись остатка."""
        stock_record.price = price
        stock_record.supplier_sku = supplier_sku
        stock_record.num_in_stock = num_in_stock
        stock_record.currency = currency
        stock_record.is_active = True
        stock_record.save(update_fields=[
            "price",
            "supplier_sku",
            "num_in_stock",
            "currency",
            "is_active",
            "updated_at",
        ])

    def _determine_change_type(self, price_changed: bool, stock_changed: bool) -> str:
        """Определяет тип изменения для истории."""
        if price_changed and stock_changed:
            return SupplierStockHistory.ChangeType.BOTH_CHANGED
        elif price_changed:
            return SupplierStockHistory.ChangeType.PRICE_CHANGED
        else:
            return SupplierStockHistory.ChangeType.STOCK_CHANGED

    def _create_history_record(
        self,
        stock_record: SupplierStockRecord,
        change_type: str,
        price_before: Optional[Decimal],
        price_after: Decimal,
        stock_before: Optional[int],
        stock_after: int,
    ) -> SupplierStockHistory:
        """Создаёт запись в истории изменений."""
        return SupplierStockHistory.objects.create(
            stock_record=stock_record,
            sync=self.sync_record,
            snapshot_supplier_name=self.supplier.name,
            snapshot_product_title=stock_record.product.title,
            snapshot_product_upc=stock_record.product.upc or "",
            snapshot_supplier_sku=stock_record.supplier_sku,
            snapshot_currency_code=stock_record.currency.currency_code,
            price_before=price_before,
            price_after=price_after,
            num_in_stock_before=stock_before,
            num_in_stock_after=stock_after,
            change_type=change_type,
        )


# ─── API Sync Service ─────────────────────────────────────────────────────────


class APISupplierSyncService(BaseSupplierSyncService):
    """
    Сервис синхронизации через REST API.
    """

    def fetch_data(self) -> List[SupplierProductDTO]:
        """Загружает данные через HTTP API."""
        import httpx

        if not self.supplier.api_url:
            raise ValueError(f"API URL не настроен для поставщика {self.supplier.name}")

        credential = getattr(self.supplier, "credential", None)
        headers = {}

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

    def _parse_api_response(self,  Dict[str, Any]) -> List[SupplierProductDTO]:
        """Парсит ответ API в список DTO."""
        products = []
        items = data.get("items", data.get("products", []))
        field_mapping = self.supplier.api_extra_config.get("field_mapping", {})

        for item in items:
            products.append(SupplierProductDTO(
                supplier_sku=str(item.get(field_mapping.get("sku", "sku"), "")),
                price=Decimal(str(item.get(field_mapping.get("price", "price"), "0"))),
                currency_code=item.get(
                    field_mapping.get("currency", "currency"),
                    self.supplier.default_currency.currency_code
                ),
                num_in_stock=int(item.get(field_mapping.get("stock", "stock"), 0)),
                product_upc=item.get(field_mapping.get("upc", "upc")),
                product_title=item.get(field_mapping.get("title", "title")),
                extra_data=item,
            ))

        return products


# ─── Manual Sync Service ──────────────────────────────────────────────────────


class ManualSupplierSyncService(BaseSupplierSyncService):
    """
    Сервис ручной синхронизации.
    Данные передаются напрямую в конструктор.
    """

    def __init__(self, supplier: Supplier, products_ List[SupplierProductDTO]):
        super().__init__(supplier)
        self.products_data = products_data

    def fetch_data(self) -> List[SupplierProductDTO]:
        """Возвращает заранее подготовленные данные."""
        return self.products_data


# ─── Factory ──────────────────────────────────────────────────────────────────


def get_sync_service(
    supplier: Supplier,
    products_ Optional[List[SupplierProductDTO]] = None
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
        raise NotImplementedError(f"Метод синхронизации {supplier.sync_method} ещё не реализован")


# ─── Helper Functions ─────────────────────────────────────────────────────────


def sync_supplier(supplier_id: int, triggered_by: str = "celery") -> SupplierCatalogSync:
    """Утилита для запуска синхронизации поставщика по ID."""
    supplier = Supplier.objects.get(id=supplier_id)

    if not supplier.supplier_is_active:
        raise ValueError(f"Поставщик {supplier.name} отключён")

    service = get_sync_service(supplier)
    return service.sync(triggered_by=triggered_by)


def sync_all_active_suppliers(triggered_by: str = "celery") -> List[SupplierCatalogSync]:
    """Запускает синхронизацию всех активных поставщиков."""
    suppliers = Supplier.objects.filter(supplier_is_active=True)
    results = []

    for supplier in suppliers:
        try:
            sync_record = sync_supplier(supplier.id, triggered_by=triggered_by)
            results.append(sync_record)
        except Exception as e:
            logger.error(f"Ошибка синхронизации {supplier.name}: {e}")

    return results
