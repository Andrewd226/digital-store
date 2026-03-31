"""
suppliers/service/dto.py

Data Transfer Objects для передачи данных между слоями приложения.
"""

from decimal import Decimal
from typing import Annotated, Any

from helpers.arithmetic import round_decimal

from pydantic import BaseModel, ConfigDict, Field


# ─── Config ───────────────────────────────────────────────────────────────────

DTOConfig = ConfigDict(
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
    """
    Данные товара от поставщика.
    Используется для передачи данных из внешнего источника в сервис.
    """

    model_config = DTOConfig

    supplier_sku: SupplierSku
    price: Price
    currency_code: CurrencyCode
    num_in_stock: NumInStock
    product_upc: Annotated[str | None, Field(description="UPC товара")] = None
    product_title: Annotated[str | None, Field(description="Название товара")] = None
    extra_data: Annotated[dict[str, Any] | None, Field(description="Дополнительные данные")] = None

    def __hash__(self):
        return hash((self.supplier_sku, self.price, self.num_in_stock))


# ─── Sync Result DTO ──────────────────────────────────────────────────────────


class SyncResultDTO(BaseModel):
    """
    Результат синхронизации одного товара.
    """

    model_config = DTOConfig

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


# ─── Sync Stats DTO ───────────────────────────────────────────────────────────


class SyncStatsDTO(BaseModel):
    """
    Статистика синхронизации каталога.
    
    total — расчётное поле (сумма всех счётчиков).
    """

    model_config = DTOConfig

    created: int = Field(default=0, ge=0, description="Создано")
    updated: int = Field(default=0, ge=0, description="Обновлено")
    skipped: int = Field(default=0, ge=0, description="Пропущено")
    failed: int = Field(default=0, ge=0, description="Ошибок")

    @property
    def total(self) -> int:
        """
        Расчётное поле: общая сумма всех счётчиков.
        """
        return self.created + self.updated + self.skipped + self.failed

    @property
    def success_rate(self) -> Decimal:
        """Процент успешных операций."""
        if self.total == 0:
            return Decimal('0.0')
        return round_decimal(Decimal(str((self.created + self.updated) / self.total) * 100), 2)

    @property
    def has_errors(self) -> bool:
        """Есть ли ошибки."""
        return self.failed > 0

    @property
    def has_changes(self) -> bool:
        """Были ли изменения."""
        return self.created > 0 or self.updated > 0


# ─── Sync Config DTO ──────────────────────────────────────────────────────────


class SyncConfigDTO(BaseModel):
    """
    Конфигурация синхронизации.
    """

    model_config = DTOConfig

    triggered_by: str = "celery"
    batch_size: BatchSize = 100
    timeout_seconds: TimeoutSeconds = 300
    create_missing_products: bool = False
    deactivate_missing_products: bool = False
