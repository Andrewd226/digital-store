"""
tests/conftest.py

Общие фикстуры для тестов currencies.
"""

from decimal import Decimal
import pytest
from django.utils import timezone

from core.models import Currency
from currencies.models import (
    CurrencyRateSource,
    CurrencyRateSourceCredential,
    ExchangeRate,
)


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
