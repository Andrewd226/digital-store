"""
suppliers/service/dao.py

Data Access Object (DAO) для работы с базой данных модуля поставщиков.
Использует TYPE_CHECKING для безопасных аннотаций внешних моделей.
Все методы статические для упрощения тестирования.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import QuerySet
from django.utils import timezone

from core.dao import CurrencyDAO
from catalogue.dao import ProductDAO

from suppliers.models import (
    Supplier,
    SupplierCatalogSync,
    SupplierCredential,
    SupplierStockHistory,
    SupplierStockRecord,
)

if TYPE_CHECKING:
    from core.models import Currency
    from catalogue.models import Product

logger = logging.getLogger(__name__)


# ─── Supplier DAO ─────────────────────────────────────────────────────────────

class SupplierDAO:
    """DAO для операций с поставщиками."""

    @staticmethod
    def get_by_id(supplier_id: int) -> Supplier | None:
        """Получает поставщика по первичному ключу."""
        try:
            return Supplier.objects.get(id=supplier_id)
        except Supplier.DoesNotExist:
            return None

    @staticmethod
    def get_by_code(code: str) -> Supplier | None:
        """Получает поставщика по уникальному коду (slug)."""
        try:
            return Supplier.objects.get(code=code)
        except Supplier.DoesNotExist:
            return None

    @staticmethod
    def get_active_suppliers() -> QuerySet[Supplier]:
        """Возвращает всех активных поставщиков."""
        return Supplier.objects.filter(supplier_is_active=True)

    @staticmethod
    def get_active_by_sync_method(sync_method: str) -> QuerySet[Supplier]:
        """Возвращает активных поставщиков с конкретным методом синхронизации."""
        return Supplier.objects.filter(
            supplier_is_active=True,
            sync_method=sync_method,
        )

    @staticmethod
    def get_credential(supplier: Supplier) -> SupplierCredential | None:
        """Получает зашифрованные учётные данные поставщика."""
        try:
            return SupplierCredential.objects.get(supplier=supplier)
        except SupplierCredential.DoesNotExist:
            return None


# ─── SupplierStockRecord DAO ──────────────────────────────────────────────────

class SupplierStockRecordDAO:
    """DAO для операций с записями остатков поставщиков."""

    @staticmethod
    def get_by_supplier_product(supplier: Supplier, product: Product) -> SupplierStockRecord | None:
        """Получает запись остатка по связке поставщик-товар."""
        try:
            return SupplierStockRecord.objects.select_related("currency").get(
                supplier=supplier, product=product
            )
        except SupplierStockRecord.DoesNotExist:
            return None

    @staticmethod
    def get_or_create(
        supplier: Supplier, product: Product, defaults: dict
    ) -> tuple[SupplierStockRecord, bool]:
        """Находит существующую запись или создаёт новую."""
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
        currency: Currency,
    ) -> SupplierStockRecord:
        """Обновляет параметры поставки. Активирует запись, если была деактивирована."""
        stock_record.price = price
        stock_record.supplier_sku = supplier_sku
        stock_record.num_in_stock = num_in_stock
        stock_record.currency = currency
        stock_record.is_active = True
        stock_record.save(
            update_fields=[
                "price", "supplier_sku", "num_in_stock",
                "currency", "is_active", "updated_at",
            ]
        )
        return stock_record

    @staticmethod
    def get_active_by_supplier(supplier: Supplier) -> QuerySet[SupplierStockRecord]:
        """Возвращает активные записи остатков конкретного поставщика."""
        return SupplierStockRecord.objects.filter(supplier=supplier, is_active=True)

    @staticmethod
    def get_by_supplier_sku(supplier: Supplier, supplier_sku: str) -> SupplierStockRecord | None:
        """Получает запись по внутреннему артикулу поставщика."""
        try:
            return SupplierStockRecord.objects.get(supplier=supplier, supplier_sku=supplier_sku)
        except SupplierStockRecord.DoesNotExist:
            return None

    @staticmethod
    def deactivate_missing(supplier: Supplier, active_skus: list[str]) -> int:
        """Деактивирует записи, отсутствующие в текущей выгрузке."""
        deactivated = (
            SupplierStockRecord.objects.filter(supplier=supplier, is_active=True)
            .exclude(supplier_sku__in=active_skus)
            .update(is_active=False)
        )
        if deactivated > 0:
            logger.info("Деактивировано %d записей остатков для %s", deactivated, supplier.name)
        return deactivated

    @staticmethod
    def bulk_update_records(records: list[SupplierStockRecord], fields: list[str]) -> None:
        """Пакетное обновление существующих записей."""
        if records:
            SupplierStockRecord.objects.bulk_update(records, fields)


# ─── SupplierStockHistory DAO ─────────────────────────────────────────────────

class SupplierStockHistoryDAO:
    """DAO для операций с историей изменений остатков (append-only)."""

    @staticmethod
    def create(
        stock_record: SupplierStockRecord,
        sync: SupplierCatalogSync | None,
        snapshot_supplier_name: str,
        snapshot_product_title: str,
        snapshot_product_upc: str,
        snapshot_supplier_sku: str,
        snapshot_currency_code: str,
        price_before: Decimal | None,
        price_after: Decimal,
        num_in_stock_before: int | None,
        num_in_stock_after: int,
        change_type: str,
    ) -> SupplierStockHistory:
        """Создаёт снимок изменения в истории."""
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
    def bulk_create_history(history_records: list[SupplierStockHistory]) -> None:
        """Пакетное создание записей истории."""
        if history_records:
            SupplierStockHistory.objects.bulk_create(history_records)

    @staticmethod
    def get_by_stock_record(
        stock_record: SupplierStockRecord, limit: int | None = None
    ) -> QuerySet[SupplierStockHistory]:
        """Возвращает историю изменений конкретной записи (от новых к старым)."""
        qs = SupplierStockHistory.objects.filter(stock_record=stock_record).order_by("-recorded_at")
        return qs[:limit] if limit else qs

    @staticmethod
    def get_by_supplier(
        supplier: Supplier, limit: int | None = None
    ) -> QuerySet[SupplierStockHistory]:
        """Возвращает общую историю изменений для всех товаров поставщика."""
        qs = SupplierStockHistory.objects.filter(stock_record__supplier=supplier).order_by("-recorded_at")
        return qs[:limit] if limit else qs


# ─── SupplierCatalogSync DAO ──────────────────────────────────────────────────

class SupplierCatalogSyncDAO:
    """DAO для управления логами синхронизаций."""

    @staticmethod
    def create_running(supplier: Supplier, triggered_by: str = "celery") -> SupplierCatalogSync:
        """Создаёт запись о начале процесса синхронизации."""
        return SupplierCatalogSync.objects.create(
            supplier=supplier,
            status=SupplierCatalogSync.Status.RUNNING,
            triggered_by=triggered_by,
            # started_at не передаём — поле auto_now_add=True, явное значение игнорируется Django
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
        """Фиксирует завершение синхронизации."""
        sync_record.status = status
        sync_record.finished_at = timezone.now()
        sync_record.total_items = total_items
        sync_record.created_items = created_items
        sync_record.updated_items = updated_items
        sync_record.skipped_items = skipped_items
        sync_record.failed_items = failed_items
        sync_record.error_log = error_log[:65535] if error_log else ""
        sync_record.save(
            update_fields=[
                "status", "finished_at", "total_items", "created_items",
                "updated_items", "skipped_items", "failed_items", "error_log",
            ]
        )
        return sync_record

    @staticmethod
    def get_by_supplier(supplier: Supplier, limit: int | None = None) -> QuerySet[SupplierCatalogSync]:
        """Возвращает историю запусков синхронизации для поставщика."""
        qs = SupplierCatalogSync.objects.filter(supplier=supplier).order_by("-started_at")
        return qs[:limit] if limit else qs

    @staticmethod
    def get_last_sync(supplier: Supplier) -> SupplierCatalogSync | None:
        """Возвращает самую последнюю запись синхронизации."""
        return SupplierCatalogSyncDAO.get_by_supplier(supplier, limit=1).first()

    @staticmethod
    def recover_stale_syncs(timeout_hours: int = 2) -> int:
        """
        Находит задачи со статусом RUNNING, которые стартовали более timeout_hours назад,
        и переводит их в FAILED. Возвращает количество восстановленных задач.
        """
        threshold = timezone.now() - timedelta(hours=timeout_hours)
        count, _ = SupplierCatalogSync.objects.filter(
            status=SupplierCatalogSync.Status.RUNNING,
            started_at__lt=threshold,
        ).update(
            status=SupplierCatalogSync.Status.FAILED,
            error_log="Аварийное завершение: процесс завис или был прерван (timeout).",
            finished_at=timezone.now(),
        )
        if count:
            logger.warning("Восстановлено %d зависших задач синхронизации", count)
        return count
