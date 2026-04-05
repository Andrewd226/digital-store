"""
suppliers/models.py

Модуль поставщиков: учет цен, остатков и истории изменений.

Правила:
- Все строковые поля → TextField
- Все денежные поля → DecimalField(max_digits=50, decimal_places=25)
- Чувствительные данные → EncryptedTextField (django-fernet-encrypted-fields)
- Защита от устаревших данных и Celery-интеграция на уровне модели
"""

from __future__ import annotations
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from encrypted_fields.fields import EncryptedTextField
from helpers.arithmetic import round_decimal


class Supplier(models.Model):
    """Модель поставщика. Хранит настройки синхронизации и метод подключения."""
    class SyncMethod(models.TextChoices):
        API = "API", _("REST API")
        MANUAL = "MANUAL", _("Ручная загрузка")
        FTP = "FTP", _("FTP/SFTP")

    name = models.TextField(_("Название"))
    code = models.TextField(
        _("Код"), unique=True, db_index=True, help_text=_("Уникальный идентификатор (slug)")
    )
    sync_method = models.TextField(
        _("Метод синхронизации"), choices=SyncMethod.choices, default=SyncMethod.MANUAL
    )
    api_url = models.TextField(_("URL API"), blank=True, default="")
    api_extra_config = models.JSONField(_("Доп. конфигурация API"), default=dict, blank=True)
    sync_schedule = models.TextField(_("Расписание синхронизации (cron)"), default="0 6 * * *")
    default_currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="default_suppliers",
        verbose_name=_("Валюта по умолчанию"),
    )
    priority = models.PositiveIntegerField(
        _("Приоритет"), default=100, help_text=_("Меньше число — выше приоритет")
    )
    supplier_is_active = models.BooleanField(_("Активен"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Поставщик")
        verbose_name_plural = _("Поставщики")
        ordering = ["priority", "name"]

    def __str__(self) -> str:
        status = _("Активен") if self.supplier_is_active else _("Отключён")
        return f"{self.name} ({status})"


class SupplierCredential(models.Model):
    """
    Учетные данные для доступа к API/FTP поставщика.

    🔒 Чувствительные поля зашифрованы на уровне БД.
    """

    supplier = models.OneToOneField(
        Supplier, on_delete=models.CASCADE, related_name="credential", verbose_name=_("Поставщик")
    )
    api_key = EncryptedTextField(_("API Key"), blank=True)
    api_secret = EncryptedTextField(_("API Secret"), blank=True)
    extra = models.JSONField(_("Доп. данные"), default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Учетные данные поставщика")
        verbose_name_plural = _("Учетные данные поставщиков")

    def __str__(self) -> str:
        return f"Credentials for {self.supplier.name}"


class SupplierStockRecord(models.Model):
    """Текущие остатки и цена товара от конкретного поставщика."""
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="stock_records",
        verbose_name=_("Поставщик"),
    )
    product = models.ForeignKey(
        "catalogue.Product",
        on_delete=models.PROTECT,
        related_name="supplier_stock_records",
        verbose_name=_("Товар"),
    )
    supplier_sku = models.TextField(_("Артикул поставщика"), db_index=True)
    price = models.DecimalField(
        _("Цена"),
        max_digits=50,
        decimal_places=25,
        default=Decimal("0"),
        validators=[MinValueValidator(0)],
    )
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="stock_records",
        verbose_name=_("Валюта"),
    )
    num_in_stock = models.PositiveIntegerField(_("Количество на складе"), default=0)
    num_allocated = models.PositiveIntegerField(
        _("Зарезервировано"), default=0, help_text=_("Количество в активных заказах")
    )
    is_active = models.BooleanField(_("Активен"), default=True)
    # Версионирование данных для защиты от перезаписи новых значений старыми
    last_supplier_updated_at = models.DateTimeField(
        _("Время обновления у поставщика"),
        null=True,
        blank=True,
        help_text=_("Если incoming.updated_at <= record.updated_at, обновление пропускается."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Остаток поставщика")
        verbose_name_plural = _("Остатки поставщиков")
        constraints = [
            models.UniqueConstraint(fields=["supplier", "product"], name="unique_supplier_product"),
        ]
        indexes = [
            models.Index(fields=["supplier", "is_active"]),
            models.Index(fields=["product", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.supplier.name} -> {self.product.title} ({self.num_in_stock} шт.)"

    @property
    def num_available(self) -> int:
        """Доступное количество (на складе минус зарезервированное)."""
        return max(0, self.num_in_stock - self.num_allocated)

    @property
    def is_available(self) -> bool:
        """Товар доступен для заказа."""
        return self.is_active and self.num_available > 0


class SupplierStockHistory(models.Model):
    """Append-only история изменений цен и остатков. Не подлежит редактированию."""
    class ChangeType(models.TextChoices):
        CREATED = "CREATED", _("Создано")
        PRICE_CHANGED = "PRICE_CHANGED", _("Изменение цены")
        STOCK_CHANGED = "STOCK_CHANGED", _("Изменение остатка")
        BOTH_CHANGED = "BOTH_CHANGED", _("Изменение цены и остатка")
        DEACTIVATED = "DEACTIVATED", _("Деактивировано")

    stock_record = models.ForeignKey(
        SupplierStockRecord,
        on_delete=models.PROTECT,
        related_name="history",
        verbose_name=_("Запись остатка"),
    )
    sync = models.ForeignKey(
        "suppliers.SupplierCatalogSync",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="history_records",
        verbose_name=_("Синхронизация"),
    )
    # Все снимки данных → TextField (денормализация для аудита)
    snapshot_supplier_name = models.TextField(_("Название поставщика"))
    snapshot_product_title = models.TextField(_("Название товара"))
    snapshot_product_upc = models.TextField(_("UPC"), blank=True, default="")
    snapshot_supplier_sku = models.TextField(_("Артикул поставщика"))
    snapshot_currency_code = models.TextField(_("Код валюты"))
    # Точность цены в истории совпадает с основной таблицей
    price_before = models.DecimalField(
        _("Цена до"), max_digits=50, decimal_places=25, null=True, blank=True
    )
    price_after = models.DecimalField(_("Цена после"), max_digits=50, decimal_places=25)
    num_in_stock_before = models.PositiveIntegerField(_("Остаток до"), null=True, blank=True)
    num_in_stock_after = models.PositiveIntegerField(_("Остаток после"))
    change_type = models.TextField(_("Тип изменения"), choices=ChangeType.choices)
    recorded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("История изменений")
        verbose_name_plural = _("История изменений")
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(fields=["stock_record", "-recorded_at"]),
            models.Index(fields=["snapshot_supplier_name", "-recorded_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.snapshot_supplier_sku}: {self.price_before} -> {self.price_after} ({self.change_type})"

    @property
    def price_delta(self) -> Decimal:
        """Абсолютное изменение цены."""
        if self.price_before is None:
            return self.price_after
        return self.price_after - self.price_before

    @property
    def price_delta_pct(self) -> Decimal:
        """Процентное изменение цены (финансовое округление через quantize)."""
        if self.price_before and self.price_before > 0:
            return round_decimal(self.price_delta / self.price_before * 100, 2)
        return Decimal("0.00")


class SupplierCatalogSync(models.Model):
    """Лог выполнения задач синхронизации каталогов."""
    class Status(models.TextChoices):
        PENDING = "PENDING", _("Ожидание")
        RUNNING = "RUNNING", _("Выполняется")
        SUCCESS = "SUCCESS", _("Успешно")
        PARTIAL = "PARTIAL", _("Частично выполнено")
        FAILED = "FAILED", _("Ошибка")

    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="sync_logs", verbose_name=_("Поставщик")
    )
    status = models.TextField(_("Статус"), choices=Status.choices, default=Status.PENDING)
    triggered_by = models.TextField(_("Запущено"), default="celery")
    # Поле для связки с асинхронными задачами Celery
    task_id = models.TextField(
        _("Celery Task ID"), blank=True, default="", help_text=_("ID асинхронной задачи")
    )
    started_at = models.DateTimeField(_("Начало"), auto_now_add=True)
    finished_at = models.DateTimeField(_("Окончание"), null=True, blank=True)
    total_items = models.PositiveIntegerField(_("Всего элементов"), default=0)
    created_items = models.PositiveIntegerField(_("Создано"), default=0)
    updated_items = models.PositiveIntegerField(_("Обновлено"), default=0)
    skipped_items = models.PositiveIntegerField(_("Пропущено"), default=0)
    failed_items = models.PositiveIntegerField(_("Ошибки"), default=0)
    error_log = models.TextField(_("Лог ошибок"), blank=True, default="")

    class Meta:
        verbose_name = _("Синхронизация")
        verbose_name_plural = _("Синхронизации")
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["supplier", "-started_at"]),
            models.Index(fields=["status", "-started_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.supplier.name} - {self.status} ({self.started_at:%Y-%m-%d %H:%M})"

    @property
    def duration_seconds(self) -> int | None:
        """Длительность синхронизации в секундах."""
        if self.finished_at and self.started_at:
            return int((self.finished_at - self.started_at).total_seconds())
        return None
