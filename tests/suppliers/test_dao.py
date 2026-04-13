"""
tests/suppliers/test_dao.py
"""

from __future__ import annotations

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from catalogue.models import Product
from core.models import Currency
from suppliers.models import (
    Supplier,
    SupplierCatalogSync,
    SupplierCredential,
    SupplierStockHistory,
    SupplierStockRecord,
)
from suppliers.service.dao import (
    SupplierCatalogSyncDAO,
    SupplierDAO,
    SupplierStockHistoryDAO,
    SupplierStockRecordDAO,
)
from suppliers.service.dto import (
    CatalogSyncResultDTO,
    SupplierCredentialDTO,
    SupplierDTO,
    SupplierStockHistoryCreateDTO,
    SupplierStockRecordCreateDTO,
    SupplierStockRecordDTO,
    SupplierStockRecordUpdateDTO,
    StockChangeType,
)

if TYPE_CHECKING:



# region Fixtures

@pytest.fixture
def currency_usd(db: None) -> Currency:
    currency, _ = Currency.objects.get_or_create(
        code="USD",
        defaults={"name": "US Dollar", "symbol": "$"},
    )
    return currency


@pytest.fixture
def currency_eur(db: None) -> Currency:
    currency, _ = Currency.objects.get_or_create(
        code="EUR",
        defaults={"name": "Euro", "symbol": "€"},
    )
    return currency


@pytest.fixture
def supplier(db: None, currency_usd: Currency) -> Supplier:
    return Supplier.objects.create(
        name="Test Supplier",
        code="TEST_SUPPLIER",
        sync_method=Supplier.SyncMethod.API,
        default_currency=currency_usd,
        priority=100,
        supplier_is_active=True,
    )


@pytest.fixture
def product(db: None) -> Product:
    return Product.objects.create(
        title="Test Product",
        slug="test-product",
        upc="TEST-UPC-001",
    )


@pytest.fixture
def dao_supplier() -> SupplierDAO:
    return SupplierDAO()


@pytest.fixture
def dao_stock() -> SupplierStockRecordDAO:
    return SupplierStockRecordDAO()


@pytest.fixture
def dao_history() -> SupplierStockHistoryDAO:
    return SupplierStockHistoryDAO()


@pytest.fixture
def dao_sync() -> SupplierCatalogSyncDAO:
    return SupplierCatalogSyncDAO()


