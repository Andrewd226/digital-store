"""
tests/suppliers/test_models.py

Тесты для моделей приложения suppliers.
Проверяют целостность данных, свойства, ограничения, типы полей и поведение связей.
Соответствует правилам: TextField, Decimal(50,25), EncryptedTextField, PROTECT/CASCADE.
"""
from __future__ import annotations

import time
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from suppliers.models import (
    Supplier,
    SupplierCatalogSync,
    SupplierCredential,
    SupplierStockHistory,
    SupplierStockRecord,
)


# ─── Supplier Tests ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSupplier:
    """Тесты модели поставщика."""

    def test_str_representation_active(self, supplier_api):
        assert f"{supplier_api.name} (Активен)" == str(supplier_api)

    def test_str_representation_inactive(self, supplier_api):
        supplier_api.supplier_is_active = False
        supplier_api.save()
        assert f"{supplier_api.name} (Отключён)" == str(supplier_api)

    def test_sync_method_choices(self):
        assert Supplier.SyncMethod.API == "api"
        assert Supplier.SyncMethod.MANUAL == "manual"
        assert Supplier.SyncMethod.FTP == "ftp"

    def test_default_values(self, supplier_api):
        assert supplier_api.priority == 100
        assert supplier_api.supplier_is_active is True
        assert supplier_api.api_extra_config == {}
        assert supplier_api.sync_schedule == "0 6 * * *"


