"""
suppliers/service/dao.py

Data Access Object (DAO) для работы с базой данных модуля поставщиков.
Использует TYPE_CHECKING для безопасных аннотаций внешних моделей.
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
    @staticmethod
    def get_by_id(supplier_id: int) -> Supplier | None:
        try:
            return Supplier.objects.get(id=supplier_id)
        except Supplier.DoesNotExist:
            return None

    @staticmethod
    def get_active_suppliers() -> QuerySet[Supplier]:
        return Supplier.objects.filter(supplier_is_active=True)


# ─── SupplierStockRecord DAO ──────────────────────────────────────────────────

class SupplierStockRecordDAO:
    @staticmethod
    def get_by_supplier_product(supplier: Supplier, product: Product) -> SupplierStockRecord | None:
        try:
            return SupplierStockRecord.objects.select_related("currency").get(
                supplier=supplier, product=product
            )
        except SupplierStockRecord.DoesNotExist:
            return None

    @staticmethod
    def bulk_update_records(records: list[SupplierStockRecord], fields: list[str]) -> None:
        """Пакетное обновление существующих записей."""
        if records:
            SupplierStockRecord.objects.bulk_update(records, fields)

    @staticmethod
    def deactivate_missing(supplier: Supplier, active_skus: list[str]) -> int:
        deactivated = (
            SupplierStockRecord.objects.filter(supplier=supplier, is_active=True)
            .exclude(supplier_sku__in=active_skus)
            .update(is_active=False)
        )
        if deactivated > 0:
            logger.info("Деактивировано %d записей остатков для %s", deactivated, supplier.name)
        return deactivated


# ─── SupplierStockHistory DAO ─────────────────────────────────────────────────

class SupplierStockHistoryDAO:
    @staticmethod
    def bulk_create_history(history_records: list[SupplierStockHistory]) -> None:
        """Пакетное создание записей истории."""
        if history_records:
            SupplierStockHistory.objects.bulk_create(history_records)


# ─── SupplierCatalogSync DAO ──────────────────────────────────────────────────

class SupplierCatalogSyncDAO:
    @staticmethod
    def create_running(supplier: Supplier, triggered_by: str = "celery") -> SupplierCatalogSync:
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
