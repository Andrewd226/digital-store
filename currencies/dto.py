"""
currencies/dto.py

Data Transfer Objects для синхронизации курсов валют.
Используются для передачи данных между слоями:
    Fetcher → DAO → tasks
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator


class RateDTO(BaseModel):
    """
    Один курс валютной пары, полученный от внешнего источника.
    Передаётся из Fetcher в DAO.
    """

    from_code: str
    to_code: str
    rate: Decimal
    rate_datetime: datetime

    @field_validator("from_code", "to_code")
    @classmethod
    def code_must_be_uppercase(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("rate")
    @classmethod
    def rate_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("rate должен быть больше нуля")
        return v

    model_config = {"frozen": True}


class SyncResultDTO(BaseModel):
    """
    Результат синхронизации одного источника.
    Возвращается из sync_currency_rates.
    """

    status: str  # "success" | "failed" | "skipped"
    source_id: int | None = None
    source_name: str | None = None
    rates_updated: int = 0
    error: str | None = None
