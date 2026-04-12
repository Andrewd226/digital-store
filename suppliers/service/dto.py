"""
suppliers/service/dto.py

Data Transfer Objects сервиса синхронизации каталогов поставщиков.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

ImmutableDTOConfig = ConfigDict(
    from_attributes=True,
    frozen=True,
    arbitrary_types_allowed=True,
    use_enum_values=True,
    extra="ignore",
)


class StockChangeType(StrEnum):
    """Тип изменения записи остатка. Значения совпадают с SupplierStockHistory.ChangeType."""

    CREATED = "CREATED"
    PRICE_CHANGED = "PRICE_CHANGED"
    STOCK_CHANGED = "STOCK_CHANGED"
    BOTH_CHANGED = "BOTH_CHANGED"
    DEACTIVATED = "DEACTIVATED"


class SupplierDTO(BaseModel):
    """Снимок поставщика для передачи между слоями."""

    model_config = ImmutableDTOConfig

    id: int
    name: str
    code: str
    sync_method: str
    api_url: str
    api_extra_config: dict
    default_currency_code: str


class SupplierCredentialDTO(BaseModel):
    """Учётные данные поставщика."""

    model_config = ImmutableDTOConfig

    api_key: str
    api_secret: str
    extra: dict


class RawCatalogItemDTO(BaseModel):
    """
    Сырая позиция каталога, полученная от источника поставщика.
    Выход метода fetch_catalog().
    supplier_sku используется как UPC для матчинга с Product.
    """

    model_config = ImmutableDTOConfig

    supplier_sku: str
    price: Decimal
    currency_code: str
    num_in_stock: int
    supplier_updated_at: datetime | None = None

    @field_validator("price")
    @classmethod
    def price_must_be_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("price должен быть >= 0")
        return v

    @field_validator("currency_code")
    @classmethod
    def currency_code_upper(cls, v: str) -> str:
        return v.strip().upper()


class SupplierStockRecordDTO(BaseModel):
    """Снимок текущей записи остатка поставщика."""

    model_config = ImmutableDTOConfig

    id: int
    supplier_id: int
    product_id: int
    supplier_sku: str
    price: Decimal
    currency_code: str
    num_in_stock: int
    is_active: bool
    last_supplier_updated_at: datetime | None


class SupplierStockRecordCreateDTO(BaseModel):
    """DTO для bulk-создания новых записей остатков."""

    model_config = ImmutableDTOConfig

    supplier_id: int
    product_id: int
    supplier_sku: str
    price: Decimal
    currency_code: str
    num_in_stock: int
    is_active: bool = True
    last_supplier_updated_at: datetime | None = None


class SupplierStockRecordUpdateDTO(BaseModel):
    """DTO для bulk-обновления существующих записей остатков."""

    model_config = ImmutableDTOConfig

    id: int
    price: Decimal
    currency_code: str
    num_in_stock: int
    is_active: bool
    last_supplier_updated_at: datetime | None


class SupplierStockHistoryCreateDTO(BaseModel):
    """DTO для bulk-создания записей истории изменений."""

    model_config = ImmutableDTOConfig

    stock_record_id: int
    sync_id: int | None
    snapshot_supplier_name: str
    snapshot_product_title: str
    snapshot_product_upc: str
    snapshot_supplier_sku: str
    snapshot_currency_code: str
    price_before: Decimal | None
    price_after: Decimal
    num_in_stock_before: int | None
    num_in_stock_after: int
    change_type: StockChangeType


class CatalogSyncResultDTO(BaseModel):
    """Итог одного запуска синхронизации каталога."""

    model_config = ImmutableDTOConfig

    sync_id: int
    total_items: int
    created_items: int
    updated_items: int
    skipped_items: int
    failed_items: int
