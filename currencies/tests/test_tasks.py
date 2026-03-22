"""
currencies/tests/test_tasks.py

Тесты для tasks: CoinCapFetcher, sync_currency_rates, sync_all_currency_rates.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from currencies.models import CurrencyRateSync, ExchangeRate
from currencies.tasks import CoinCapFetcher, get_fetcher, sync_all_currency_rates, sync_currency_rates


# ─── Вспомогательные функции ──────────────────────────────────────────────────


def make_coincap_response(items: list[dict]) -> MagicMock:
    """Мок ответа CoinCap API."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": items}
    mock_response.raise_for_status.return_value = None
    return mock_response


# ─── CoinCapFetcher ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCoinCapFetcherFetch:

    def test_fetch_returns_rate_dtos(self, coincap_source_with_credential):
        api_items = [
            {"id": "united-states-dollar", "rateUsd": "1.0"},
            {"id": "russian-ruble", "rateUsd": "0.011"},
            {"id": "bitcoin", "rateUsd": "85000.0"},
        ]
        mock_response = make_coincap_response(api_items)

        with patch("currencies.tasks.requests.get", return_value=mock_response):
            fetcher = CoinCapFetcher(coincap_source_with_credential)
            rates = fetcher.fetch()

        # 3 валюты → 3×2 = 6 кросс-пар
        assert len(rates) == 6
        codes = {(r.from_code, r.to_code) for r in rates}
        assert ("USD", "RUB") in codes
        assert ("RUB", "USD") in codes
        assert ("BTC", "USD") in codes

    def test_fetch_cross_rate_calculation(self, coincap_source_with_credential):
        """USD→RUB = rateUsd(USD) / rateUsd(RUB) = 1.0 / 0.01 = 100."""
        api_items = [
            {"id": "united-states-dollar", "rateUsd": "1.0"},
            {"id": "russian-ruble", "rateUsd": "0.01"},
        ]
        mock_response = make_coincap_response(api_items)

        with patch("currencies.tasks.requests.get", return_value=mock_response):
            fetcher = CoinCapFetcher(coincap_source_with_credential)
            rates = fetcher.fetch()

        usd_rub = next(r for r in rates if r.from_code == "USD" and r.to_code == "RUB")
        assert usd_rub.rate == pytest.approx(Decimal("100"), rel=Decimal("1e-6"))

    def test_fetch_skips_unknown_ids(self, coincap_source_with_credential):
        """Неизвестный coincap_id не попадает в результат."""
        api_items = [
            {"id": "united-states-dollar", "rateUsd": "1.0"},
            {"id": "unknown-coin", "rateUsd": "0.5"},
        ]
        mock_response = make_coincap_response(api_items)

        with patch("currencies.tasks.requests.get", return_value=mock_response):
            fetcher = CoinCapFetcher(coincap_source_with_credential)
            rates = fetcher.fetch()

        # Только 1 валюта распознана — пар нет
        assert rates == []

    def test_fetch_empty_ids_map_returns_empty(self, coincap_source):
        """Если ids_map пустой — возвращает пустой список без HTTP-запроса."""
        coincap_source.api_extra_config = {}
        coincap_source.tracked_currencies.clear()

        with patch("currencies.tasks.requests.get") as mock_get:
            mock_get.return_value = make_coincap_response([])
            fetcher = CoinCapFetcher(coincap_source)
            # Переопределяем _build_ids_map чтобы вернуть пустой словарь
            fetcher._build_ids_map = lambda: {}
            rates = fetcher.fetch()

        assert rates == []

    def test_fetch_invalid_rate_usd_skipped(self, coincap_source_with_credential):
        """Запись с невалидным rateUsd пропускается без падения."""
        api_items = [
            {"id": "united-states-dollar", "rateUsd": "not-a-number"},
            {"id": "russian-ruble", "rateUsd": "0.01"},
        ]
        mock_response = make_coincap_response(api_items)

        with patch("currencies.tasks.requests.get", return_value=mock_response):
            fetcher = CoinCapFetcher(coincap_source_with_credential)
            rates = fetcher.fetch()

        # USD не распознан → пар нет
        assert rates == []

    def test_fetch_rate_datetime_is_timezone_aware(self, coincap_source_with_credential):
        api_items = [
            {"id": "united-states-dollar", "rateUsd": "1.0"},
            {"id": "russian-ruble", "rateUsd": "0.01"},
        ]
        mock_response = make_coincap_response(api_items)

        with patch("currencies.tasks.requests.get", return_value=mock_response):
            fetcher = CoinCapFetcher(coincap_source_with_credential)
            rates = fetcher.fetch()

        for rate in rates:
            assert rate.rate_datetime.tzinfo is not None

    def test_api_key_sent_in_header(self, coincap_source_with_credential):
        api_items = [
            {"id": "united-states-dollar", "rateUsd": "1.0"},
            {"id": "russian-ruble", "rateUsd": "0.01"},
        ]
        mock_response = make_coincap_response(api_items)

        with patch("currencies.tasks.requests.get", return_value=mock_response) as mock_get:
            fetcher = CoinCapFetcher(coincap_source_with_credential)
            fetcher.fetch()

        call_kwargs = mock_get.call_args.kwargs
        assert "headers" in call_kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer test-api-key"


