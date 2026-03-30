"""
tests/suppliers/test_dao.py

Тесты для DAO (Data Access Object) модуля suppliers.
"""

from decimal import Decimal

from suppliers.models import Supplier, SupplierStockRecord
from suppliers.service.dao import (
    CurrencyDAO,
    ProductDAO,
    SupplierCatalogSyncDAO,
    SupplierDAO,
    SupplierStockHistoryDAO,
    SupplierStockRecordDAO,
)

# ─── SupplierDAO Tests ────────────────────────────────────────────────────────


class TestSupplierDAO:
    """Тесты для SupplierDAO."""

    def test_get_by_id(self, supplier_api):
        """Получение поставщика по ID."""
        supplier = SupplierDAO.get_by_id(supplier_api.id)
        assert supplier == supplier_api

    def test_get_by_id_not_found(self):
        """Получение несуществующего поставщика."""
        supplier = SupplierDAO.get_by_id(99999)
        assert supplier is None

    def test_get_by_code(self, supplier_api):
        """Получение поставщика по коду."""
        supplier = SupplierDAO.get_by_code("test-api-supplier")
        assert supplier == supplier_api

    def test_get_active_suppliers(self, supplier_api, supplier_manual, supplier_inactive):
        """Получение активных поставщиков."""
        active = SupplierDAO.get_active_suppliers()
        assert active.count() == 2
        assert supplier_api in active
        assert supplier_manual in active
        assert supplier_inactive not in active

    def test_get_active_by_sync_method(self, supplier_api, supplier_ftp):
        """Получение поставщиков по методу синхронизации."""
        api_suppliers = SupplierDAO.get_active_by_sync_method(Supplier.SyncMethod.API)
        assert api_suppliers.count() == 1
        assert supplier_api in api_suppliers

    def test_get_credential(self, supplier_credential):
        """Получение учётных данных."""
        credential = SupplierDAO.get_credential(supplier_credential.supplier)
        assert credential == supplier_credential

    def test_get_credential_not_found(self, supplier_manual):
        """Получение несуществующих учётных данных."""
        credential = SupplierDAO.get_credential(supplier_manual)
        assert credential is None


# ─── SupplierStockRecordDAO Tests ─────────────────────────────────────────────


class TestSupplierStockRecordDAO:
    """Тесты для SupplierStockRecordDAO."""

    def test_get_by_supplier_product(self, stock_record):
        """Получение записи по поставщику и товару."""
        record = SupplierStockRecordDAO.get_by_supplier_product(
            supplier=stock_record.supplier,
            product=stock_record.product,
        )
        assert record == stock_record

    def test_get_by_supplier_product_not_found(self, supplier_api, product_test):
        """Получение несуществующей записи."""
        record = SupplierStockRecordDAO.get_by_supplier_product(
            supplier=supplier_api,
            product=product_test,
        )
        assert record is None

    def test_get_or_create_new(self, supplier_api, product_test, rub):
        """Создание новой записи через get_or_create."""
        record, created = SupplierStockRecordDAO.get_or_create(
            supplier=supplier_api,
            product=product_test,
            defaults={
                "supplier_sku": "ART-NEW",
                "price": Decimal("999.99"),
                "currency": rub,
                "num_in_stock": 100,
                "is_active": True,
            },
        )
        assert created is True
        assert record.supplier_sku == "ART-NEW"

    def test_get_or_create_existing(self, stock_record):
        """Получение существующей записи через get_or_create."""
        record, created = SupplierStockRecordDAO.get_or_create(
            supplier=stock_record.supplier,
            product=stock_record.product,
            defaults={"supplier_sku": "ART-NEW", "price": Decimal("500.00")},
        )
        assert created is False
        assert record == stock_record

    def test_update(self, stock_record, rub):
        """Обновление записи остатка."""
        updated = SupplierStockRecordDAO.update(
            stock_record=stock_record,
            price=Decimal("1999.99"),
            supplier_sku="ART-UPDATED",
            num_in_stock=200,
            currency=rub,
        )
        assert updated.price == Decimal("1999.99")
        assert updated.supplier_sku == "ART-UPDATED"
        assert updated.num_in_stock == 200

    def test_get_active_by_supplier(self, stock_record, supplier_api, product_test_2, rub):
        """Получение активных записей поставщика."""
        SupplierStockRecord.objects.create(
            supplier=supplier_api,
            product=product_test_2,
            supplier_sku="ART-002",
            price=Decimal("500.00"),
            currency=rub,
            num_in_stock=50,
            is_active=False,
        )
        active = SupplierStockRecordDAO.get_active_by_supplier(supplier_api)
        assert active.count() == 1

    def test_deactivate_missing(self, supplier_api, product_test, product_test_2, rub):
        """Деактивация отсутствующих записей."""
        SupplierStockRecord.objects.create(
            supplier=supplier_api,
            product=product_test,
            supplier_sku="ART-001",
            price=Decimal("999.99"),
            currency=rub,
            num_in_stock=100,
            is_active=True,
        )
        SupplierStockRecord.objects.create(
            supplier=supplier_api,
            product=product_test_2,
            supplier_sku="ART-002",
            price=Decimal("500.00"),
            currency=rub,
            num_in_stock=50,
            is_active=True,
        )
        deactivated = SupplierStockRecordDAO.deactivate_missing(
            supplier=supplier_api,
            active_skus=["ART-001"],
        )
        assert deactivated == 1


# ─── SupplierStockHistoryDAO Tests ────────────────────────────────────────────


