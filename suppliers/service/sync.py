"""
suppliers/service/sync.py

Сервисы синхронизации каталогов поставщиков.
Использует генераторы для потоковой обработки и локальные переменные для безопасности.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Iterator

import httpx

from helpers.arithmetic import round_decimal
from suppliers.models import Supplier, SupplierCatalogSync, SupplierStockHistory
from suppliers.service.base import BaseService
from suppliers.service.dao import SupplierDAO, SupplierStockHistoryDAO, SupplierStockRecordDAO
from core.dao import CurrencyDAO
from catalogue.dao import ProductDAO
from suppliers.service.dto import SupplierProductDTO, SyncResultDTO

logger = logging.getLogger(__name__)


class BaseSupplierSyncService(BaseService[SupplierProductDTO, SyncResultDTO]):
    def process_item(self, item: SupplierProductDTO) -> SyncResultDTO:
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
            supplier=self.supplier, product=product,
            defaults={"supplier_sku": item.supplier_sku, "price": price,
                      "currency": currency, "num_in_stock": item.num_in_stock, "is_active": True},
        )

        if created:
            result.created = True
            result.price_after = price
            result.stock_after = item.num_in_stock
            SupplierStockHistoryDAO.create(
                stock_record=stock_record, sync=self.sync_record,
                snapshot_supplier_name=self.supplier.name, snapshot_product_title=product.title,
                snapshot_product_upc=product.upc or "", snapshot_supplier_sku=item.supplier_sku,
                snapshot_currency_code=currency.currency_code, price_before=None,
                price_after=price, num_in_stock_before=None, num_in_stock_after=item.num_in_stock,
                change_type=SupplierStockHistory.ChangeType.CREATED,
            )
        else:
            price_changed = stock_record.price != price
            stock_changed = stock_record.num_in_stock != item.num_in_stock

            if price_changed or stock_changed:
                SupplierStockRecordDAO.update(stock_record, price, item.supplier_sku, item.num_in_stock, currency)
                result.updated = True
                result.price_changed = price_changed
                result.stock_changed = stock_changed
                result.price_before = stock_record.price
                result.price_after = price
                result.stock_before = stock_record.num_in_stock
                result.stock_after = item.num_in_stock

                SupplierStockHistoryDAO.create(
                    stock_record=stock_record, sync=self.sync_record,
                    snapshot_supplier_name=self.supplier.name, snapshot_product_title=product.title,
                    snapshot_product_upc=product.upc or "", snapshot_supplier_sku=item.supplier_sku,
                    snapshot_currency_code=currency.currency_code,
                    price_before=result.price_before, price_after=price,
                    num_in_stock_before=result.stock_before, num_in_stock_after=item.num_in_stock,
                    change_type=self._determine_change_type(price_changed, stock_changed),
                )
            else:
                result.skipped = True
        return result

    def _determine_change_type(self, pc: bool, sc: bool) -> str:
        if pc and sc: return SupplierStockHistory.ChangeType.BOTH_CHANGED
        if pc: return SupplierStockHistory.ChangeType.PRICE_CHANGED
        return SupplierStockHistory.ChangeType.STOCK_CHANGED


class APISupplierSyncService(BaseSupplierSyncService):
    def fetch_data(self) -> Iterator[SupplierProductDTO]:
        if not self.supplier.api_url:
            raise ValueError(f"API URL не настроен для поставщика {self.supplier.name}")

        credential = SupplierDAO.get_credential(self.supplier)
        headers: dict[str, str] = {}
        if credential:
            if credential.api_key: headers["Authorization"] = f"Bearer {credential.api_key}"
            if credential.extra: headers.update(credential.extra.get("headers", {}))
        if self.supplier.api_extra_config.get("headers"):
            headers.update(self.supplier.api_extra_config["headers"])

        timeout = int(self.supplier.api_extra_config.get("timeout", 30))
        pagination = self.supplier.api_extra_config.get("pagination", {})
        page_param = pagination.get("page_param", "page")
        page_size = pagination.get("page_size", 100)
        
        # ✅ Локальная переменная вместо мутации self.supplier.api_url
        current_url = self.supplier.api_url
        current_page = pagination.get("start_page", 1)

        with httpx.Client(timeout=timeout) as client:
            while True:
                params = {page_param: current_page, "limit": page_size}
                response = client.get(current_url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

                yield from self._parse_api_response(data)

                next_page = data.get("next_page", data.get("next"))
                if not next_page: break
                if isinstance(next_page, str) and next_page.startswith("http"):
                    current_url = next_page
                    page_param = None
                else:
                    current_page += 1

    def _parse_api_response(self,  dict[str, Any]) -> Iterator[SupplierProductDTO]:
        items = data.get("items", data.get("products", []))
        mapping = self.supplier.api_extra_config.get("field_mapping", {})
        for item in items:
            yield SupplierProductDTO(
                supplier_sku=str(item.get(mapping.get("sku", "sku"), "")),
                price=Decimal(str(item.get(mapping.get("price", "price"), "0"))),
                currency_code=item.get(mapping.get("currency", "currency"), self.supplier.default_currency.currency_code),
                num_in_stock=int(item.get(mapping.get("stock", "stock"), 0)),
                product_upc=item.get(mapping.get("upc", "upc")),
                product_title=item.get(mapping.get("title", "title")),
                extra_config=item,
            )


class ManualSupplierSyncService(BaseSupplierSyncService):
    def __init__(self, supplier: Supplier, products_ list[SupplierProductDTO]):
        super().__init__(supplier)
        self.products_data = products_data

    def fetch_data(self) -> Iterator[SupplierProductDTO]:
        yield from self.products_data


def get_sync_service(supplier: Supplier, products_ list[SupplierProductDTO] | None = None) -> BaseSupplierSyncService:
    if supplier.sync_method == Supplier.SyncMethod.API: return APISupplierSyncService(supplier)
    if supplier.sync_method == Supplier.SyncMethod.MANUAL:
        if products_data is None: raise ValueError("Для ручной синхронизации необходимо передать products_data")
        return ManualSupplierSyncService(supplier, products_data)
    raise NotImplementedError(f"Метод синхронизации {supplier.sync_method} ещё не реализован")


def sync_supplier(supplier_id: int, triggered_by: str = "celery") -> SupplierCatalogSync:
    supplier = SupplierDAO.get_by_id(supplier_id)
    if not supplier: raise ValueError(f"Поставщик с ID {supplier_id} не найден")
    if not supplier.supplier_is_active: raise ValueError(f"Поставщик {supplier.name} отключён")
    return get_sync_service(supplier).sync(triggered_by=triggered_by)


def sync_all_active_suppliers(triggered_by: str = "celery") -> list[SupplierCatalogSync]:
    results = []
    for supplier in SupplierDAO.get_active_suppliers():
        try: results.append(sync_supplier(supplier.id, triggered_by))
        except Exception as e: logger.error("Ошибка синхронизации %s: %s", supplier.name, e)
    return results
