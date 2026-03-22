"""
currencies/tests/test_models.py

Тесты для моделей currencies.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from currencies.models import (
    CurrencyRateSync,
    ExchangeRate,
    ExchangeRateHistory,
)


@pytest.mark.django_db
class TestCurrencyRateSourceStr:

    def test_str_active(self, coincap_source):
        assert "CoinCap Test" in str(coincap_source)
        assert "USD" in str(coincap_source)
        assert "[отключён]" not in str(coincap_source)

    def test_str_inactive(self, inactive_source):
        assert "[отключён]" in str(inactive_source)


@pytest.mark.django_db
class TestExchangeRateStr:

    def test_str(self, existing_rate):
        s = str(existing_rate)
        assert "USD" in s
        assert "RUB" in s
        assert "CoinCap Test" in s


@pytest.mark.django_db
class TestExchangeRateHistory:

    def test_delta(self, existing_rate):
        history = ExchangeRateHistory(
            rate_record=existing_rate,
            snapshot_source_name="test",
            snapshot_from_currency="USD",
            snapshot_to_currency="RUB",
            rate=Decimal("95"),
            rate_datetime=timezone.now(),
            previous_rate=Decimal("90"),
        )
        assert history.delta == Decimal("5")

    def test_delta_none_when_no_previous(self, existing_rate):
        history = ExchangeRateHistory(
            rate_record=existing_rate,
            snapshot_source_name="test",
            snapshot_from_currency="USD",
            snapshot_to_currency="RUB",
            rate=Decimal("95"),
            rate_datetime=timezone.now(),
            previous_rate=None,
        )
        assert history.delta is None

    def test_delta_pct(self, existing_rate):
        history = ExchangeRateHistory(
            rate_record=existing_rate,
            snapshot_source_name="test",
            snapshot_from_currency="USD",
            snapshot_to_currency="RUB",
            rate=Decimal("99"),
            rate_datetime=timezone.now(),
            previous_rate=Decimal("90"),
        )
        assert history.delta_pct == pytest.approx(10.0, rel=1e-3)

    def test_delta_pct_none_when_no_previous(self, existing_rate):
        history = ExchangeRateHistory(
            rate_record=existing_rate,
            snapshot_source_name="test",
            snapshot_from_currency="USD",
            snapshot_to_currency="RUB",
            rate=Decimal("95"),
            rate_datetime=timezone.now(),
            previous_rate=None,
        )
        assert history.delta_pct is None

    def test_str(self, existing_rate):
        history = ExchangeRateHistory(
            rate_record=existing_rate,
            snapshot_source_name="CoinCap",
            snapshot_from_currency="USD",
            snapshot_to_currency="RUB",
            rate=Decimal("90"),
            rate_datetime=timezone.now(),
        )
        s = str(history)
        assert "USD/RUB" in s
        assert "CoinCap" in s


@pytest.mark.django_db
class TestCurrencyRateSync:

    def test_duration_seconds(self, coincap_source):
        from datetime import timedelta
        now = timezone.now()
        sync = CurrencyRateSync(
            source=coincap_source,
            status=CurrencyRateSync.Status.SUCCESS,
            started_at=now,
            finished_at=now + timedelta(seconds=42),
        )
        assert sync.duration_seconds == pytest.approx(42.0)

    def test_duration_seconds_none_when_not_finished(self, coincap_source):
        sync = CurrencyRateSync(
            source=coincap_source,
            status=CurrencyRateSync.Status.RUNNING,
            started_at=timezone.now(),
            finished_at=None,
        )
        assert sync.duration_seconds is None

    def test_str(self, coincap_source):
        sync = CurrencyRateSync.objects.create(
            source=coincap_source,
            status=CurrencyRateSync.Status.SUCCESS,
        )
        s = str(sync)
        assert "CoinCap Test" in s
        assert "Успешно" in s