class TestSupplierStockHistoryDAO:
    """Тесты для SupplierStockHistoryDAO."""

    def test_create(self, stock_record, supplier_api):
        """Создание записи истории."""
        history = SupplierStockHistoryDAO.create(
            stock_record=stock_record,
            sync=None,
            snapshot_supplier_name=supplier_api.name,
            snapshot_product_title=stock_record.product.title,
            snapshot_product_upc=stock_record.product.upc or "",
            snapshot_supplier_sku=stock_record.supplier_sku,
            snapshot_currency_code=stock_record.currency.currency_code,
            price_before=Decimal("500.00"),
            price_after=Decimal("999.99"),
            num_in_stock_before=50,
            num_in_stock_after=100,
            change_type="price_changed",
        )
        assert history.price_before == Decimal("500.00")
        assert history.price_after == Decimal("999.99")

    def test_get_by_stock_record(self, stock_record):
        """Получение истории по записи остатка."""
        SupplierStockHistoryDAO.create(
            stock_record=stock_record,
            sync=None,
            snapshot_supplier_name=stock_record.supplier.name,
            snapshot_product_title=stock_record.product.title,
            snapshot_product_upc=stock_record.product.upc or "",
            snapshot_supplier_sku=stock_record.supplier_sku,
            snapshot_currency_code=stock_record.currency.currency_code,
            price_before=None,
            price_after=Decimal("999.99"),
            num_in_stock_before=None,
            num_in_stock_after=100,
            change_type="created",
        )
        history = SupplierStockHistoryDAO.get_by_stock_record(stock_record)
        assert history.count() == 1

    def test_get_by_supplier(self, supplier_api, stock_record):
        """Получение истории по поставщику."""
        SupplierStockHistoryDAO.create(
            stock_record=stock_record,
            sync=None,
            snapshot_supplier_name=supplier_api.name,
            snapshot_product_title=stock_record.product.title,
            snapshot_product_upc=stock_record.product.upc or "",
            snapshot_supplier_sku=stock_record.supplier_sku,
            snapshot_currency_code=stock_record.currency.currency_code,
            price_before=None,
            price_after=Decimal("999.99"),
            num_in_stock_before=None,
            num_in_stock_after=100,
            change_type="created",
        )
        history = SupplierStockHistoryDAO.get_by_supplier(supplier_api)
        assert history.count() == 1


# ─── SupplierCatalogSyncDAO Tests ─────────────────────────────────────────────


class TestSupplierCatalogSyncDAO:
    """Тесты для SupplierCatalogSyncDAO."""

    def test_create_running(self, supplier_api):
        """Создание записи синхронизации."""
        sync = SupplierCatalogSyncDAO.create_running(
            supplier=supplier_api,
            triggered_by="pytest",
        )
        assert sync.supplier == supplier_api
        assert sync.status == "running"
        assert sync.triggered_by == "pytest"

    def test_complete(self, supplier_api):
        """Завершение синхронизации."""
        sync = SupplierCatalogSyncDAO.create_running(supplier=supplier_api)
        completed = SupplierCatalogSyncDAO.complete(
            sync_record=sync,
            status="success",
            total_items=10,
            created_items=5,
            updated_items=3,
            skipped_items=1,
            failed_items=1,
            error_log="",
        )
        assert completed.status == "success"
        assert completed.total_items == 10
        assert completed.finished_at is not None

    def test_get_by_supplier(self, supplier_api):
        """Получение записей синхронизации по поставщику."""
        SupplierCatalogSyncDAO.create_running(supplier=supplier_api)
        SupplierCatalogSyncDAO.create_running(supplier=supplier_api)
        syncs = SupplierCatalogSyncDAO.get_by_supplier(supplier_api)
        assert syncs.count() == 2

    def test_get_last_sync(self, supplier_api):
        """Получение последней синхронизации."""
        sync1 = SupplierCatalogSyncDAO.create_running(supplier=supplier_api)
        import time

        time.sleep(0.01)
        sync2 = SupplierCatalogSyncDAO.create_running(supplier=supplier_api)
        last = SupplierCatalogSyncDAO.get_last_sync(supplier_api)
        assert last == sync2


# ─── ProductDAO Tests ─────────────────────────────────────────────────────────


class TestProductDAO:
    """Тесты для ProductDAO."""

    def test_get_by_upc(self, product_test):
        """Получение товара по UPC."""
        product = ProductDAO.get_by_upc("123456789012")
        assert product == product_test

    def test_get_by_upc_not_found(self):
        """Получение несуществующего товара."""
        product = ProductDAO.get_by_upc("NONEXISTENT123")
        assert product is None

    def test_get_by_upc_list(self, product_test, product_test_2):
        """Получение товаров по списку UPC."""
        products = ProductDAO.get_by_upc_list(["123456789012", "123456789013"])
        assert products.count() == 2


# ─── CurrencyDAO Tests ────────────────────────────────────────────────────────


class TestCurrencyDAO:
    """Тесты для CurrencyDAO."""

    def test_get_by_code(self, rub):
        """Получение валюты по коду."""
        currency = CurrencyDAO.get_by_code("RUB")
        assert currency == rub

    def test_get_by_code_not_found(self):
        """Получение несуществующей валюты."""
        currency = CurrencyDAO.get_by_code("XXX")
        assert currency is None

    def test_get_active(self, rub, usd):
        """Получение всех валют."""
        currencies = CurrencyDAO.get_active()
        assert rub in currencies
        assert usd in currencies