@pytest.fixture
def stock_create_dto(
    supplier: Supplier,
    product: Product,
    currency_usd: Currency,
) -> SupplierStockRecordCreateDTO:
    return SupplierStockRecordCreateDTO(
        supplier_id=supplier.id,
        product_id=product.id,
        supplier_sku="SUP-SKU-001",
        price=Decimal("1245.50"),
        currency_code=currency_usd.code,
        num_in_stock=42,
        is_active=True,
        last_supplier_updated_at=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def bulk_create_dtos(
    supplier: Supplier,
    product: Product,
    currency_usd: Currency,
) -> list[SupplierStockRecordCreateDTO]:
    return [
        SupplierStockRecordCreateDTO(
            supplier_id=supplier.id,
            product_id=product.id,
            supplier_sku=f"BULK-SKU-{i:03d}",
            price=Decimal(f"{i * 100}.{i:02d}"),
            currency_code=currency_usd.code,
            num_in_stock=i * 5,
            is_active=True,
            last_supplier_updated_at=datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
        )
        for i in range(1, 11)
    ]

# endregion


@pytest.mark.django_db
class TestSupplierDAO:
    """Тесты для SupplierDAO."""

    def test_get_active_ids_returns_scalar_list(
        self,
        dao_supplier: SupplierDAO,
        supplier: Supplier,
        db: None,
    ) -> None:
        Supplier.objects.create(
            name="Inactive",
            code="INACTIVE",
            default_currency=supplier.default_currency,
            supplier_is_active=False,
        )

        result = dao_supplier.get_active_ids()

        assert isinstance(result, list)
        assert all(isinstance(uid, int) for uid in result)
        assert supplier.id in result
        assert len(result) == 1

    def test_get_by_id_returns_dto_or_none(
        self,
        dao_supplier: SupplierDAO,
        supplier: Supplier,
    ) -> None:
        result = dao_supplier.get_by_id(supplier.id)
        assert isinstance(result, SupplierDTO)
        assert result.id == supplier.id
        assert result.code == supplier.code

        missing = dao_supplier.get_by_id(99999)
        assert missing is None

    def test_get_credential_returns_dto_or_none(
        self,
        dao_supplier: SupplierDAO,
        supplier: Supplier,
        db: None,
    ) -> None:
        SupplierCredential.objects.create(
            supplier=supplier,
            api_key="test_key",
            api_secret="test_secret",
        )

        result = dao_supplier.get_credential(supplier.id)
        assert isinstance(result, SupplierCredentialDTO)
        assert result.api_key == "test_key"

        missing = dao_supplier.get_credential(99999)
        assert missing is None


@pytest.mark.django_db
class TestSupplierStockRecordDAO:
    """Тесты для SupplierStockRecordDAO."""

    def test_bulk_create_returns_dto_list(
        self,
        dao_stock: SupplierStockRecordDAO,
        bulk_create_dtos: list[SupplierStockRecordCreateDTO],
    ) -> None:
        results = dao_stock.bulk_create(bulk_create_dtos)

        assert len(results) == len(bulk_create_dtos)
        assert all(isinstance(r, SupplierStockRecordDTO) for r in results)
        assert all(r.id is not None for r in results)
        assert SupplierStockRecord.objects.count() == len(bulk_create_dtos)

    def test_bulk_create_ignores_duplicates(
        self,
        dao_stock: SupplierStockRecordDAO,
        bulk_create_dtos: list[SupplierStockRecordCreateDTO],
    ) -> None:
        dao_stock.bulk_create(bulk_create_dtos)
        initial_count = SupplierStockRecord.objects.count()

        results = dao_stock.bulk_create(bulk_create_dtos)

        assert SupplierStockRecord.objects.count() == initial_count
        assert len(results) == len(bulk_create_dtos)

    def test_bulk_update_returns_updated_count(
        self,
        dao_stock: SupplierStockRecordDAO,
        bulk_create_dtos: list[SupplierStockRecordCreateDTO],
    ) -> None:
        created = dao_stock.bulk_create(bulk_create_dtos)

        update_dtos = [
            SupplierStockRecordUpdateDTO(
                id=r.id,
                price=r.price + Decimal("10.00"),
                currency_code=r.currency_code,
                num_in_stock=r.num_in_stock + 1,
                is_active=r.is_active,
                last_supplier_updated_at=r.last_supplier_updated_at,
            )
            for r in created
        ]

        updated_count = dao_stock.bulk_update(update_dtos)

        assert updated_count == len(update_dtos)

        for r in created:
            r.refresh_from_db()
            idx = [c.id for c in created].index(r.id)
            assert r.price == update_dtos[idx].price

    def test_get_by_supplier_returns_dto_list(
        self,
        dao_stock: SupplierStockRecordDAO,
        supplier: Supplier,
        stock_create_dto: SupplierStockRecordCreateDTO,
    ) -> None:
        dao_stock.bulk_create([stock_create_dto])

        results = dao_stock.get_by_supplier(supplier.id)

        assert isinstance(results, list)
        assert all(isinstance(r, SupplierStockRecordDTO) for r in results)
        assert len(results) == 1
        assert results[0].supplier_sku == stock_create_dto.supplier_sku

    def test_currency_code_mapping_in_dto(
        self,
        dao_stock: SupplierStockRecordDAO,
        supplier: Supplier,
        product: Product,
        currency_eur: Currency,
    ) -> None:
        dto = SupplierStockRecordCreateDTO(
            supplier_id=supplier.id,
            product_id=product.id,
            supplier_sku="EUR-SKU",
            price=Decimal("99.99"),
            currency_code=currency_eur.code,
            num_in_stock=10,
            is_active=True,
        )

        results = dao_stock.bulk_create([dto])

        assert results[0].currency_code == currency_eur.code
        record = SupplierStockRecord.objects.get(id=results[0].id)
        assert record.currency.code == currency_eur.code


@pytest.mark.django_db
class TestSupplierStockHistoryDAO:
    """Тесты для SupplierStockHistoryDAO."""

    def test_bulk_create_history_records(
        self,
        dao_stock: SupplierStockRecordDAO,
        dao_history: SupplierStockHistoryDAO,
        supplier: Supplier,
        product: Product,
        currency_usd: Currency,
    ) -> None:
        created_records = dao_stock.bulk_create([
            SupplierStockRecordCreateDTO(
                supplier_id=supplier.id,
                product_id=product.id,
                supplier_sku="HIST-SKU",
                price=Decimal("100.00"),
                currency_code=currency_usd.code,
                num_in_stock=50,
                is_active=True,
            )
        ])

        history_dtos = [
            SupplierStockHistoryCreateDTO(
                stock_record_id=rec.id,
                sync_id=None,
                snapshot_supplier_name=supplier.name,
                snapshot_product_title=product.title,
                snapshot_product_upc=product.upc or "",
                snapshot_supplier_sku=rec.supplier_sku,
                snapshot_currency_code=currency_usd.code,
                price_before=None,
                price_after=rec.price,
                num_in_stock_before=None,
                num_in_stock_after=rec.num_in_stock,
                change_type=StockChangeType.CREATED,
            )
            for rec in created_records
        ]

        dao_history.bulk_create(history_dtos)

        assert SupplierStockHistory.objects.count() == 1
        history = SupplierStockHistory.objects.first()
        assert history is not None
        assert history.change_type == StockChangeType.CREATED
        assert history.price_after == Decimal("100.00")


@pytest.mark.django_db
class TestSupplierCatalogSyncDAO:
    """Тесты для SupplierCatalogSyncDAO."""

    def test_create_running_returns_scalar_id(
        self,
        dao_sync: SupplierCatalogSyncDAO,
        supplier: Supplier,
    ) -> None:
        result = dao_sync.create_running(supplier.id)

        assert isinstance(result, int)
        sync = SupplierCatalogSync.objects.get(id=result)
        assert sync.supplier_id == supplier.id
        assert sync.status == SupplierCatalogSync.Status.RUNNING

    def test_mark_success_updates_fields(
        self,
        dao_sync: SupplierCatalogSyncDAO,
        supplier: Supplier,
    ) -> None:
        sync_id = dao_sync.create_running(supplier.id)

        result_dto = CatalogSyncResultDTO(
            sync_id=sync_id,
            total_items=100,
            created_items=10,
            updated_items=25,
            skipped_items=60,
            failed_items=5,
        )

        dao_sync.mark_success(sync_id, result_dto)

        sync = SupplierCatalogSync.objects.get(id=sync_id)
        assert sync.status == SupplierCatalogSync.Status.SUCCESS
        assert sync.finished_at is not None
        assert sync.total_items == 100
        assert sync.created_items == 10

    def test_mark_failed_updates_fields(
        self,
        dao_sync: SupplierCatalogSyncDAO,
        supplier: Supplier,
    ) -> None:
        sync_id = dao_sync.create_running(supplier.id)
        error_msg = "Connection timeout after 30s"

        dao_sync.mark_failed(sync_id, error_msg)

        sync = SupplierCatalogSync.objects.get(id=sync_id)
        assert sync.status == SupplierCatalogSync.Status.FAILED
        assert sync.finished_at is not None
        assert error_msg in sync.error_log

    @pytest.mark.django_db(transaction=True)
    def test_mark_success_is_transactional(
        self,
        dao_sync: SupplierCatalogSyncDAO,
        supplier: Supplier,
        mocker,
    ) -> None:
        sync_id = dao_sync.create_running(supplier.id)

        result_dto = CatalogSyncResultDTO(
            sync_id=sync_id,
            total_items=100,
            created_items=10,
            updated_items=25,
            skipped_items=60,
            failed_items=5,
        )

        mocker.patch(
            "suppliers.service.dao.SupplierCatalogSync.objects.filter.update",
            side_effect=ConnectionError("DB timeout"),
        )

        with pytest.raises(ConnectionError):
            dao_sync.mark_success(sync_id, result_dto)

        sync = SupplierCatalogSync.objects.get(id=sync_id)
        assert sync.status == SupplierCatalogSync.Status.RUNNING
        assert sync.finished_at is None
