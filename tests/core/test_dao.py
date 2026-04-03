"""
tests/core/test_dao.py

Тесты для слоя доступа к данным (DAO) модуля core.
"""
from __future__ import annotations

import pytest

from core.dao import CurrencyDAO


class TestCurrencyDAO:
    """Тесты работы со справочником валют."""

    def test_get_by_code(self, rub):
        currency = CurrencyDAO.get_by_code("RUB")
        assert currency == rub

    def test_get_by_code_not_found(self):
        currency = CurrencyDAO.get_by_code("XXX")
        assert currency is None

    def test_get_active(self, rub, usd):
        currencies = CurrencyDAO.get_active()
        assert rub in currencies
        assert usd in currencies
