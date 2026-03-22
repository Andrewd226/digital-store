"""
currencies/tests/conftest.py

Общие фикстуры для тестов currencies.
"""

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
    return Currency.objects.get(currency_code="USD")


@pytest.fixture
def rub(db):
    return Currency.objects.get(currency_code="RUB")


@pytest.fixture
def eur(db):
    return Currency.objects.get(currency_code="EUR")


@pytest.fixture
def btc(db):
    return Currency.objects.get(currency_code="BTC")


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
    return ExchangeRate.objects.create(
        source=coincap_source,
        from_currency=usd,
        to_currency=rub,
        rate="90.000000000000000000",
        rate_datetime=timezone.now(),
        updated_at=timezone.now(),
    )


@pytest.fixture
def rate_datetime():
    return timezone.now()
