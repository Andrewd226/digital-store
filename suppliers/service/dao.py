"""
suppliers/service/dao.py

Граница доступа к данным. 
Публичный API принимает/возвращает ТОЛЬКО DTO или скалярные значения.
Все ORM-модели, маппинг, FK-резолвинг и пакетные операции инкапсулированы внутри.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from core.dao import CurrencyDAO
from catalogue.dao import ProductDAO
from suppliers.models import (
    Supplier,
    SupplierCaыtalogSync,
    SupplierCredential,
    SupplierStockHistory, 
    SupplierStockRecord,
)
from suppliers.service.dto import SupplierStockRecordDTO, SyncLogDTO, SyncStatsDTO

if TYPE_CHECKING:
    from core.models import Currency
    from catalogue.models import Product

logger = logging.getLogger(__name__)


# ─── Internal Mappers ─────────────────────────────────────────────────────────
def _to_record_dto(record: SupplierStockRecord) -> SupplierStockRecordDTO:
    return SupplierStockRecordDTO(
        id=record.id,
        supplier_sku=record.supplier_sku,
        price=record.price,
        currency_code=record.currency.currency_code,
        num_in_stock=record.num_in_stock,
        num_allocated=record.num_allocated,
        is_active=record.is_active,
        last_supplier_updated_at=record.last_supplier_updated_at,
        product_upc=record.product.upc,
    )


def _from_record_dto(dto: SupplierStockRecordDTO, currency: Currency, product: Product) -> SupplierStockRecord:
    instance = SupplierStockRecord(
        id=dto.id,
        supplier_sku=dto.supplier_sku,
        price=dto.price,
        currency=currency,
        num_in_stock=dto.num_in_stock,
        num_allocated=dto.num_allocated,
        is_active=dto.is_active,
        last_supplier_updated_at=dto.last_supplier_updated_at,
        product=product,
        supplier_id=dto.id,  # Placeholder, resolved internally
    )
    return instance


# ─── Public DAO API ───────────────────────────────────────────────────────────
class SupplierStockRecordDAO:
    @staticmethod
    def get_by_product_upc(product_upc: str) -> SupplierStockRecordDTO | None:
        """Возвращает DTO записи или None. FK резолвятся внутри."""
        try:
            record = SupplierStockRecord.objects.select_related("currency", "product").get(product__upc=product_upc)
            return _to_record_dto(record)
        except SupplierStockRecord.DoesNotExist:
            return None

    @staticmethod
    def get_last_updated_at(product_upc: str) -> datetime | None:
        """Скаляр: время последнего обновления по UPC."""
        return SupplierStockRecord.objects.filter(product__upc=product_upc).values_list("last_supplier_updated_at", flat=True).first()

    @staticmethod
    @transaction.atomic
    def bulk_save(records_dto: list[SupplierStockRecordDTO], supplier_id: int) -> None:
        """Принимает DTO, внутри маппит в ORM и выполняет bulk_create / bulk_update."""
        if not records_dto:
            return

        to_create: list[SupplierStockRecord] = []
        to_update: list[SupplierStockRecord] = []
        
        # Предзагрузка валют и продуктов для избежания N+1
        currency_codes = {dto.currency_code for dto in records_dto}
        product_upcs = {dto.product_upc for dto in records_dto if dto.product_upc}
        
        currencies_map = {c.currency_code: c for c in CurrencyDAO.get_by_codes(currency_codes)}
        products_map = {p.upc: p for p in ProductDAO.get_by_upcs(product_upcs)}
        
        supplier = Supplier.objects.get(id=supplier_id)

        for dto in records_dto:
            currency = currencies_map.get(dto.currency_code)
            product = products_map.get(dto.product_upc) if dto.product_upc else None
            
            if not currency or not product:
                logger.warning("Пропущена запись: валюта=%s, upc=%s", dto.currency_code, dto.product_upc)
                continue

            if dto.id is None:
                obj = SupplierStockRecord(
                    supplier=supplier, product=product,
                    supplier_sku=dto.supplier_sku, price=dto.price,
                    currency=currency, num_in_stock=dto.num_in_stock,
                    num_allocated=dto.num_allocated, is_active=dto.is_active,
                    last_supplier_updated_at=dto.last_supplier_updated_at,
                )
                to_create.append(obj)
            else:
                obj = SupplierStockRecord(
                    id=dto.id, supplier_id=supplier.id, product_id=product.id,
                    supplier_sku=dto.supplier_sku, price=dto.price,
                    currency=currency, num_in_stock=dto.num_in_stock,
                    num_allocated=dto.num_allocated, is_active=dto.is_active,
                    last_supplier_updated_at=dto.last_supplier_updated_at,
                )
                to_update.append(obj)

        if to_create:
            SupplierStockRecord.objects.bulk_create(to_create)
        if to_update:
            SupplierStockRecord.objects.bulk_update(to_update, [
                "supplier_sku", "price", "currency_id", "num_in_stock",
                "num_allocated", "is_active", "last_supplier_updated_at"
            ])


class SyncLogDAO:
    @staticmethod
    def create_running(supplier_code: str, triggered_by: str = "celery") -> SyncLogDTO:
        supplier = Supplier.objects.get(code=supplier_code)
        sync = SupplierCatalogSync.objects.create(
            supplier=supplier,
            status=SupplierCatalogSync.Status.RUNNING,
            triggered_by=triggered_by,
            started_at=timezone.now(),
        )
        return SyncLogDTO(
            id=sync.id, supplier_code=supplier.code, status=sync.status,
            triggered_by=sync.triggered_by, started_at=sync.started_at,
        )

    @staticmethod
    @transaction.atomic
    def complete(sync_id: int, status: str, stats: SyncStatsDTO, error_log: str = "") -> SyncLogDTO:
        sync = SupplierCatalogSync.objects.get(id=sync_id)
        sync.status = status
        sync.finished_at = timezone.now()
        sync.total_items, sync.created_items, sync.updated_items = stats.total, stats.created, stats.updated
        sync.skipped_items, sync.failed_items, sync.error_log = stats.skipped, stats.failed, error_log[:65535]
        sync.save(update_fields=[
            "status", "finished_at", "total_items", "created_items",
            "updated_items", "skipped_items", "failed_items", "error_log"
        ])
        return SyncLogDTO(
            id=sync.id, supplier_code=sync.supplier.code, status=sync.status,
            triggered_by=sync.triggered_by, started_at=sync.started_at,
            finished_at=sync.finished_at,
        )

    @staticmethod
    def recover_stale_syncs(timeout_hours: int = 2) -> int:
        threshold = timezone.now() - timedelta(hours=timeout_hours)
        count, _ = SupplierCatalogSync.objects.filter(
            status=SupplierCatalogSync.Status.RUNNING, started_at__lt=threshold
        ).update(status=SupplierCatalogSync.Status.FAILED, error_log="Timeout/Zombie recovery", finished_at=timezone.now())
        return count
