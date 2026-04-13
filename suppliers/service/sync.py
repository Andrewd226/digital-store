"""
suppliers/service/sync.py

Бизнес-логика обработки каталога поставщика.
Не обращается к ORM напрямую — только через DAO и DTO.
"""

from __future__ import annotations

import logging

from django.db import transaction

from catalogue.dao import ProductDAO
from catalogue.dto import ProductDTO
from suppliers.service.dao import SupplierStockHistoryDAO, SupplierStockRecordDAO
from suppliers.service.dto import (
    CatalogSyncResultDTO,
    RawCatalogItemDTO,
    StockChangeType,
    SupplierDTO,
    SupplierStockHistoryCreateDTO,
    SupplierStockRecordCreateDTO,
    SupplierStockRecordDTO,
    SupplierStockRecordUpdateDTO,
)

logger = logging.getLogger(__name__)


def _determine_change_type(
    existing: SupplierStockRecordDTO,
    raw: RawCatalogItemDTO,
) -> StockChangeType:
    """Определяет тип изменения по сравнению существующей записи с новыми данными."""
    price_changed = existing.price != raw.price or existing.currency_code != raw.currency_code
    stock_changed = existing.num_in_stock != raw.num_in_stock

    if price_changed and stock_changed:
        return StockChangeType.BOTH_CHANGED
    if price_changed:
        return StockChangeType.PRICE_CHANGED
    return StockChangeType.STOCK_CHANGED


def _is_stale(
    existing: SupplierStockRecordDTO,
    raw: RawCatalogItemDTO,
) -> bool:
    """
    Проверяет, являются ли входящие данные устаревшими.
    Если supplier_updated_at у входящей позиции не новее последнего обновления
    у поставщика — обновление пропускается.
    """
    if raw.supplier_updated_at is None or existing.last_supplier_updated_at is None:
        return False
    return raw.supplier_updated_at <= existing.last_supplier_updated_at


