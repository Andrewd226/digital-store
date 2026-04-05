"""
suppliers/service/dto.py

Граница слоя данных. Все DTO строго типизированы.
ImmutableDTOConfig — для передачи между слоями (гарантия отсутствия побочных эффектов).
MutableDTOConfig — для внутренней обработки внутри бизнес-логики (статистика, результаты).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from helpers.arithmetic import round_decimal

# ─── Configs ──────────────────────────────────────────────────────────────────
ImmutableDTOConfig = ConfigDict(frozen=True, arbitrary_types_allowed=True, use_enum_values=True, extra="ignore")
MutableDTOConfig = ConfigDict(frozen=False, arbitrary_types_allowed=True, use_enum_values=True, extra="ignore")

# ─── Type Aliases ─────────────────────────────────────────────────────────────
SupplierSku = Annotated[str, Field(min_length=1)]
Price = Annotated[Decimal, Field(ge=0)]
CurrencyCode = Annotated[str, Field(min_length=3)]
NumInStock = Annotated[int, Field(ge=0)]
BatchSize = Annotated[int, Field(gt=0)]
TimeoutSeconds = Annotated[int, Field(gt=0)]


# ─── Input DTO ────────────────────────────────────────────────────────────────
class SupplierProductDTO(BaseModel):
    model_config = ImmutableDTOConfig
    supplier_sku: SupplierSku
    price: Price
    currency_code: CurrencyCode
    num_in_stock: NumInStock
    product_upc: str | None = None
    product_title: str | None = None
    config: dict[str, Any] | None = None
    source_updated_at: datetime | None = None


# ─── State DTO (DAO ↔ Business) ──────────────────────────────────────────────
class SupplierStockRecordDTO(BaseModel):
    """Представление записи остатка на границе DAO. Immutable для передачи между слоями."""
    model_config = ImmutableDTOConfig
    id: int | None = None
    supplier_sku: SupplierSku
    price: Price
    currency_code: CurrencyCode
    num_in_stock: NumInStock
    num_allocated: int = 0
    is_active: bool = True
    last_supplier_updated_at: datetime | None = None
    product_upc: str | None = None


# ─── Process Result DTO ───────────────────────────────────────────────────────
class SyncResultDTO(BaseModel):
    model_config = MutableDTOConfig
    supplier_sku: SupplierSku
    created: bool = False
    updated: bool = False
    skipped: bool = False
    failed: bool = False
    error_message: str | None = None
    price_changed: bool = False
    stock_changed: bool = False
    price_before: Price | None = None
    price_after: Price | None = None
    stock_before: NumInStock | None = None
    stock_after: NumInStock | None = None
    skipped_reason: str | None = None


# ─── Stats DTO ────────────────────────────────────────────────────────────────
class SyncStatsDTO(BaseModel):
    model_config = MutableDTOConfig
    created: int = Field(default=0, ge=0)
    updated: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)

    @property
    def total(self) -> int:
        return self.created + self.updated + self.skipped + self.failed

    @property
    def success_rate(self) -> Decimal:
        if self.total == 0:
            return Decimal("0.0")
        return round_decimal(Decimal(self.created + self.updated) * 100 / Decimal(self.total), 2)

    @property
    def has_errors(self) -> bool:
        return self.failed > 0

    @property
    def has_changes(self) -> bool:
        return self.created > 0 or self.updated > 0


# ─── Sync Log DTO (DAO ↔ Business) ────────────────────────────────────────────
class SyncLogDTO(BaseModel):
    model_config = MutableDTOConfig
    id: int | None = None
    supplier_code: str
    status: str
    triggered_by: str
    started_at: datetime
    finished_at: datetime | None = None
    task_id: str | None = None


# ─── Config DTO ───────────────────────────────────────────────────────────────
class SyncConfigDTO(BaseModel):
    model_config = ImmutableDTOConfig
    triggered_by: str = "celery"
    batch_size: BatchSize = 100
    timeout_seconds: TimeoutSeconds = 300
    create_missing_products: bool = False
    deactivate_missing_products: bool = False
