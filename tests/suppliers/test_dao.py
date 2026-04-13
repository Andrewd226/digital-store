"""
tests/suppliers/test_dao.py
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from django.db import transaction
from django.test.utils import CaptureQueriesContext
from django.db import connection

from suppliers.models import (
    Supplier,
    SupplierStockRecord,
    SupplierStockHistory,
    SupplierCatalogSync,
)
from suppliers.service.dto import (
    SupplierPriceDTO,
    SupplierStockRecordDTO,
    SupplierSyncStatusDTO,
    CatalogSyncResultDTO,
)
from suppliers.service.dao import (
    SupplierDAO,
    SupplierStockRecordDAO,
    SupplierCatalogSyncDAO,
)


# region Fixtures

@pytest.fixture
def supplier(db):
    return Supplier.objects.create(
        code="TEST_SUPPLIER",
        name="Test Supplier",
        base_currency="USD",
        sync_interval_min=15,
        is_active=True,
    )


@pytest.fixture
def dao_stock():
    return SupplierStockRecordDAO()


@pytest.fixture
def dao_sync():
    return SupplierCatalogSyncDAO()


@pytest.fixture
def dao_supplier():
    return SupplierDAO()


@pytest.fixture
def price_dto():
    return SupplierPriceDTO(
        external_sku="EXT-SKU-001",
        price=Decimal("1245.50"),
        currency_code="USD",
        stock_quantity=Decimal("42.000000"),
        updated_at=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def bulk_price_dtos():
    return [
        SupplierPriceDTO(
            external_sku=f"BULK-SKU-{i:03d}",
            price=Decimal(f"{i * 100}.{i:02d}"),
            currency_code="USD",
            stock_quantity=Decimal(f"{i * 5}.000000"),
            updated_at=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
        )
        for i in range(1, 11)
    ]

# endregion


@pytest.mark.django_db
class TestSupplierDAO:
    """Тесты для SupplierDAO — работа с поставщиками."""

    def test_get_active_ids_returns_scalar_list(self, dao_supplier, supplier, db):
        Supplier.objects.create(
            code="INACTIVE",
            name="Inactive",
            base_currency="EUR",
            is_active=False,
        )
        
        result = dao_supplier.get_active_ids()
        
        assert isinstance(result, list)
        assert all(isinstance(uid, int) for uid in result)
        assert supplier.id in result
        assert len(result) == 1

    def test_get_by_id_returns_none_for_missing(self, dao_supplier):
        result = dao_supplier.get_by_id(99999)
        assert result is None


@pytest.mark.django_db
class TestSupplierStockRecordDAO:
    """Тесты для SupplierStockRecordDAO — цены и остатки."""

    def test_upsert_creates_new_record_returns_dto(self, dao_stock, supplier, price_dto):
        result = dao_stock.upsert_price(supplier.id, price_dto)
        
        assert isinstance(result, SupplierStockRecordDTO)
        assert result.price == price_dto.price
        assert result.stock_quantity == price_dto.stock_quantity
        assert result.currency_code == price_dto.currency_code
        assert result.external_sku == price_dto.external_sku
        assert SupplierStockRecord.objects.count() == 1

    def test_upsert_updates_existing_and_records_history(self, dao_stock, supplier, price_dto):
        dao_stock.upsert_price(supplier.id, price_dto)
        
        updated_dto = SupplierPriceDTO(
            external_sku=price_dto.external_sku,
            price=Decimal("1300.00"),
            currency_code="USD",
            stock_quantity=Decimal("38.000000"),
            updated_at=datetime(2024, 6, 16, 10, 0, 0, tzinfo=timezone.utc),
        )
        
        result = dao_stock.upsert_price(supplier.id, updated_dto)
        
        assert result.price == Decimal("1300.00")
        assert SupplierStockRecord.objects.count() == 1
        assert SupplierStockHistory.objects.count() == 2

    def test_upsert_skips_unchanged_data(self, dao_stock, supplier, price_dto):
        dao_stock.upsert_price(supplier.id, price_dto)
        initial_history_count = SupplierStockHistory.objects.count()
        
        same_dto = SupplierPriceDTO(
            external_sku=price_dto.external_sku,
            price=price_dto.price,
            currency_code=price_dto.currency_code,
            stock_quantity=price_dto.stock_quantity,
            updated_at=datetime(2024, 6, 17, 10, 0, 0, tzinfo=timezone.utc),
        )
        
        result = dao_stock.upsert_price(supplier.id, same_dto)
        
        assert result is None
        assert SupplierStockHistory.objects.count() == initial_history_count

    def test_bulk_upsert_uses_bulk_operations(self, dao_stock, supplier, bulk_price_dtos):
        with CaptureQueriesContext(connection) as ctx:
            results = dao_stock.bulk_upsert_prices(supplier.id, bulk_price_dtos)
        
        queries = [q["sql"].lower() for q in ctx.captured_queries]
        assert any("insert" in q and "supplier_stockrecord" in q for q in queries)
        assert any("update" in q and "supplier_stockrecord" in q for q in queries)
        assert len(results) == len(bulk_price_dtos)
        assert all(isinstance(r, SupplierStockRecordDTO) for r in results)

    def test_bulk_upsert_handles_mixed_create_update(self, dao_stock, supplier, bulk_price_dtos):
        existing_dto = bulk_price_dtos[0].model_copy(update={"price": Decimal("999.99")})
        dtos = [existing_dto] + bulk_price_dtos[1:]
        
        results = dao_stock.bulk_upsert_prices(supplier.id, dtos)
        
        assert len(results) == len(dtos)
        assert results[0].price == Decimal("999.99")

    @pytest.mark.django_db(transaction=True)
    def test_upsert_is_transactional_with_history(self, dao_stock, supplier, price_dto, mocker):
        dao_stock.upsert_price(supplier.id, price_dto)
        
        mocker.patch(
            "suppliers.service.dao.SupplierStockHistory.objects.bulk_create",
            side_effect=RuntimeError("History write failed"),
        )
        
        new_price_dto = price_dto.model_copy(update={
            "price": Decimal("999.00"),
            "updated_at": datetime(2024, 6, 16, 10, 0, 0, tzinfo=timezone.utc),
        })
        
        with pytest.raises(RuntimeError):
            dao_stock.upsert_price(supplier.id, new_price_dto)
        
        record = SupplierStockRecord.objects.get(
            supplier=supplier,
            external_sku=price_dto.external_sku,
        )
        assert record.price == price_dto.price
        assert SupplierStockHistory.objects.count() == 1

    def test_get_active_by_supplier_returns_dto_list(self, dao_stock, supplier, price_dto):
        dao_stock.upsert_price(supplier.id, price_dto)
        
        results = dao_stock.get_active_by_supplier(supplier.id)
        
        assert isinstance(results, list)
        assert all(isinstance(r, SupplierStockRecordDTO) for r in results)
        assert len(results) == 1
        assert results[0].price == price_dto.price


@pytest.mark.django_db
class TestSupplierCatalogSyncDAO:
    """Тесты для SupplierCatalogSyncDAO — управление задачами синхронизации."""

    def test_create_running_returns_scalar_id(self, dao_sync, supplier):
        result = dao_sync.create_running(supplier.id, task_type="full")
        
        assert isinstance(result, int)
        assert SupplierCatalogSync.objects.filter(id=result, status="running").exists()

    def test_update_progress_returns_processed_count(self, dao_sync, supplier):
        sync_id = dao_sync.create_running(supplier.id, task_type="prices")
        
        result = dao_sync.update_progress(sync_id, processed=150, errors=3)
        
        assert isinstance(result, int)
        assert result == 150
        sync = SupplierCatalogSync.objects.get(id=sync_id)
        assert sync.processed_count == 150
        assert sync.error_count == 3

    def test_finalize_completed_updates_fields(self, dao_sync, supplier):
        sync_id = dao_sync.create_running(supplier.id, task_type="full")
        
        result = dao_sync.finalize_completed(
            sync_id,
            created=10,
            updated=25,
            unchanged=5,
            errors=2,
            error_log="Minor issues",
        )
        
        assert isinstance(result, CatalogSyncResultDTO)
        assert result.created_items == 10
        assert result.updated_items == 25
        assert result.unchanged_items == 5
        assert result.failed_items == 2
        
        sync = SupplierCatalogSync.objects.get(id=sync_id)
        assert sync.status == "completed"
        assert sync.finished_at is not None

    @pytest.mark.django_db(transaction=True)
    def test_finalize_rolls_back_on_error(self, dao_sync, supplier, mocker):
        sync_id = dao_sync.create_running(supplier.id, task_type="full")
        
        mocker.patch(
            "suppliers.service.dao.SupplierCatalogSync.objects.filter.update",
            side_effect=ConnectionError("DB timeout"),
        )
        
        with pytest.raises(ConnectionError):
            dao_sync.finalize_completed(
                sync_id,
                created=5,
                updated=0,
                unchanged=0,
                errors=0,
                error_log=None,
            )
        
        sync = SupplierCatalogSync.objects.get(id=sync_id)
        assert sync.status == "running"
        assert sync.finished_at is None

    def test_get_recent_failed_returns_dto_list(self, dao_sync, supplier):
        dao_sync.create_running(supplier.id, task_type="full")
        dao_sync.finalize_completed(
            1, created=0, updated=0, unchanged=0, errors=5, error_log="Test error"
        )
        
        results = dao_sync.get_recent_failed(limit=5)
        
        assert isinstance(results, list)
        assert all(isinstance(r, SupplierSyncStatusDTO) for r in results)
