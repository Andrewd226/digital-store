"""
core/dao.py

Data Access Object для справочника валют.
Размещен в core, так как Currency — это базовая сущность системы.
"""

from __future__ import annotations

from django.db.models import QuerySet

from core.models import Currency


class CurrencyDAO:
    """DAO для операций со справочником валют."""

    @staticmethod
    def get_by_code(currency_code: str) -> Currency | None:
        """Получает валюту по ISO-коду (например, 'USD', 'RUB')."""
        try:
            return Currency.objects.get(currency_code=currency_code)
        except Currency.DoesNotExist:
            return None

    @staticmethod
    def get_active() -> QuerySet[Currency]:
        """Возвращает все доступные в системе валюты."""
        return Currency.objects.all()
