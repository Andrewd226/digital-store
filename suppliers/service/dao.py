"""
suppliers/service/dao.py

Data Access Object (DAO) для работы с базой данных.
Все операции с БД должны выполняться через этот слой.
"""

import logging
from typing import List, Optional, Tuple

from django.db import transaction
from django.db.models import QuerySet
from decimal import Decimal

from suppliers.models import (
    Supplier,
    SupplierCredential,
    SupplierCatalogSync,
    SupplierStockRecord,
    SupplierStockHistory,
)
from suppliers.service.dto import SupplierProductDTO

logger = logging.getLogger(__name__)


# ─── Supplier DAO ─────────────────────────────────────────────────────────────


class SupplierDAO:
    """
    DAO для операций с поставщиками.
    """

    @staticmethod
    def get_by_id(supplier_id: int) -> Optional[Supplier]:
        """Получает поставщика по ID."""
        try:
            return Supplier.objects.get(id=supplier_id)
        except Supplier.DoesNotExist:
            return None

    @staticmethod
    def get_by_code(code: str) -> Optional[Supplier]:
        """Получает поставщика по коду."""
        try:
            return Supplier.objects.get(code=code)
        except Supplier.DoesNotExist:
            return None

    @staticmethod
    def get_active_suppliers() -> QuerySet[Supplier]:
        """Возвращает queryset активных поставщиков."""
        return Supplier.objects.filter(supplier_is_active=True)

    @staticmethod
    def get_active_by_sync_method(sync_method: str) -> QuerySet[Supplier]:
        """Возвращает активных поставщиков по методу синхронизации."""
        return Supplier.objects.filter(
            supplier_is_active=True,
            sync_method=sync_method,
        )

    @staticmethod
    def get_credential(supplier: Supplier) -> Optional[SupplierCredential]:
        """Получает учётные данные поставщика."""
        try:
            return SupplierCredential.objects.get(supplier=supplier)
        except SupplierCredential.DoesNotExist:
            return None


# ─── SupplierStockRecord DAO ──────────────────────────────────────────────────


class SupplierStockRecordDAO:
    """
    DAO для операций с записями остатков поставщиков.
    """

    @staticmethod
    def get_by_supplier_product(
        supplier: Supplier,
        product: "Product"
    ) -> Optional[SupplierStockRecord]:
        """Получает запись остатка по поставщику и товару."""
        try:
            return SupplierStockRecord.objects.get(
                supplier=supplier,
                product=product,
            )
        except SupplierStockRecord.DoesNotExist:
            return None

    @staticmethod
    def get_or_create(
        supplier: Supplier,
        product: "Product",
        defaults: dict
    ) -> Tuple[SupplierStockRecord, bool]:
        """
        Находит или создаёт запись остатка.
        
        Returns:
            (record, created) — запись и флаг создания
        """
        return SupplierStockRecord.objects.get_or_create(
            supplier=supplier,
            product=product,
            defaults=defaults,
        )

    @staticmethod
    def update(
        stock_record: SupplierStockRecord,
        price: Decimal,
        supplier_sku: str,
        num_in_stock: int,
        currency: "Currency",
    ) -> SupplierStockRecord:
        """
        Обновляет запись остатка.
        
        Returns:
            Обновлённая запись
        """
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
        return stock_record

    @staticmethod
    def get_active_by_supplier(supplier: Supplier) -> QuerySet[SupplierStockRecord]:
        """Возвращает активные записи остатков поставщика."""
        return SupplierStockRecord.objects.filter(
            supplier=supplier,
            is_active=True,
        )

    @staticmethod
    def get_by_supplier_sku(
        supplier: Supplier,
        supplier_sku: str
    ) -> Optional[SupplierStockRecord]:
        """Получает запись по артикулу поставщика."""
        try:
            return SupplierStockRecord.objects.get(
                supplier=supplier,
                supplier_sku=supplier_sku,
            )
        except SupplierStockRecord.DoesNotExist:
            return None

    @staticmethod
    def deactivate_missing(
        supplier: Supplier,
        active_skus: List[str]
    ) -> int:
        """
        Деактивирует записи, отсутствующие в списке активных SKU.
        
        Returns:
            Количество деактивированных записей
        """
        deactivated = SupplierStockRecord.objects.filter(
            supplier=supplier,
            is_active=True,
        ).exclude(
            supplier_sku__in=active_skus
        ).update(is_active=False)
        
        logger.info(f"Деактивировано {deactivated} записей остатков для {supplier.name}")
        return deactivated


# ─── SupplierStockHistory DAO ─────────────────────────────────────────────────


