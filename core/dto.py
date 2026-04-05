"""
core/dto.py

Data Transfer Objects для базовых справочников системы.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

ImmutableDTOConfig = ConfigDict(
    frozen=True,
    arbitrary_types_allowed=True,
    use_enum_values=True,
    extra="ignore",
)


class CurrencyDTO(BaseModel):
    """Иммутабельный снимок валюты для передачи между слоями."""

    model_config = ImmutableDTOConfig

    id: int
    currency_code: str
    name: str
    symbol: str
