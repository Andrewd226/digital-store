"""
suppliers/service/dto.py

Data Transfer Objects (DTO) для передачи данных между слоями приложения.
Используют Pydantic v2 для строгой валидации, сериализации и типизации.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from helpers.arithmetic import round_decimal
from pydantic import BaseModel, ConfigDict, Field


# ─── Configs ──────────────────────────────────────────────────────────────────

ImmutableDTOConfig = ConfigDict(
    frozen=True,
    arbitrary_types_allowed=True,
    use_enum_values=True,
    extra="ignore",
)

MutableDTOConfig = ConfigDict(
    frozen=False,
    arbitrary_types_allowed=True,
    use_enum_values=True,
    extra="ignore",
)

# ─── Annotated types ──────────────────────────────────────────────────────────

SupplierSku = Annotated[str, Field(min_length=1, description="Артикул поставщика")]
Price = Annotated[Decimal, Field(ge=0, description="Цена товара")]
CurrencyCode = Annotated[str, Field(min_length=3, description="Код валюты (ISO 4217)")]
NumInStock = Annotated[int, Field(ge=0, description="Количество на складе")]
BatchSize = Annotated[int, Field(gt=0, description="Размер батча")]
TimeoutSeconds = Annotated[int, Field(gt=0, description="Таймаут в секундах")]


# ─── Product Data DTO ─────────────────────────────────────────────────────────


class SupplierProductDTO(BaseModel):
    """Данные товара от поставщика. Иммутабелен, безопасен для кеширования."""
    model_config = ImmutableDTOConfig

    supplier_sku: SupplierSku
    price: Price
    currency_code: CurrencyCode
    num_in_stock: NumInStock
    product_upc: Annotated[str | None, Field(description="UPC товара")] = None
    product_title: Annotated[str | None, Field(description="Название товара")] = None
    config: Annotated[dict[str, Any] | None, Field(description="Доп. данные")] = None
    # ✅ Пункт 2: Время обновления в источнике для защиты от перезаписи новых данных старыми
    source_updated_at: Annotated[datetime | None, Field(description="Timestamp обновления у поставщика")] = None


# ─── Sync Result DTO ──────────────────────────────────────────────────────────


class SyncResultDTO(BaseModel):
    """Результат обработки одного товара. Мутируется сервисом в процессе."""
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
    skipped_reason: str | None = None  # ✅ Причина пропуска (например, "stale_data")


# ─── Sync Stats DTO ───────────────────────────────────────────────────────────


class SyncStatsDTO(BaseModel):
    """Агрегированная статистика синхронизации. Мутируется сервисом."""
    model_config = MutableDTOConfig

    created: int = Field(default=0, ge=0, description="Создано")
    updated: int = Field(default=0, ge=0, description="Обновлено")
    skipped: int = Field(default=0, ge=0, description="Пропущено")
    failed: int = Field(default=0, ge=0, description="Ошибок")

    @property
    def total(self) -> int:
        return self.created + self.updated + self.skipped + self.failed

    @property
    def success_rate(self) -> Decimal:
        if self.total == 0:
            return Decimal("0.0")
        return round_decimal(
            Decimal(self.created + self.updated) * 100 / Decimal(self.total), 2
        )

    @property
    def has_errors(self) -> bool:
        return self.failed > 0

    @property
    def has_changes(self) -> bool:
        return self.created > 0 or self.updated > 0


# ─── Sync Config DTO ──────────────────────────────────────────────────────────


class SyncConfigDTO(BaseModel):
    """Конфигурация запуска синхронизации. Иммутабельна."""
    model_config = ImmutableDTOConfig

    triggered_by: str = "celery"
    batch_size: BatchSize = 500  # ✅ Уменьшен для регулярного флеша буферов
    timeout_seconds: TimeoutSeconds = 300
    create_missing_products: bool = False
    deactivate_missing_products: bool = False