class SupplierStockHistoryDAO:
    """
    DAO для операций с историей изменений остатков.
    """

    @staticmethod
    def create(
        stock_record: SupplierStockRecord,
        sync: Optional[SupplierCatalogSync],
        snapshot_supplier_name: str,
        snapshot_product_title: str,
        snapshot_product_upc: str,
        snapshot_supplier_sku: str,
        snapshot_currency_code: str,
        price_before: Optional[Decimal],
        price_after: Decimal,
        num_in_stock_before: Optional[int],
        num_in_stock_after: int,
        change_type: str,
    ) -> SupplierStockHistory:
        """
        Создаёт запись в истории изменений.
        
        Returns:
            Созданная запись истории
        """
        return SupplierStockHistory.objects.create(
            stock_record=stock_record,
            sync=sync,
            snapshot_supplier_name=snapshot_supplier_name,
            snapshot_product_title=snapshot_product_title,
            snapshot_product_upc=snapshot_product_upc,
            snapshot_supplier_sku=snapshot_supplier_sku,
            snapshot_currency_code=snapshot_currency_code,
            price_before=price_before,
            price_after=price_after,
            num_in_stock_before=num_in_stock_before,
            num_in_stock_after=num_in_stock_after,
            change_type=change_type,
        )

    @staticmethod
    def get_by_stock_record(
        stock_record: SupplierStockRecord,
        limit: Optional[int] = None
    ) -> QuerySet[SupplierStockHistory]:
        """Возвращает историю по записи остатка."""
        qs = SupplierStockHistory.objects.filter(
            stock_record=stock_record
        ).order_by("-recorded_at")
        
        if limit:
            qs = qs[:limit]
        
        return qs

    @staticmethod
    def get_by_supplier(
        supplier: Supplier,
        limit: Optional[int] = None
    ) -> QuerySet[SupplierStockHistory]:
        """Возвращает историю по поставщику."""
        qs = SupplierStockHistory.objects.filter(
            stock_record__supplier=supplier
        ).order_by("-recorded_at")
        
        if limit:
            qs = qs[:limit]
        
        return qs


# ─── SupplierCatalogSync DAO ──────────────────────────────────────────────────


class SupplierCatalogSyncDAO:
    """
    DAO для операций с записями синхронизации.
    """

    @staticmethod
    def create_running(
        supplier: Supplier,
        triggered_by: str = "celery"
    ) -> SupplierCatalogSync:
        """
        Создаёт запись о начале синхронизации.
        
        Returns:
            Созданная запись синхронизации
        """
        from django.utils import timezone
        
        return SupplierCatalogSync.objects.create(
            supplier=supplier,
            status=SupplierCatalogSync.Status.RUNNING,
            triggered_by=triggered_by,
            started_at=timezone.now(),
        )

    @staticmethod
    def complete(
        sync_record: SupplierCatalogSync,
        status: str,
        total_items: int,
        created_items: int,
        updated_items: int,
        skipped_items: int,
        failed_items: int,
        error_log: str = "",
    ) -> SupplierCatalogSync:
        """
        Завершает синхронизацию.
        
        Returns:
            Обновлённая запись синхронизации
        """
        from django.utils import timezone
        
        sync_record.status = status
        sync_record.finished_at = timezone.now()
        sync_record.total_items = total_items
        sync_record.created_items = created_items
        sync_record.updated_items = updated_items
        sync_record.skipped_items = skipped_items
        sync_record.failed_items = failed_items
        sync_record.error_log = error_log[:65535] if error_log else ""
        sync_record.save(update_fields=[
            "status",
            "finished_at",
            "total_items",
            "created_items",
            "updated_items",
            "skipped_items",
            "failed_items",
            "error_log",
        ])
        return sync_record

    @staticmethod
    def get_by_supplier(
        supplier: Supplier,
        limit: Optional[int] = None
    ) -> QuerySet[SupplierCatalogSync]:
        """Возвращает записи синхронизации по поставщику."""
        qs = SupplierCatalogSync.objects.filter(
            supplier=supplier
        ).order_by("-started_at")
        
        if limit:
            qs = qs[:limit]
        
        return qs

    @staticmethod
    def get_last_sync(supplier: Supplier) -> Optional[SupplierCatalogSync]:
        """Возвращает последнюю синхронизацию поставщика."""
        return SupplierCatalogSyncDAO.get_by_supplier(supplier, limit=1).first()


# ─── Product DAO (для внешних зависимостей) ───────────────────────────────────


class ProductDAO:
    """
    DAO для операций с товарами (внешняя зависимость).
    """

    @staticmethod
    def get_by_upc(upc: str) -> Optional["Product"]:
        """Получает товар по UPC."""
        from catalogue.models import Product
        
        try:
            return Product.objects.get(upc=upc)
        except Product.DoesNotExist:
            return None

    @staticmethod
    def get_by_upc_list(upc_list: List[str]) -> QuerySet["Product"]:
        """Возвращает товары по списку UPC."""
        from catalogue.models import Product
        
        return Product.objects.filter(upc__in=upc_list)


# ─── Currency DAO (для внешних зависимостей) ──────────────────────────────────


class CurrencyDAO:
    """
    DAO для операций с валютами (внешняя зависимость).
    """

    @staticmethod
    def get_by_code(currency_code: str) -> Optional["Currency"]:
        """Получает валюту по коду."""
        from core.models import Currency
        
        try:
            return Currency.objects.get(currency_code=currency_code)
        except Currency.DoesNotExist:
            return None

    @staticmethod
    def get_active() -> QuerySet["Currency"]:
        """Возвращает все активные валюты."""
        from core.models import Currency
        
        return Currency.objects.all()