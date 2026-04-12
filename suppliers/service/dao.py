"""
suppliers/service/dao.py

Data Access Objects сервиса синхронизации каталогов поставщиков.
Единственный слой, обращающийся к ORM напрямую.
Принимает и возвращает только DTO или скалярные значения.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from suppliers.models import (
    Supplier,
    SupplierCatalogSync,
    SupplierCredential,
    SupplierStockHistory,
    SupplierStockRecord,
)
from suppliers.service.dto import (
    CatalogSyncResultDTO,
    SupplierCredentialDTO,
    SupplierDTO,
    SupplierStockHistoryCreateDTO,
    SupplierStockRecordCreateDTO,
    SupplierStockRecordDTO,
    SupplierStockRecordUpdateDTO,
)

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 500


class SupplierDAO:
    """DAO для операций с поставщиками."""

    # @staticmethod
    # def _to_dto(supplier: Supplier) -> SupplierDTO:
    #     return SupplierDTO(
    #         id=supplier.id,
    #         name=supplier.name,
    #         code=supplier.code,
    #         sync_method=supplier.sync_method,
    #         api_url=supplier.api_url,
    #         api_extra_config=supplier.api_extra_config,
    #         default_currency_code=supplier.default_currency_id,
    #     )

    @staticmethod
    def get_active_ids() -> list[int]:
        """Возвращает всех активных поставщиков."""
        return [
            d.id
            for s in Supplier.objects.filter(supplier_is_active=True).order_by("priority", "name")
        ]

    @staticmethod
    def get_by_id(supplier_id: int) -> SupplierDTO | None:
        """Возвращает поставщика по id или None."""
        try:
            return SupplierDTO.model_validate(Supplier.objects.get(id=supplier_id))
        except Supplier.DoesNotExist:
            return None

    @staticmethod
    def get_credential(supplier_id: int) -> SupplierCredentialDTO | None:
        """Возвращает учётные данные поставщика или None."""
        try:
            cred = SupplierCredential.objects.get(supplier_id=supplier_id)
            return SupplierCredentialDTO(
                api_key=cred.api_key,
                api_secret=cred.api_secret,
                extra=cred.extra,
            )
        except SupplierCredential.DoesNotExist:
            return None


class SupplierStockRecordDAO:
    """DAO для операций с записями остатков поставщиков."""

    # @staticmethod
    # def _to_dto(record: SupplierStockRecord) -> SupplierStockRecordDTO:
    #     return SupplierStockRecordDTO(
    #         id=record.id,
    #         supplier_id=record.supplier_id,
    #         product_id=record.product_id,
    #         supplier_sku=record.supplier_sku,
    #         price=record.price,
    #         currency_code=record.currency_id,
    #         num_in_stock=record.num_in_stock,
    #         is_active=record.is_active,
    #         last_supplier_updated_at=record.last_supplier_updated_at,
    #     )

    @staticmethod
    def get_by_supplier(supplier_id: int) -> list[SupplierStockRecordDTO]:
        """Возвращает все текущие записи остатков поставщика одним запросом."""
        return [
            SupplierStockRecordDTO.model_validate(r)
            for r in SupplierStockRecord.objects.filter(supplier_id=supplier_id)
        ]

    @staticmethod
    def bulk_create(records: list[SupplierStockRecordCreateDTO]) -> list[SupplierStockRecordDTO]:
        """
        Bulk-создание новых записей остатков.

        После bulk_create перечитывает созданные записи из БД по (supplier_id, supplier_sku)
        чтобы получить актуальные id — Django не гарантирует заполнение pk
        при ignore_conflicts=True.
        """
        if not records:
            return []

        supplier_id = records[0].supplier_id
        new_skus = {r.supplier_sku for r in records}

        objs = [
            SupplierStockRecord(
                supplier_id=r.supplier_id,
                product_id=r.product_id,
                supplier_sku=r.supplier_sku,
                price=r.price,
                currency_id=r.currency_code,
                num_in_stock=r.num_in_stock,
                is_active=r.is_active,
                last_supplier_updated_at=r.last_supplier_updated_at,
            )
            for r in records
        ]

        for i in range(0, len(objs), _CHUNK_SIZE):
            SupplierStockRecord.objects.bulk_create(
                objs[i : i + _CHUNK_SIZE],
                ignore_conflicts=True,
            )

        created = SupplierStockRecord.objects.filter(
            supplier_id=supplier_id,
            supplier_sku__in=new_skus,
        )
        return [SupplierStockRecordDTO.model_validate(r) for r in created]

    @staticmethod
    def bulk_update(records: list[SupplierStockRecordUpdateDTO]) -> int:
        """
        Bulk-обновление существующих записей остатков.
        Возвращает количество обновлённых записей.
        """
        if not records:
            return 0

        record_map = {r.id: r for r in records}
        ids = list(record_map.keys())

        objs = list(SupplierStockRecord.objects.filter(id__in=ids))
        for obj in objs:
            dto = record_map[obj.id]
            obj.price = dto.price
            obj.currency_id = dto.currency_code
            obj.num_in_stock = dto.num_in_stock
            obj.is_active = dto.is_active
            obj.last_supplier_updated_at = dto.last_supplier_updated_at

        total = 0
        for i in range(0, len(objs), _CHUNK_SIZE):
            chunk = objs[i : i + _CHUNK_SIZE]
            SupplierStockRecord.objects.bulk_update(
                chunk,
                fields=["price", "currency_id", "num_in_stock", "is_active", "last_supplier_updated_at"],
            )
            total += len(chunk)

        return total


class SupplierStockHistoryDAO:
    """DAO для append-only записи истории изменений остатков."""

    @staticmethod
    def bulk_create(items: list[SupplierStockHistoryCreateDTO]) -> None:
        """Bulk-создание записей истории изменений."""
        if not items:
            return

        objs = [
            SupplierStockHistory(
                stock_record_id=item.stock_record_id,
                sync_id=item.sync_id,
                snapshot_supplier_name=item.snapshot_supplier_name,
                snapshot_product_title=item.snapshot_product_title,
                snapshot_product_upc=item.snapshot_product_upc,
                snapshot_supplier_sku=item.snapshot_supplier_sku,
                snapshot_currency_code=item.snapshot_currency_code,
                price_before=item.price_before,
                price_after=item.price_after,
                num_in_stock_before=item.num_in_stock_before,
                num_in_stock_after=item.num_in_stock_after,
                change_type=item.change_type,
            )
            for item in items
        ]

        for i in range(0, len(objs), _CHUNK_SIZE):
            SupplierStockHistory.objects.bulk_create(objs[i : i + _CHUNK_SIZE])


class SupplierCatalogSyncDAO:
    """DAO для управления логом синхронизаций."""

    @staticmethod
    def create_running(supplier_id: int) -> int:
        """
        Создаёт запись синхронизации со статусом RUNNING.
        Возвращает id созданной записи (скалярное значение).
        """
        sync = SupplierCatalogSync.objects.create(
            supplier_id=supplier_id,
            status=SupplierCatalogSync.Status.RUNNING,
        )
        return sync.id

    @staticmethod
    def mark_success(sync_id: int, result: CatalogSyncResultDTO) -> None:
        """Помечает синхронизацию успешной и записывает итоговую статистику."""
        SupplierCatalogSync.objects.filter(id=sync_id).update(
            status=SupplierCatalogSync.Status.SUCCESS,
            finished_at=timezone.now(),
            total_items=result.total_items,
            created_items=result.created_items,
            updated_items=result.updated_items,
            skipped_items=result.skipped_items,
            failed_items=result.failed_items,
        )

    @staticmethod
    def mark_failed(sync_id: int, error_log: str) -> None:
        """Помечает синхронизацию проваленной и записывает лог ошибок."""
        SupplierCatalogSync.objects.filter(id=sync_id).update(
            status=SupplierCatalogSync.Status.FAILED,
            finished_at=timezone.now(),
            error_log=error_log,
        )