# ─── get_fetcher ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestGetFetcher:

    def test_custom_api_returns_coincap_fetcher(self, coincap_source):
        fetcher = get_fetcher(coincap_source)
        assert isinstance(fetcher, CoinCapFetcher)

    def test_unknown_source_type_raises(self, coincap_source):
        coincap_source.source_type = "cbr"
        with pytest.raises(ValueError, match="Нет fetcher'а"):
            get_fetcher(coincap_source)


# ─── sync_currency_rates ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestSyncCurrencyRates:

    def test_success(self, coincap_source_with_credential):
        api_items = [
            {"id": "united-states-dollar", "rateUsd": "1.0"},
            {"id": "russian-ruble", "rateUsd": "0.011"},
        ]
        mock_response = make_coincap_response(api_items)

        with patch("currencies.tasks.requests.get", return_value=mock_response):
            result = sync_currency_rates(coincap_source_with_credential.id)

        assert result.status == "success"
        assert result.rates_updated == 2
        assert result.error is None

        sync = CurrencyRateSync.objects.get(source=coincap_source_with_credential)
        assert sync.status == CurrencyRateSync.Status.SUCCESS
        assert sync.rates_updated == 2
        assert sync.finished_at is not None

    def test_creates_exchange_rates(self, coincap_source_with_credential, usd, rub):
        api_items = [
            {"id": "united-states-dollar", "rateUsd": "1.0"},
            {"id": "russian-ruble", "rateUsd": "0.011"},
        ]
        mock_response = make_coincap_response(api_items)

        with patch("currencies.tasks.requests.get", return_value=mock_response):
            sync_currency_rates(coincap_source_with_credential.id)

        assert ExchangeRate.objects.filter(source=coincap_source_with_credential).count() == 2

    def test_skipped_for_inactive_source(self, inactive_source):
        result = sync_currency_rates(inactive_source.id)

        assert result.status == "skipped"
        assert result.source_id == inactive_source.id
        assert CurrencyRateSync.objects.count() == 0

    def test_skipped_for_missing_source(self):
        result = sync_currency_rates(99999)

        assert result.status == "skipped"
        assert CurrencyRateSync.objects.count() == 0

    def test_failed_on_http_error(self, coincap_source_with_credential):
        with patch("currencies.tasks.requests.get", side_effect=Exception("Connection refused")):
            result = sync_currency_rates(coincap_source_with_credential.id)

        assert result.status == "failed"
        assert "Connection refused" in result.error

        sync = CurrencyRateSync.objects.get(source=coincap_source_with_credential)
        assert sync.status == CurrencyRateSync.Status.FAILED
        assert "Connection refused" in sync.error_log
        assert sync.finished_at is not None

    def test_failed_sync_log_contains_traceback(self, coincap_source_with_credential):
        with patch("currencies.tasks.requests.get", side_effect=ValueError("bad value")):
            sync_currency_rates(coincap_source_with_credential.id)

        sync = CurrencyRateSync.objects.get(source=coincap_source_with_credential)
        assert "ValueError" in sync.error_log
        assert "Traceback" in sync.error_log


# ─── sync_all_currency_rates ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestSyncAllCurrencyRates:

    def test_dispatches_to_all_active_sources(self, coincap_source_with_credential, inactive_source):
        api_items = [
            {"id": "united-states-dollar", "rateUsd": "1.0"},
            {"id": "russian-ruble", "rateUsd": "0.011"},
        ]
        mock_response = make_coincap_response(api_items)

        with patch("currencies.tasks.requests.get", return_value=mock_response):
            results = sync_all_currency_rates()

        # Только один активный источник
        assert len(results) == 1
        assert results[0].status == "success"

    def test_returns_list_of_sync_result_dtos(self, coincap_source_with_credential):
        api_items = [{"id": "united-states-dollar", "rateUsd": "1.0"}]
        mock_response = make_coincap_response(api_items)

        with patch("currencies.tasks.requests.get", return_value=mock_response):
            results = sync_all_currency_rates()

        from currencies.dto import SyncResultDTO
        assert all(isinstance(r, SyncResultDTO) for r in results)

    def test_empty_when_no_active_sources(self, inactive_source):
        results = sync_all_currency_rates()
        assert results == []
