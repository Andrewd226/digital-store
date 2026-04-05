"""
catalogue/dto.py

Data Transfer Objects для каталога товаров.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

ImmutableDTOConfig = ConfigDict(
    frozen=True,
    arbitrary_types_allowed=True,
    use_enum_values=True,
    extra="ignore",
)


class ProductDTO(BaseModel):
    """Иммутабельный снимок товара для передачи между слоями."""

    model_config = ImmutableDTOConfig

    id: int
    title: str
    upc: str | None
