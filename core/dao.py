"""
core/dao.py

Data Access Object для справочника валют.
Все методы принимают и возвращают только DTO или скалярные значения.
"""

from __future__ import annotations

from core.dto import CurrencyDTO
from core.models import Currency


class CurrencyDAO:
    """DAO для операций со справочником валют."""

    # @staticmethod
    # def _to_dto(currency: Currency) -> CurrencyDTO:
    #     return CurrencyDTO(
    #         id=currency.id,
    #         currency_code=currency.currency_code,
    #         name=currency.name,
    #         symbol=currency.symbol,
    #     )

    @staticmethod
    def get_by_code(currency_code: str) -> CurrencyDTO | None:
        """Получает валюту по ISO-коду (например, 'USD', 'RUB')."""
        try:
            return CurrencyDTO.model_validate(Currency.objects.get(currency_code=currency_code))
        except Currency.DoesNotExist:
            return None

    @staticmethod
    def get_active() -> list[CurrencyDTO]:
        """Возвращает все доступные в системе валюты."""
        return [CurrencyDTO.model_validate(c) for c in Currency.objects.all()]