# ─── SupplierCredential Tests ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestSupplierCredential:
    """Тесты учетных данных (шифрование + уникальность)."""

    def test_str_representation(self, supplier_api):
        cred = SupplierCredential.objects.create(supplier=supplier_api, api_key="key")
        assert str(cred) == f"Credentials for {supplier_api.name}"

    def test_encrypted_fields_transparency(self, supplier_api):
        """ORM прозрачно шифрует при записи и расшифровывает при чтении."""
        plain_secret = "super_secret_value_123"
        cred = SupplierCredential.objects.create(
            supplier=supplier_api, api_key="key", api_secret=plain_secret
        )
        assert cred.api_secret == plain_secret

        # Проверка на уровне БД: в таблице данные не должны совпадать с открытым текстом
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT api_secret FROM suppliers_suppliercredential WHERE id = %s",
                [cred.id],
            )
            db_value = cursor.fetchone()[0]
            assert db_value != plain_secret

    def test_one_to_one_constraint(self, supplier_api):
        SupplierCredential.objects.create(
            supplier=supplier_api, 
            api_key="key1", 
            api_secret="secret1"
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                SupplierCredential.objects.create(
                    supplier=supplier_api, 
                    api_key="key2", 
                    api_secret="secret2"
                )

# ─── SupplierStockRecord Tests ────────────────────────────────────────────────


@pytest.mark.django_db
class TestSupplierStockRecord:
    """Тесты остатков и цен поставщиков."""

    def test_str_representation(self, stock_record):
        expected = f"{stock_record.supplier.name} -> {stock_record.product.title} ({stock_record.num_in_stock} шт.)"
        assert str(stock_record) == expected

    def test_num_available_property(self, stock_record):
        stock_record.num_in_stock = 10
        stock_record.num_allocated = 4
        assert stock_record.num_available == 6

    def test_num_available_floor_at_zero(self, stock_record):
        stock_record.num_in_stock = 2
        stock_record.num_allocated = 5
        assert stock_record.num_available == 0  # max(0, ...)

    def test_is_available_property_true(self, stock_record):
        stock_record.is_active = True
        stock_record.num_in_stock = 5
        stock_record.num_allocated = 2
        assert stock_record.is_available is True

    def test_is_available_property_false_inactive(self, stock_record):
        stock_record.is_active = False
        assert stock_record.is_available is False

    def test_is_available_property_false_allocated(self, stock_record):
        stock_record.is_active = True
        stock_record.num_in_stock = 0
        stock_record.num_allocated = 0
        assert stock_record.is_available is False

    def test_price_precision_50_25(self, supplier_api, product_test, rub):
        high_precision = Decimal("9999999999999999999999999.9999999999999999999999999")
        record = SupplierStockRecord.objects.create(
            supplier=supplier_api, product=product_test,
            supplier_sku="HIGH-PREC", price=high_precision, currency=rub, num_in_stock=1
        )
        assert record.price == high_precision

    def test_negative_price_validation(self, supplier_api, product_test, rub):
        with pytest.raises(ValidationError):
            record = SupplierStockRecord(
                supplier=supplier_api, product=product_test,
                supplier_sku="NEG", price=Decimal("-10.00"), currency=rub, num_in_stock=0
            )
            record.full_clean()

    def test_unique_supplier_product_constraint(self, supplier_api, product_test, rub):
        SupplierStockRecord.objects.create(
            supplier=supplier_api, product=product_test,
            supplier_sku="SKU1", price=Decimal("100"), currency=rub, num_in_stock=1
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                SupplierStockRecord.objects.create(
                    supplier=supplier_api, product=product_test,
                    supplier_sku="SKU2", price=Decimal("200"), currency=rub, num_in_stock=1
                )

    def test_protect_on_delete_product(self, stock_record, product_test):
        """Удаление товара запрещено, пока есть запись остатка."""
        with pytest.raises(ProtectedError):
            product_test.delete()

    def test_cascade_on_delete_supplier(self, stock_record, supplier_api):
        """Удаление поставщика каскадно удаляет его остатки."""
        supplier_api.delete()
        assert SupplierStockRecord.objects.filter(id=stock_record.id).count() == 0


# ─── SupplierStockHistory Tests ───────────────────────────────────────────────


@pytest.mark.django_db
class TestSupplierStockHistory:
    """Тесты append-only истории изменений."""

    def test_str_representation(self, stock_record):
        history = SupplierStockHistory.objects.create(
            stock_record=stock_record, sync=None,
            snapshot_supplier_name="Test", snapshot_product_title="Test",
            snapshot_product_upc="", snapshot_supplier_sku="SKU",
            snapshot_currency_code="RUB",
            price_before=Decimal("100.00"), price_after=Decimal("150.50"),
            num_in_stock_before=10, num_in_stock_after=15,
            change_type=SupplierStockHistory.ChangeType.PRICE_CHANGED,
        )
        assert "SKU: 100.00 -> 150.50" in str(history)

    def test_price_delta_created(self, stock_record):
        history = SupplierStockHistory.objects.create(
            stock_record=stock_record, sync=None,
            snapshot_supplier_name="T", snapshot_product_title="T",
            snapshot_product_upc="", snapshot_supplier_sku="SKU",
            snapshot_currency_code="RUB",
            price_before=None, price_after=Decimal("99.99"),
            num_in_stock_before=None, num_in_stock_after=1,
            change_type=SupplierStockHistory.ChangeType.CREATED,
        )
        assert history.price_delta == Decimal("99.99")

    def test_price_delta_updated(self, stock_record):
        history = SupplierStockHistory.objects.create(
            stock_record=stock_record, sync=None,
            snapshot_supplier_name="T", snapshot_product_title="T",
            snapshot_product_upc="", snapshot_supplier_sku="SKU",
            snapshot_currency_code="RUB",
            price_before=Decimal("100.00"), price_after=Decimal("80.00"),
            num_in_stock_before=10, num_in_stock_after=5,
            change_type=SupplierStockHistory.ChangeType.BOTH_CHANGED,
        )
        assert history.price_delta == Decimal("-20.00")

    def test_price_delta_pct_normal(self, stock_record):
        history = SupplierStockHistory.objects.create(
            stock_record=stock_record, sync=None,
            snapshot_supplier_name="T", snapshot_product_title="T",
            snapshot_product_upc="", snapshot_supplier_sku="SKU",
            snapshot_currency_code="RUB",
            price_before=Decimal("100.00"), price_after=Decimal("125.50"),
            num_in_stock_before=10, num_in_stock_after=10,
            change_type=SupplierStockHistory.ChangeType.PRICE_CHANGED,
        )
        # (25.50 / 100.00) * 100 = 25.50
        assert history.price_delta_pct == Decimal("25.50")

    def test_price_delta_pct_zero_division_guard(self, stock_record):
        history = SupplierStockHistory.objects.create(
            stock_record=stock_record, sync=None,
            snapshot_supplier_name="T", snapshot_product_title="T",
            snapshot_product_upc="", snapshot_supplier_sku="SKU",
            snapshot_currency_code="RUB",
            price_before=Decimal("0.00"), price_after=Decimal("10.00"),
            num_in_stock_before=10, num_in_stock_after=10,
            change_type=SupplierStockHistory.ChangeType.PRICE_CHANGED,
        )
        assert history.price_delta_pct == Decimal("0.00")

    def test_on_delete_set_null_sync(self, stock_record, supplier_api):
        sync = SupplierCatalogSync.objects.create(
            supplier=supplier_api, status=SupplierCatalogSync.Status.SUCCESS
        )
        history = SupplierStockHistory.objects.create(
            stock_record=stock_record, sync=sync,
            snapshot_supplier_name="T", snapshot_product_title="T",
            snapshot_product_upc="", snapshot_supplier_sku="SKU",
            snapshot_currency_code="RUB",
            price_before=None, price_after=Decimal("50"),
            num_in_stock_before=None, num_in_stock_after=5,
            change_type=SupplierStockHistory.ChangeType.CREATED,
        )
        sync.delete()
        history.refresh_from_db()
        assert history.sync is None


# ─── SupplierCatalogSync Tests ────────────────────────────────────────────────


@pytest.mark.django_db
class TestSupplierCatalogSync:
    """Тесты логов синхронизации."""

    def test_str_representation(self, supplier_api):
        now = timezone.now()
        sync = SupplierCatalogSync.objects.create(
            supplier=supplier_api, status=SupplierCatalogSync.Status.RUNNING, started_at=now
        )
        assert supplier_api.name in str(sync)
        assert "RUNNING" in str(sync)

    def test_duration_seconds_property(self, supplier_api):
        started = timezone.now()
        time.sleep(0.05)
        finished = timezone.now()
        sync = SupplierCatalogSync.objects.create(
            supplier=supplier_api, status=SupplierCatalogSync.Status.SUCCESS,
            started_at=started, finished_at=finished
        )
        assert sync.duration_seconds >= 0

    def test_duration_seconds_null_if_not_finished(self, supplier_api):
        sync = SupplierCatalogSync.objects.create(
            supplier=supplier_api, status=SupplierCatalogSync.Status.RUNNING
        )
        assert sync.duration_seconds is None

    def test_default_status_and_triggered(self, supplier_api):
        sync = SupplierCatalogSync.objects.create(supplier=supplier_api)
        assert sync.status == SupplierCatalogSync.Status.PENDING
        assert sync.triggered_by == "celery"
        assert sync.task_id == ""
        assert sync.error_log == ""
