"""
tests/conftest.py

Общие фикстуры для всех тестов проекта.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from catalogue.models import Product
from core.models import Currency
from currencies.models import (
    CurrencyRateSource,
    CurrencyRateSourceCredential,
    ExchangeRate,
)
from suppliers.models import (
    Supplier,
    SupplierCredential,
    SupplierStockRecord,
)

# ─── Currency Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def usd(db):
    currency, _ = Currency.objects.get_or_create(
        currency_code="USD",
        defaults={"name": "US Dollar", "currency_type": Currency.CurrencyType.FIAT, "symbol": "$"},
    )
    return currency


@pytest.fixture
def rub(db):
    currency, _ = Currency.objects.get_or_create(
        currency_code="RUB",
        defaults={
            "name": "Russian Ruble",
            "currency_type": Currency.CurrencyType.FIAT,
            "symbol": "₽",
        },
    )
    return currency


@pytest.fixture
def eur(db):
    currency, _ = Currency.objects.get_or_create(
        currency_code="EUR",
        defaults={"name": "Euro", "currency_type": Currency.CurrencyType.FIAT, "symbol": "€"},
    )
    return currency


@pytest.fixture
def btc(db):
    currency, _ = Currency.objects.get_or_create(
        currency_code="BTC",
        defaults={"name": "Bitcoin", "currency_type": Currency.CurrencyType.CRYPTO, "symbol": "₿"},
    )
    return currency


# ─── CurrencyRateSource Fixtures ──────────────────────────────────────────────


@pytest.fixture
def coincap_source(db, usd):
    source = CurrencyRateSource.objects.create(
        name="CoinCap Test",
        source_type=CurrencyRateSource.SourceType.CUSTOM_API,
        base_currency=usd,
        api_url="",
        is_active=True,
        api_extra_config={
            "ids": {
                "USD": "united-states-dollar",
                "RUB": "russian-ruble",
                "BTC": "bitcoin",
            }
        },
    )
    return source


@pytest.fixture
def coincap_source_with_credential(coincap_source):
    CurrencyRateSourceCredential.objects.create(
        source=coincap_source,
        api_key="test-api-key",
        api_secret="test-api-secret",
    )
    return coincap_source


@pytest.fixture
def inactive_source(db, usd):
    return CurrencyRateSource.objects.create(
        name="Inactive Source",
        source_type=CurrencyRateSource.SourceType.CUSTOM_API,
        base_currency=usd,
        is_active=False,
    )


@pytest.fixture
def existing_rate(db, coincap_source, usd, rub):
    now = timezone.now()
    return ExchangeRate.objects.create(
        source=coincap_source,
        from_currency=usd,
        to_currency=rub,
        rate=Decimal("90.0000000000000000000000000"),
        rate_datetime=now,
        updated_at=now,
    )


@pytest.fixture
def rate_datetime():
    return timezone.now()


# ─── Supplier Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def supplier_api(db, rub):
    """Поставщик с методом синхронизации API."""
    return Supplier.objects.create(
        name="Test API Supplier",
        code="test-api-supplier",
        sync_method=Supplier.SyncMethod.API,
        api_url="https://api.example.com/products",
        default_currency=rub,
        sync_schedule="0 6 * * *",
        supplier_is_active=True,
        priority=100,
    )


@pytest.fixture
def supplier_manual(db, rub):
    """Поставщик с ручной синхронизацией."""
    return Supplier.objects.create(
        name="Test Manual Supplier",
        code="test-manual-supplier",
        sync_method=Supplier.SyncMethod.MANUAL,
        default_currency=rub,
        sync_schedule="0 6 * * *",
        supplier_is_active=True,
        priority=100,
    )


@pytest.fixture
def supplier_ftp(db, rub):
    """Поставщик с методом синхронизации FTP."""
    return Supplier.objects.create(
        name="Test FTP Supplier",
        code="test-ftp-supplier",
        sync_method=Supplier.SyncMethod.FTP,
        default_currency=rub,
        sync_schedule="0 3 * * *",
        supplier_is_active=True,
        priority=50,
    )


@pytest.fixture
def supplier_inactive(db, rub):
    """Неактивный поставщик."""
    return Supplier.objects.create(
        name="Test Inactive Supplier",
        code="test-inactive-supplier",
        sync_method=Supplier.SyncMethod.MANUAL,
        default_currency=rub,
        supplier_is_active=False,
        priority=100,
    )


@pytest.fixture
def supplier_credential(supplier_api):
    """Учётные данные поставщика."""
    return SupplierCredential.objects.create(
        supplier=supplier_api,
        api_key="test-api-key-12345",
        api_secret="test-api-secret-67890",
    )


@pytest.fixture
def product_test(db):
    """Тестовый товар."""
    return Product.objects.create(
        title="Test Product",
        upc="123456789012",
    )


@pytest.fixture
def product_test_2(db):
    """Второй тестовый товар."""
    return Product.objects.create(
        title="Test Product 2",
        upc="123456789013",
    )


@pytest.fixture
def stock_record(supplier_api, product_test, rub):
    """Запись остатка у поставщика."""
    return SupplierStockRecord.objects.create(
        supplier=supplier_api,
        product=product_test,
        supplier_sku="ART-001",
        price=Decimal("999.99"),
        currency=rub,
        num_in_stock=100,
        num_allocated=0,
        is_active=True,
    )


@pytest.fixture
def stock_record_list(supplier_api, product_test, product_test_2, rub):
    """Список записей остатков."""
    return [
        SupplierStockRecord.objects.create(
            supplier=supplier_api,
            product=product_test,
            supplier_sku="ART-001",
            price=Decimal("999.99"),
            currency=rub,
            num_in_stock=100,
            is_active=True,
        ),
        SupplierStockRecord.objects.create(
            supplier=supplier_api,
            product=product_test_2,
            supplier_sku="ART-002",
            price=Decimal("1499.50"),
            currency=rub,
            num_in_stock=50,
            is_active=True,
        ),
    ]
