"""
tests/suppliers/test_dto.py

Тесты для DTO (Data Transfer Objects).
Проверяют валидацию полей, расчётные свойства и граничные случаи.
"""
from __future__ import annotations

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
    """Тесты валидации DTO товара от поставщика."""

    def test_create_valid(self):
        """Создание валидного DTO проходит без ошибок."""
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
        """Артикул автоматически приводится к верхнему регистру."""
        dto = SupplierProductDTO(
            supplier_sku="art-001",
            price=Decimal("100"),
            currency_code="RUB",
            num_in_stock=10,
        )
        assert dto.supplier_sku == "ART-001"

    def test_uppercase_currency(self):
        """Код валюты автоматически приводится к верхнему регистру."""
        dto = SupplierProductDTO(
            supplier_sku="ART-001",
            price=Decimal("100"),
            currency_code="rub",
            num_in_stock=10,
        )
        assert dto.currency_code == "RUB"

    def test_invalid_currency_code_pattern(self):
        """Код валюты должен соответствовать формату ISO 4217 (3 буквы)."""
        with pytest.raises(ValidationError):
            SupplierProductDTO(
                supplier_sku="ART-001",
                price=Decimal("100"),
                currency_code="123",
                num_in_stock=10,
            )

    def test_negative_price(self):
        """Отрицательная цена запрещена валидатором ge=0."""
        with pytest.raises(ValidationError):
            SupplierProductDTO(
                supplier_sku="ART-001",
                price=Decimal("-100"),
                currency_code="RUB",
                num_in_stock=10,
            )

    def test_empty_sku(self):
        """Пустой артикул запрещён валидатором min_length=1."""
        with pytest.raises(ValidationError):
            SupplierProductDTO(
                supplier_sku="",
                price=Decimal("100"),
                currency_code="RUB",
                num_in_stock=10,
            )

    def test_optional_fields(self):
        """Опциональные поля могут быть опущены или равны None."""
        dto = SupplierProductDTO(
            supplier_sku="ART-001",
            price=Decimal("100"),
            currency_code="RUB",
            num_in_stock=10,
        )
        assert dto.product_upc is None
        assert dto.product_title is None
        assert dto.extra_data is None

    def test_extra_data_dict(self):
        """Поле extra_data принимает произвольный словарь."""
        dto = SupplierProductDTO(
            supplier_sku="ART-001",
            price=Decimal("100"),
            currency_code="RUB",
            num_in_stock=10,
            extra_data={"vendor": "Test", "category": "Electronics"},
        )
        assert dto.extra_data["vendor"] == "Test"

    def test_hash_consistency(self):
        """Хеш идентичен для одинаковых неизменяемых полей."""
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
    """Тесты DTO результата обработки одного товара."""

    def test_create_default(self):
        """По умолчанию все статусы сброшены."""
        dto = SyncResultDTO(supplier_sku="ART-001")
        assert dto.created is False
        assert dto.updated is False
        assert dto.skipped is False
        assert dto.failed is False

    def test_success_property_created(self):
        """success=True при успешном создании."""
        dto = SyncResultDTO(supplier_sku="ART-001", created=True)
        assert dto.success is True

    def test_success_property_failed(self):
        """success=False при наличии ошибки, даже если created=True."""
        dto = SyncResultDTO(supplier_sku="ART-001", created=True, failed=True)
        assert dto.success is False

    def test_has_changes_property(self):
        """has_changes=True при изменении цены или остатка."""
        dto = SyncResultDTO(
            supplier_sku="ART-001",
            price_changed=True,
            stock_changed=False,
        )
        assert dto.has_changes is True


# ─── SyncStatsDTO Tests ───────────────────────────────────────────────────────


class TestSyncStatsDTO:
    """Тесты DTO агрегированной статистики синхронизации."""

    def test_create_default(self):
        """Счётчики инициализируются нулями."""
        dto = SyncStatsDTO()
        assert dto.total == 0
        assert dto.created == 0

    def test_total_auto_calculation(self):
        """total автоматически рассчитывается как сумма счётчиков."""
        dto = SyncStatsDTO(created=10, updated=5, skipped=3, failed=2)
        assert dto.total == 20

    def test_success_rate(self):
        """success_rate корректно считает процент через Decimal."""
        dto = SyncStatsDTO(created=10, updated=5, skipped=3, failed=2)
        assert dto.success_rate == Decimal("75.00")

    def test_has_errors_true(self):
        """has_errors=True при наличии хотя бы одной ошибки."""
        dto = SyncStatsDTO(failed=1)
        assert dto.has_errors is True

    def test_has_changes_true(self):
        """has_changes=True при создании или обновлении."""
        dto = SyncStatsDTO(created=10)
        assert dto.has_changes is True


# ─── SyncConfigDTO Tests ──────────────────────────────────────────────────────


class TestSyncConfigDTO:
    """Тесты DTO конфигурации запуска синхронизации."""

    def test_create_default(self):
        """Значения по умолчанию соответствуют спецификации."""
        dto = SyncConfigDTO()
        assert dto.triggered_by == "celery"
        assert dto.batch_size == 100
        assert dto.timeout_seconds == 300
        assert dto.create_missing_products is False
        assert dto.deactivate_missing_products is False

    def test_batch_size_validation(self):
        """batch_size должен быть строго больше 0 и не превышать 10000."""
        with pytest.raises(ValidationError):
            SyncConfigDTO(batch_size=0)
        with pytest.raises(ValidationError):
            SyncConfigDTO(batch_size=10001)

    def test_timeout_validation(self):
        """timeout_seconds должен быть строго больше 0."""
        with pytest.raises(ValidationError):
            SyncConfigDTO(timeout_seconds=0)
