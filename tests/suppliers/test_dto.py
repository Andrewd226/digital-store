"""
tests/suppliers/test_dto.py

Тесты для DTO (Data Transfer Objects).
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from suppliers.service.dto import (
    SupplierProductDTO,
    SyncConfigDTO,
    SyncResultDTO,
    SyncStatsDTO,
)

# ─── SupplierProductDTO Tests ─────────────────────────────────────────────────


class TestSupplierProductDTO:
    """Тесты для SupplierProductDTO."""

    def test_create_valid(self):
        """Создание валидного DTO."""
        dto = SupplierProductDTO(
            supplier_sku="ART-001",
            price=Decimal("999.99"),
            currency_code="RUB",
            num_in_stock=100,
        )
        assert dto.supplier_sku == "ART-001"
        assert dto.price == Decimal("999.99")
        assert dto.currency_code == "RUB"
        assert dto.num_in_stock == 100

    def test_uppercase_sku(self):
        """Артикул приводится к верхнему регистру."""
        dto = SupplierProductDTO(
            supplier_sku="art-001",
            price=Decimal("100"),
            currency_code="RUB",
            num_in_stock=10,
        )
        assert dto.supplier_sku == "ART-001"

    def test_uppercase_currency(self):
        """Код валюты приводится к верхнему регистру."""
        dto = SupplierProductDTO(
            supplier_sku="ART-001",
            price=Decimal("100"),
            currency_code="rub",
            num_in_stock=10,
        )
        assert dto.currency_code == "RUB"

    def test_invalid_currency_code_pattern(self):
        """Невалидный код валюты (не соответствует паттерну)."""
        with pytest.raises(ValidationError) as exc_info:
            SupplierProductDTO(
                supplier_sku="ART-001",
                price=Decimal("100"),
                currency_code="123",
                num_in_stock=10,
            )
        assert "currency_code" in str(exc_info.value)

    def test_invalid_currency_code_short(self):
        """Невалидный код валюты (короткий)."""
        with pytest.raises(ValidationError) as exc_info:
            SupplierProductDTO(
                supplier_sku="ART-001",
                price=Decimal("100"),
                currency_code="RU",
                num_in_stock=10,
            )
        assert "currency_code" in str(exc_info.value)

    def test_negative_price(self):
        """Отрицательная цена не допускается."""
        with pytest.raises(ValidationError) as exc_info:
            SupplierProductDTO(
                supplier_sku="ART-001",
                price=Decimal("-100"),
                currency_code="RUB",
                num_in_stock=10,
            )
        assert "price" in str(exc_info.value)

    def test_negative_stock(self):
        """Отрицательный остаток не допускается."""
        with pytest.raises(ValidationError) as exc_info:
            SupplierProductDTO(
                supplier_sku="ART-001",
                price=Decimal("100"),
                currency_code="RUB",
                num_in_stock=-10,
            )
        assert "num_in_stock" in str(exc_info.value)

    def test_empty_sku(self):
        """Пустой артикул не допускается."""
        with pytest.raises(ValidationError) as exc_info:
            SupplierProductDTO(
                supplier_sku="",
                price=Decimal("100"),
                currency_code="RUB",
                num_in_stock=10,
            )
        assert "supplier_sku" in str(exc_info.value)

    def test_optional_fields(self):
        """Опциональные поля могут быть None."""
        dto = SupplierProductDTO(
            supplier_sku="ART-001",
            price=Decimal("100"),
            currency_code="RUB",
            num_in_stock=10,
            product_upc=None,
            product_title=None,
            extra_data=None,
        )
        assert dto.product_upc is None
        assert dto.product_title is None
        assert dto.extra_data is None

    def test_hash_consistency(self):
        """Хеш консистентен для одинаковых данных."""
        dto1 = SupplierProductDTO(
            supplier_sku="ART-001",
            price=Decimal("100"),
            currency_code="RUB",
            num_in_stock=10,
        )
        dto2 = SupplierProductDTO(
            supplier_sku="ART-001",
            price=Decimal("100"),
            currency_code="RUB",
            num_in_stock=10,
        )
        assert hash(dto1) == hash(dto2)


# ─── SyncResultDTO Tests ──────────────────────────────────────────────────────


class TestSyncResultDTO:
    """Тесты для SyncResultDTO."""

    def test_create_default(self):
        """Создание с значениями по умолчанию."""
        dto = SyncResultDTO(supplier_sku="ART-001")
        assert dto.created is False
        assert dto.updated is False
        assert dto.skipped is False
        assert dto.failed is False

    def test_success_property_created(self):
        """Свойство success=True при created."""
        dto = SyncResultDTO(supplier_sku="ART-001", created=True)
        assert dto.success is True

    def test_success_property_failed(self):
        """Свойство success=False при failed."""
        dto = SyncResultDTO(supplier_sku="ART-001", created=True, failed=True)
        assert dto.success is False

    def test_has_changes_property(self):
        """Свойство has_changes корректно."""
        dto = SyncResultDTO(
            supplier_sku="ART-001",
            price_changed=True,
            stock_changed=False,
        )
        assert dto.has_changes is True


# ─── SyncStatsDTO Tests ───────────────────────────────────────────────────────


class TestSyncStatsDTO:
    """Тесты для SyncStatsDTO."""

    def test_create_default(self):
        """Создание с значениями по умолчанию."""
        dto = SyncStatsDTO()
        assert dto.total == 0
        assert dto.created == 0
        assert dto.failed == 0

    def test_total_auto_calculation(self):
        """Total автоматически рассчитывается."""
        dto = SyncStatsDTO(created=10, updated=5, skipped=3, failed=2)
        assert dto.total == 20

    def test_success_rate(self):
        """Процент успеха рассчитывается корректно."""
        dto = SyncStatsDTO(created=10, updated=5, skipped=3, failed=2)
        assert dto.success_rate == Decimal("75.00")

    def test_has_errors_true(self):
        """has_errors=True при наличии ошибок."""
        dto = SyncStatsDTO(failed=1)
        assert dto.has_errors is True

    def test_has_errors_false(self):
        """has_errors=False без ошибок."""
        dto = SyncStatsDTO(created=10, updated=5, skipped=3)
        assert dto.has_errors is False


# ─── SyncConfigDTO Tests ──────────────────────────────────────────────────────


class TestSyncConfigDTO:
    """Тесты для SyncConfigDTO."""

    def test_create_default(self):
        """Создание с значениями по умолчанию."""
        dto = SyncConfigDTO()
        assert dto.triggered_by == "celery"
        assert dto.batch_size == 100
        assert dto.timeout_seconds == 300
        assert dto.dry_run is False

    def test_dry_run_mode(self):
        """Тестовый режим устанавливается корректно."""
        dto = SyncConfigDTO(dry_run=True)
        assert dto.dry_run is True

    def test_batch_size_validation(self):
        """Валидация размера батча."""
        with pytest.raises(ValidationError):
            SyncConfigDTO(batch_size=0)
        with pytest.raises(ValidationError):
            SyncConfigDTO(batch_size=10001)

    def test_timeout_validation(self):
        """Валидация таймаута."""
        with pytest.raises(ValidationError):
            SyncConfigDTO(timeout_seconds=0)