def process_catalog(
    supplier: SupplierDTO,
    raw_items: list[RawCatalogItemDTO],
    sync_id: int,
    stock_record_dao: SupplierStockRecordDAO,
    history_dao: SupplierStockHistoryDAO,
    product_dao: ProductDAO,
) -> CatalogSyncResultDTO:
    """
    Обрабатывает сырые позиции каталога: вычисляет diff, сохраняет изменения и историю.

    Алгоритм:
    1. Загрузить текущие записи остатков поставщика — один запрос.
    2. Загрузить продукты по всем SKU — один запрос.
    3. Для каждой позиции:
       - нет Product → SKIPPED
       - есть запись, данные устарели → SKIPPED
       - есть запись, нет изменений → SKIPPED
       - есть запись, есть изменения → собрать UpdateDTO + HistoryCreateDTO
       - нет записи → собрать CreateDTO, запомнить для истории
    4. В transaction.atomic():
       - bulk_update существующих
       - bulk_create новых → перечитать с id
       - bulk_create всей истории
    5. Вернуть CatalogSyncResultDTO.
    """
    # 1. Текущие записи остатков: ключ — supplier_sku
    existing_records: dict[str, SupplierStockRecordDTO] = {
        r.supplier_sku: r for r in stock_record_dao.get_by_supplier(supplier.id)
    }

    # 2. Продукты по всем входящим SKU: один запрос
    all_skus = [item.supplier_sku for item in raw_items]
    products: dict[str, ProductDTO] = {
        p.upc: p for p in product_dao.get_by_upc_list(all_skus) if p.upc
    }

    to_create: list[SupplierStockRecordCreateDTO] = []
    to_update: list[SupplierStockRecordUpdateDTO] = []

    # История обновлённых записей (id известны)
    history_for_updates: list[SupplierStockHistoryCreateDTO] = []

    # Данные для истории создаваемых записей (id станут известны после bulk_create)
    # (supplier_sku, raw, product) — для построения DTO после получения id
    pending_create_history: list[tuple[str, RawCatalogItemDTO, ProductDTO]] = []

    created_items = 0
    updated_items = 0
    skipped_items = 0
    failed_items = 0

    # 3. Построение diff
    for raw in raw_items:
        product = products.get(raw.supplier_sku)
        if product is None:
            skipped_items += 1
            continue

        existing = existing_records.get(raw.supplier_sku)

        if existing is not None:
            if _is_stale(existing, raw):
                skipped_items += 1
                continue

            price_changed = (
                existing.price != raw.price or existing.currency_code != raw.currency_code
            )
            stock_changed = existing.num_in_stock != raw.num_in_stock

            if not price_changed and not stock_changed:
                skipped_items += 1
                continue

            change_type = _determine_change_type(existing, raw)

            to_update.append(
                SupplierStockRecordUpdateDTO(
                    id=existing.id,
                    price=raw.price,
                    currency_code=raw.currency_code,
                    num_in_stock=raw.num_in_stock,
                    is_active=True,
                    last_supplier_updated_at=raw.supplier_updated_at,
                )
            )
            history_for_updates.append(
                SupplierStockHistoryCreateDTO(
                    stock_record_id=existing.id,
                    sync_id=sync_id,
                    snapshot_supplier_name=supplier.name,
                    snapshot_product_title=product.title,
                    snapshot_product_upc=product.upc or "",
                    snapshot_supplier_sku=raw.supplier_sku,
                    snapshot_currency_code=raw.currency_code,
                    price_before=existing.price,
                    price_after=raw.price,
                    num_in_stock_before=existing.num_in_stock,
                    num_in_stock_after=raw.num_in_stock,
                    change_type=change_type,
                )
            )
            updated_items += 1

        else:
            to_create.append(
                SupplierStockRecordCreateDTO(
                    supplier_id=supplier.id,
                    product_id=product.id,
                    supplier_sku=raw.supplier_sku,
                    price=raw.price,
                    currency_code=raw.currency_code,
                    num_in_stock=raw.num_in_stock,
                    is_active=True,
                    last_supplier_updated_at=raw.supplier_updated_at,
                )
            )
            pending_create_history.append((raw.supplier_sku, raw, product))
            created_items += 1

    # 4. Атомарное сохранение: обновления + создание + история
    with transaction.atomic():
        stock_record_dao.bulk_update(to_update)

        # bulk_create перечитывает созданные записи из БД, возвращая DTO с id
        created_dtos = stock_record_dao.bulk_create(to_create)
        created_id_map: dict[str, int] = {dto.supplier_sku: dto.id for dto in created_dtos}

        # Строим историю для созданных записей — теперь id известны
        history_for_creates: list[SupplierStockHistoryCreateDTO] = []
        for sku, raw, product in pending_create_history:
            record_id = created_id_map.get(sku)
            if record_id is None:
                logger.warning(
                    "bulk_create не вернул id для sku=%s [supplier=%s]",
                    sku,
                    supplier.code,
                )
                failed_items += 1
                created_items -= 1
                continue

            history_for_creates.append(
                SupplierStockHistoryCreateDTO(
                    stock_record_id=record_id,
                    sync_id=sync_id,
                    snapshot_supplier_name=supplier.name,
                    snapshot_product_title=product.title,
                    snapshot_product_upc=product.upc or "",
                    snapshot_supplier_sku=raw.supplier_sku,
                    snapshot_currency_code=raw.currency_code,
                    price_before=None,
                    price_after=raw.price,
                    num_in_stock_before=None,
                    num_in_stock_after=raw.num_in_stock,
                    change_type=StockChangeType.CREATED,
                )
            )

        history_dao.bulk_create(history_for_updates + history_for_creates)

    return CatalogSyncResultDTO(
        sync_id=sync_id,
        total_items=len(raw_items),
        created_items=created_items,
        updated_items=updated_items,
        skipped_items=skipped_items,
        failed_items=failed_items,
    )
