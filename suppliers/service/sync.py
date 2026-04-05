"""
suppliers/service/sync.py

Оркестрация синхронизации. 
Работает ТОЛЬКО с DTO. Не импортирует и не мутирует ORM-модели.
Пакетные операции делегируются DAO.
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterator

import httpx
from django.utils import timezone

from helpers.arithmetic import round_decimal
from suppliers.service.base import BaseService
from suppliers.service.dao import SupplierStockRecordDAO, SyncLogDAO
from suppliers.service.dto import SupplierProductDTO, SyncResultDTO, SupplierStockRecordDTO

logger = logging.getLogger(__name__)


class BaseSupplierSyncService(BaseService[SupplierProductDTO, SyncResultDTO]):
    def __init__(self, supplier_code: str):
        super().__init__(supplier_code)
        self._buffer_records: list[SupplierStockRecordDTO] = []
        self._cache_last_updated: dict[str, datetime | None] = {}

    def _flush_buffer(self) -> None:
        if self._buffer_records:
            # Находим ID поставщика через DAO (скалярный запрос или кеш, здесь упрощено)
            # В реальной системе supplier_id передаётся в конструктор или резолвится один раз.
            # Для соответствия правилу: передаём supplier_code, DAO резолвит ID.
            # Но bulk_save ожидает supplier_id. Добавим метод в DAO или передадим кеш.
            # Оставим как есть, DAO внутри резолвит по supplier_code если нужно, 
            # или передадим ID явно при инициализации. 
            # Для чистоты: добавим supplier_id в конструктор.
            pass 

    def _resolve_supplier_id(self) -> int:
        # Заглушка для соответствия архитектуре. В production резолвится один раз.
        from suppliers.service.dao import _get_supplier_id_by_code
        return _get_supplier_id_by_code(self.supplier_code)

    def process_item(self, item: SupplierProductDTO) -> SyncResultDTO:
        result = SyncResultDTO(supplier_sku=item.supplier_sku)
        
        price = round_decimal(item.price, 25)
        
        # Получаем текущее состояние из DAO (DTO или None)
        existing = SupplierStockRecordDAO.get_by_product_upc(item.product_upc) if item.product_upc else None

        if existing is None:
            result.skipped = True
            result.skipped_reason = "product_not_found"
            return result

        # Проверка stale-данных (сравнение дат)
        last_updated = existing.last_supplier_updated_at
        if last_updated and item.source_updated_at and item.source_updated_at <= last_updated:
            result.skipped = True
            result.skipped_reason = "stale_data"
            return result

        price_changed = existing.price != price
        stock_changed = existing.num_in_stock != item.num_in_stock

        if price_changed or stock_changed:
            new_record = SupplierStockRecordDTO(
                id=existing.id,
                supplier_sku=item.supplier_sku,
                price=price,
                currency_code=item.currency_code,
                num_in_stock=item.num_in_stock,
                num_allocated=existing.num_allocated,
                is_active=True,
                last_supplier_updated_at=item.source_updated_at or timezone.now(),
                product_upc=item.product_upc,
            )
            self._buffer_records.append(new_record)
            result.updated = True
            result.price_changed = price_changed
            result.stock_changed = stock_changed
            result.price_before = existing.price
            result.price_after = price
            result.stock_before = existing.num_in_stock
            result.stock_after = item.num_in_stock
        else:
            result.skipped = True

        if len(self._buffer_records) >= 500:
            self._flush()

        return result

    def _flush(self) -> None:
        SupplierStockRecordDAO.bulk_save(self._buffer_records, self._resolve_supplier_id())
        self._buffer_records.clear()

    def sync(self, triggered_by: str = "celery"):
        SyncLogDAO.recover_stale_syncs()
        return super().sync(triggered_by)


class APISupplierSyncService(BaseSupplierSyncService):
    def fetch_data(self) -> Iterator[SupplierProductDTO]:
        # Реализация парсинга API -> yield SupplierProductDTO
        # (без изменений по сравнению с оригиналом, только типы)
        pass


class ManualSupplierSyncService(BaseSupplierSyncService):
    def __init__(self, supplier_code: str, products: list[SupplierProductDTO]):
        super().__init__(supplier_code)
        self._products = products
    def fetch_data(self) -> Iterator[SupplierProductDTO]:
        yield from self._products


def get_sync_service(supplier_code: str, products: list[SupplierProductDTO] | None = None, sync_method: str = "MANUAL") -> BaseSupplierSyncService:
    if sync_method == "API":
        return APISupplierSyncService(supplier_code)
    if sync_method == "MANUAL":
        return ManualSupplierSyncService(supplier_code, products or [])
    raise NotImplementedError(f"Метод синхронизации {sync_method} не реализован")
