"""
currencies/tests/test_dto.py

Тесты для DTO: RateDTO, SyncResultDTO.
"""

from decimal import Decimal

import pytest
from django.utils import timezone
from pydantic import ValidationError

from currencies.dto import RateDTO, SyncResultDTO


class TestRateDTO:

    def test_valid_rate(self, rate_datetime):
        dto = RateDTO(
            from_code="USD",
            to_code="RUB",
            rate=Decimal("90.5"),
            rate_datetime=rate_datetime,
        )
        assert dto.from_code == "USD"
        assert dto.to_code == "RUB"
        assert dto.rate == Decimal("90.5")

    def test_codes_normalized_to_uppercase(self, rate_datetime):
        dto = RateDTO(
            from_code="  usd  ",
            to_code="rub",
            rate=Decimal("90.5"),
            rate_datetime=rate_datetime,
        )
        assert dto.from_code == "USD"
        assert dto.to_code == "RUB"

    def test_rate_zero_raises(self, rate_datetime):
        with pytest.raises(ValidationError, match="больше нуля"):
            RateDTO(
                from_code="USD",
                to_code="RUB",
                rate=Decimal("0"),
                rate_datetime=rate_datetime,
            )

    def test_rate_negative_raises(self, rate_datetime):
        with pytest.raises(ValidationError, match="больше нуля"):
            RateDTO(
                from_code="USD",
                to_code="RUB",
                rate=Decimal("-1"),
                rate_datetime=rate_datetime,
            )

    def test_frozen_immutable(self, rate_datetime):
        dto = RateDTO(
            from_code="USD",
            to_code="RUB",
            rate=Decimal("90.5"),
            rate_datetime=rate_datetime,
        )
        with pytest.raises(Exception):
            dto.rate = Decimal("100")

    def test_missing_fields_raise(self):
        with pytest.raises(ValidationError):
            RateDTO(from_code="USD", to_code="RUB")

    def test_naive_datetime_raises(self):
        from datetime import datetime
        with pytest.raises(ValidationError, match="таймзону"):
            RateDTO(
                from_code="USD",
                to_code="RUB",
                rate=Decimal("90.5"),
                rate_datetime=datetime(2025, 1, 1, 12, 0, 0),  # naive — без tzinfo
            )


class TestSyncResultDTO:

    def test_success(self):
        dto = SyncResultDTO(
            status="success",
            source_id=1,
            source_name="CoinCap",
            rates_updated=42,
        )
        assert dto.status == "success"
        assert dto.rates_updated == 42
        assert dto.error is None

    def test_skipped_defaults(self):
        dto = SyncResultDTO(status="skipped", source_id=99)
        assert dto.rates_updated == 0
        assert dto.source_name is None
        assert dto.error is None

    def test_failed_with_error(self):
        dto = SyncResultDTO(status="failed", source_id=1, error="Connection timeout")
        assert dto.error == "Connection timeout"

    def test_model_dump(self):
        dto = SyncResultDTO(status="success", source_id=1, rates_updated=5)
        data = dto.model_dump()
        assert isinstance(data, dict)
        assert data["status"] == "success"
        assert data["rates_updated"] == 5
