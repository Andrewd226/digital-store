"""
tests/suppliers/test_models.py

Тесты для моделей модуля suppliers.
"""

from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from suppliers.models import (
    Supplier,
    SupplierCredential,
    SupplierCatalogSync,
    SupplierStockRecord,
    SupplierStockHistory,
)


# ─── Supplier Model Tests ─────────────────────────────────────────────────────


class TestSupplierModel:
    """Тесты для модели Supplier."""

    def test_create_supplier(self, rub):
        """Создание поставщика."""
        supplier = Supplier.objects.create(
            name="Test Supplier",
            code="test-supplier",
            sync_method=Supplier.SyncMethod.API,
            default_currency=rub,
        )
        assert supplier.name == "Test Supplier"
        assert supplier.code == "test-supplier"
        assert supplier.supplier_is_active is True
        assert supplier.priority == 100

    def test_unique_code(self, rub, supplier_api):
        """Код поставщика уникален."""
        with pytest.raises(IntegrityError):
            Supplier.objects.create(
                name="Duplicate Supplier",
                code="test-api-supplier",
                sync_method=Supplier.SyncMethod.MANUAL,
                default_currency=rub,
            )

    def test_str_representation(self, supplier_api):
        """Строковое представление активного поставщика."""
        assert "Test API Supplier" in str(supplier_api)
        assert "REST API" in str(supplier_api)

    def test_str_representation_inactive(self, supplier_inactive):
        """Строковое представление неактивного поставщика."""
        assert "[отключён]" in str(supplier_inactive)

    def test_default_values(self, rub):
        """Значения по умолчанию."""
        supplier = Supplier.objects.create(
            name="Default Supplier",
            code="default-supplier",
            default_currency=rub,
        )
        assert supplier.sync_method == Supplier.SyncMethod.MANUAL
        assert supplier.sync_schedule == "0 6 * * *"
        assert supplier.supplier_is_active is True
        assert supplier.priority == 100


# ─── SupplierCredential Model Tests ───────────────────────────────────────────


class TestSupplierCredentialModel:
    """Тесты для модели SupplierCredential."""

    def test_create_credential(self, supplier_api):
        """Создание учётных данных."""
        credential = SupplierCredential.objects.create(
            supplier=supplier_api,
            api_key="test-key",
            api_secret="test-secret",
        )
        assert credential.supplier == supplier_api
        assert credential.api_key == "test-key"

    def test_one_to_one_relation(self, supplier_api, supplier_credential):
        """Отношение OneToOne с поставщиком."""
        with pytest.raises(IntegrityError):
            SupplierCredential.objects.create(
                supplier=supplier_api,
                api_key="duplicate-key",
            )


# ─── SupplierStockRecord Model Tests ──────────────────────────────────────────


class TestSupplierStockRecordModel:
    """Тесты для модели SupplierStockRecord."""

    def test_create_stock_record(self, supplier_api, product_test, rub):
        """Создание записи остатка."""
        record = SupplierStockRecord.objects.create(
            supplier=supplier_api,
            product=product_test,
            supplier_sku="ART-001",
            price=Decimal("999.99"),
            currency=rub,
            num_in_stock=100,
        )
        assert record.price == Decimal("999.99")
        assert record.num_in_stock == 100
        assert record.is_active is True

    def test_unique_supplier_product(self, supplier_api, product_test, rub, stock_record):
        """Уникальность пары поставщик-товар."""
        with pytest.raises(IntegrityError):
            SupplierStockRecord.objects.create(
                supplier=supplier_api,
                product=product_test,
                supplier_sku="ART-002",
                price=Decimal("500.00"),
                currency=rub,
                num_in_stock=50,
            )

    def test_num_available_property(self, stock_record):
        """Свойство num_available корректно."""
        assert stock_record.num_available == 100

        stock_record.num_allocated = 30
        stock_record.save()
        assert stock_record.num_available == 70

    def test_is_available_property(self, stock_record):
        """Свойство is_available корректно."""
        assert stock_record.is_available is True

        stock_record.num_in_stock = 0
        stock_record.save()
        assert stock_record.is_available is False

        stock_record.is_active = False
        stock_record.save()
        assert stock_record.is_available is False

    def test_decimal_precision(self, supplier_api, product_test, rub):
        """Точность Decimal для цены."""
        record = SupplierStockRecord.objects.create(
            supplier=supplier_api,
            product=product_test,
            supplier_sku="ART-001",
            price=Decimal("0.0000000000000000000000001"),
            currency=rub,
            num_in_stock=1,
        )
        assert record.price == Decimal("0.0000000000000000000000001")


