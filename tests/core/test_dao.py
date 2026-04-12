"""
tests/core/test_dao.py

Тесты для слоя доступа к данным (DAO) модуля core.
"""

from __future__ import annotations

from core.dao import CurrencyDAO


class TestCurrencyDAO:
    """Тесты работы со справочником валют."""

    def test_get_by_code(self, rub_dto):
        currency = CurrencyDAO.get_by_code("RUB")
        assert currency == rub_dto

    def test_get_by_code_not_found(self, db):
        currency = CurrencyDAO.get_by_code("XXX")
        assert currency is None

    def test_get_active(self, rub_dto, usd_dto):
        currencies = CurrencyDAO.get_active()
        assert rub_dto in currencies
        assert usd_dto in currencies
