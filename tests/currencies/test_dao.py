"""
tests/currencies/test_dao.py

Тесты для DAO: ExchangeRateDAO, CurrencyRateSyncDAO.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from currencies.dao import CurrencyRateSyncDAO, ExchangeRateDAO
from currencies.dto import RateDTO
from currencies.models import (
    CurrencyRateSync,
    ExchangeRate,
    ExchangeRateHistory,
)


def make_rate_dto(from_code, to_code, rate, dt=None):
    return RateDTO(
        from_code=from_code,
        to_code=to_code,
        rate=Decimal(str(rate)),
        rate_datetime=dt or timezone.now(),
    )


@pytest.mark.django_db
class TestExchangeRateDAOSaveRates:
    def setup_method(self):
        self.dao = ExchangeRateDAO()

    def test_creates_new_rates(self, coincap_source, usd, rub):
        rates = [make_rate_dto("USD", "RUB", "90.5")]
        total = self.dao.save_rates(coincap_source.id, rates)

        assert total == 1
        assert ExchangeRate.objects.filter(source=coincap_source).count() == 1

        rate = ExchangeRate.objects.get(source=coincap_source)
        assert rate.from_currency == usd
        assert rate.to_currency == rub
        assert rate.rate == Decimal("90.5")

    def test_creates_history_for_new_rates(self, coincap_source):
        rates = [make_rate_dto("USD", "RUB", "90.5")]
        self.dao.save_rates(coincap_source.id, rates)

        history = ExchangeRateHistory.objects.filter(
            snapshot_from_currency="USD",
            snapshot_to_currency="RUB",
        )
        assert history.count() == 1
        assert history.first().previous_rate is None

    def test_updates_existing_rates(self, coincap_source, existing_rate):
        new_rate = make_rate_dto("USD", "RUB", "95.0")
        total = self.dao.save_rates(coincap_source.id, [new_rate])

        assert total == 1
        # Запись не создаётся заново — остаётся одна
        assert ExchangeRate.objects.filter(source=coincap_source).count() == 1

        existing_rate.refresh_from_db()
        assert existing_rate.rate == Decimal("95.0")

    def test_update_creates_history_with_previous_rate(self, coincap_source, existing_rate):
        old_rate = existing_rate.rate
        new_rate = make_rate_dto("USD", "RUB", "95.0")
        self.dao.save_rates(coincap_source.id, [new_rate])

        history = (
            ExchangeRateHistory.objects.filter(
                rate_record=existing_rate,
            )
            .order_by("-recorded_at")
            .first()
        )
        assert history.previous_rate == old_rate
        assert history.rate == Decimal("95.0")

    def test_update_sets_updated_at(self, coincap_source, existing_rate):
        old_updated_at = existing_rate.updated_at
        new_rate = make_rate_dto("USD", "RUB", "95.0")
        self.dao.save_rates(coincap_source.id, [new_rate])

        existing_rate.refresh_from_db()
        assert existing_rate.updated_at > old_updated_at

    def test_skips_unknown_currency(self, coincap_source):
        rates = [make_rate_dto("USD", "XYZ", "1.5")]
        total = self.dao.save_rates(coincap_source.id, rates)

        assert total == 0
        assert ExchangeRate.objects.filter(source=coincap_source).count() == 0

    def test_empty_rates_returns_zero(self, coincap_source):
        total = self.dao.save_rates(coincap_source.id, [])
        assert total == 0

    def test_bulk_create_multiple_rates(self, coincap_source, usd, rub, eur):
        rates = [
            make_rate_dto("USD", "RUB", "90.0"),
            make_rate_dto("USD", "EUR", "0.92"),
            make_rate_dto("EUR", "RUB", "97.8"),
        ]
        total = self.dao.save_rates(coincap_source.id, rates)

        assert total == 3
        assert ExchangeRate.objects.filter(source=coincap_source).count() == 3
        assert ExchangeRateHistory.objects.count() == 3

    def test_chunked_save(self, coincap_source):
        """Проверяет что данные сохраняются корректно при размере батча меньше числа записей."""
        original_chunk = ExchangeRateDAO.CHUNK_SIZE
        try:
            ExchangeRateDAO.CHUNK_SIZE = 2

            rates = [
                make_rate_dto("USD", "RUB", "90.0"),
                make_rate_dto("USD", "EUR", "0.92"),
                make_rate_dto("EUR", "RUB", "97.8"),
            ]
            total = self.dao.save_rates(coincap_source.id, rates)
            assert total == 3
        finally:
            ExchangeRateDAO.CHUNK_SIZE = original_chunk

    def test_mixed_create_and_update(self, coincap_source, existing_rate, eur):
        rates = [
            make_rate_dto("USD", "RUB", "95.0"),  # обновление
            make_rate_dto("USD", "EUR", "0.92"),  # создание
        ]
        total = self.dao.save_rates(coincap_source.id, rates)

        assert total == 2
        assert ExchangeRate.objects.filter(source=coincap_source).count() == 2
        assert ExchangeRateHistory.objects.count() == 2


@pytest.mark.django_db
class TestCurrencyRateSyncDAO:
    def setup_method(self):
        self.dao = CurrencyRateSyncDAO()

    def test_create_running(self, coincap_source):
        sync_id = self.dao.create_running(coincap_source.id)

        sync = CurrencyRateSync.objects.get(id=sync_id)
        assert sync.status == CurrencyRateSync.Status.RUNNING
        assert sync.source == coincap_source
        assert sync.finished_at is None

    def test_create_running_inactive_source_raises(self, inactive_source):
        from currencies.models import CurrencyRateSource

        with pytest.raises(CurrencyRateSource.DoesNotExist):
            self.dao.create_running(inactive_source.id)

    def test_mark_success(self, coincap_source):
        sync_id = self.dao.create_running(coincap_source.id)
        self.dao.mark_success(sync_id, rates_updated=42)

        sync = CurrencyRateSync.objects.get(id=sync_id)
        assert sync.status == CurrencyRateSync.Status.SUCCESS
        assert sync.rates_updated == 42
        assert sync.finished_at is not None

    def test_mark_failed(self, coincap_source):
        sync_id = self.dao.create_running(coincap_source.id)
        self.dao.mark_failed(sync_id, error_log="Something went wrong")

        sync = CurrencyRateSync.objects.get(id=sync_id)
        assert sync.status == CurrencyRateSync.Status.FAILED
        assert sync.error_log == "Something went wrong"
        assert sync.finished_at is not None

    def test_get_active_source_ids(self, coincap_source, inactive_source):
        ids = self.dao.get_active_source_ids()

        assert coincap_source.id in ids
        assert inactive_source.id not in ids

    def test_get_active_source_returns_source(self, coincap_source):
        source = self.dao.get_active_source(coincap_source.id)
        assert source is not None
        assert source.id == coincap_source.id

    def test_get_active_source_returns_none_for_inactive(self, inactive_source):
        source = self.dao.get_active_source(inactive_source.id)
        assert source is None

    def test_get_active_source_returns_none_for_missing(self):
        source = self.dao.get_active_source(99999)
        assert source is None