# ─── SupplierStockHistory Model Tests ─────────────────────────────────────────


class TestSupplierStockHistoryModel:
    """Тесты для модели SupplierStockHistory."""

    def test_create_history_record(self, stock_record):
        """Создание записи истории."""
        history = SupplierStockHistory.objects.create(
            stock_record=stock_record,
            snapshot_supplier_name=stock_record.supplier.name,
            snapshot_product_title=stock_record.product.title,
            snapshot_supplier_sku=stock_record.supplier_sku,
            snapshot_currency_code=stock_record.currency.currency_code,
            price_before=Decimal("500.00"),
            price_after=Decimal("999.99"),
            num_in_stock_before=50,
            num_in_stock_after=100,
            change_type=SupplierStockHistory.ChangeType.BOTH_CHANGED,
        )
        assert history.price_before == Decimal("500.00")
        assert history.price_after == Decimal("999.99")
        assert history.change_type == SupplierStockHistory.ChangeType.BOTH_CHANGED

    def test_price_delta_property(self, stock_record):
        """Свойство price_delta корректно."""
        history = SupplierStockHistory.objects.create(
            stock_record=stock_record,
            snapshot_supplier_name=stock_record.supplier.name,
            snapshot_product_title=stock_record.product.title,
            snapshot_supplier_sku=stock_record.supplier_sku,
            snapshot_currency_code=stock_record.currency.currency_code,
            price_before=Decimal("500.00"),
            price_after=Decimal("999.99"),
            num_in_stock_before=50,
            num_in_stock_after=100,
            change_type=SupplierStockHistory.ChangeType.PRICE_CHANGED,
        )
        assert history.price_delta == Decimal("499.99")

    def test_price_delta_pct_property(self, stock_record):
        """Свойство price_delta_pct корректно."""
        history = SupplierStockHistory.objects.create(
            stock_record=stock_record,
            snapshot_supplier_name=stock_record.supplier.name,
            snapshot_product_title=stock_record.product.title,
            snapshot_supplier_sku=stock_record.supplier_sku,
            snapshot_currency_code=stock_record.currency.currency_code,
            price_before=Decimal("500.00"),
            price_after=Decimal("750.00"),
            num_in_stock_before=50,
            num_in_stock_after=100,
            change_type=SupplierStockHistory.ChangeType.PRICE_CHANGED,
        )
        assert history.price_delta_pct == Decimal("50.00")

    def test_protect_on_delete(self, stock_record):
        """PROTECT предотвращает удаление связанной записи."""
        history = SupplierStockHistory.objects.create(
            stock_record=stock_record,
            snapshot_supplier_name=stock_record.supplier.name,
            snapshot_product_title=stock_record.product.title,
            snapshot_supplier_sku=stock_record.supplier_sku,
            snapshot_currency_code=stock_record.currency.currency_code,
            price_before=None,
            price_after=Decimal("999.99"),
            num_in_stock_before=None,
            num_in_stock_after=100,
            change_type=SupplierStockHistory.ChangeType.CREATED,
        )
        with pytest.raises(IntegrityError):
            stock_record.delete()


# ─── SupplierCatalogSync Model Tests ──────────────────────────────────────────


class TestSupplierCatalogSyncModel:
    """Тесты для модели SupplierCatalogSync."""

    def test_create_sync_record(self, supplier_api):
        """Создание записи синхронизации."""
        sync = SupplierCatalogSync.objects.create(
            supplier=supplier_api,
            status=SupplierCatalogSync.Status.RUNNING,
            triggered_by="pytest",
        )
        assert sync.supplier == supplier_api
        assert sync.status == SupplierCatalogSync.Status.RUNNING
        assert sync.triggered_by == "pytest"

    def test_duration_seconds_property(self, supplier_api):
        """Свойство duration_seconds корректно."""
        now = timezone.now()
        sync = SupplierCatalogSync.objects.create(
            supplier=supplier_api,
            status=SupplierCatalogSync.Status.SUCCESS,
            started_at=now,
            finished_at=now,
        )
        assert sync.duration_seconds == 0

    def test_default_status(self, supplier_api):
        """Статус по умолчанию — PENDING."""
        sync = SupplierCatalogSync.objects.create(
            supplier=supplier_api,
            triggered_by="pytest",
        )
        assert sync.status == SupplierCatalogSync.Status.PENDING
