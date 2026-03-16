from django.db import models
from encrypted_fields.fields import EncryptedCharField


# ─── 1.1 Supplier ─────────────────────────────────────────────────────────────


class Supplier(models.Model):
    """
    Поставщик товаров. Самостоятельная модель — не наследует AbstractPartner,
    чтобы не конфликтовать с Oscar Partner при регистрации моделей.
    Данные не удаляются — отключение через supplier_is_active = False.
    """

    class SyncMethod(models.TextChoices):
        API = "api", "REST API"
        FTP = "ftp", "FTP/SFTP"
        EMAIL = "email", "E-mail прайс-лист"
        MANUAL = "manual", "Вручную"

    name = models.TextField(
        verbose_name="Название",
    )
    code = models.SlugField(
        unique=True,
        verbose_name="Код",
        help_text="Уникальный идентификатор, используется в URL и импорте",
    )
    sync_method = models.TextField(
        choices=SyncMethod.choices,
        default=SyncMethod.MANUAL,
        verbose_name="Метод синхронизации",
    )
    api_url = models.TextField(
        blank=True,
        verbose_name="URL API",
    )
    api_extra_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Доп. параметры подключения",
        help_text="Заголовки, тайм-ауты, маппинг полей и т.д.",
    )
    default_currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="default_for_suppliers",
        verbose_name="Валюта по умолчанию",
    )
    sync_schedule = models.TextField(
        default="0 6 * * *",
        verbose_name="Расписание (cron)",
        help_text='Например: "0 6 * * *" — каждый день в 06:00',
    )
    supplier_is_active = models.BooleanField(
        default=True,
        verbose_name="Поставщик активен",
        help_text="False — поставщик отключён. Данные сохраняются.",
    )
    priority = models.PositiveSmallIntegerField(
        default=100,
        verbose_name="Приоритет",
        help_text="Меньше = выше приоритет при выборе стратегии",
    )

    class Meta:
        verbose_name = "Поставщик"
        verbose_name_plural = "Поставщики"
        ordering = ["priority", "name"]

    def __str__(self):
        status = "" if self.supplier_is_active else " [отключён]"
        return f"{self.name} ({self.get_sync_method_display()}){status}"


# ─── 1.2 SupplierCredential ───────────────────────────────────────────────────


class SupplierCredential(models.Model):
    """
    API-ключи поставщика. Хранятся зашифрованными.
    Данные не удаляются.
    """

    supplier = models.OneToOneField(
        "Supplier",
        on_delete=models.PROTECT,
        related_name="credential",
        verbose_name="Поставщик",
    )
    api_key = EncryptedCharField(
        max_length=512,
        blank=True,
        verbose_name="API-ключ",
    )
    api_secret = EncryptedCharField(
        max_length=512,
        blank=True,
        verbose_name="API-секрет",
    )
    extra = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Доп. учётные данные",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Учётные данные поставщика"
        verbose_name_plural = "Учётные данные поставщиков"
        default_permissions = ("view", "change")

    def __str__(self):
        return f"Credentials: {self.supplier.name}"


# ─── 1.3 SupplierCatalogSync ──────────────────────────────────────────────────


class SupplierCatalogSync(models.Model):
    """
    Лог каждого запуска синхронизации каталога поставщика.
    Данные не удаляются.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает запуска"
        RUNNING = "running", "Выполняется"
        SUCCESS = "success", "Успешно"
        PARTIAL = "partial", "Частичный успех"
        FAILED = "failed", "Ошибка"

    supplier = models.ForeignKey(
        "Supplier",
        on_delete=models.PROTECT,
        related_name="catalog_syncs",
        verbose_name="Поставщик",
    )
    status = models.TextField(
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Статус",
    )
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Начало")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Конец")
    task_id = models.TextField(blank=True, verbose_name="ID задачи Celery")

    total_items = models.PositiveIntegerField(default=0, verbose_name="Всего позиций")
    created_items = models.PositiveIntegerField(default=0, verbose_name="Создано")
    updated_items = models.PositiveIntegerField(default=0, verbose_name="Обновлено")
    skipped_items = models.PositiveIntegerField(default=0, verbose_name="Пропущено")
    failed_items = models.PositiveIntegerField(default=0, verbose_name="Ошибок")

    error_log = models.TextField(blank=True, verbose_name="Лог ошибок")
    triggered_by = models.TextField(
        default="celery",
        verbose_name="Инициатор",
        help_text='"celery", "admin", "api" или имя пользователя',
    )

    class Meta:
        verbose_name = "Синхронизация каталога поставщика"
        verbose_name_plural = "Синхронизации каталогов поставщиков"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["supplier", "-started_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return (
            f"{self.supplier.name} | "
            f"{self.started_at:%Y-%m-%d %H:%M} | "
            f"{self.get_status_display()}"
        )

    @property
    def duration_seconds(self):
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


# ─── 1.4 SupplierStockRecord ──────────────────────────────────────────────────


class SupplierStockRecord(models.Model):
    """
    Текущая цена и наличие товара у поставщика в его валюте.
    Уникальность: один товар × один поставщик = одна запись.
    История изменений — в SupplierStockHistory.
    Данные не удаляются — мягкое отключение через is_active = False.
    """

    supplier = models.ForeignKey(
        "Supplier",
        on_delete=models.PROTECT,
        related_name="stock_records",
        verbose_name="Поставщик",
    )
    product = models.ForeignKey(
        "catalogue.Product",
        on_delete=models.PROTECT,
        related_name="supplier_stock_records",
        verbose_name="Товар",
    )
    supplier_sku = models.TextField(
        blank=False,
        verbose_name="Артикул поставщика",
    )
    price = models.DecimalField(
        max_digits=18,
        decimal_places=18,
        null=False,
        blank=False,
        verbose_name="Цена",
    )
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="supplier_stock_records",
        verbose_name="Валюта",
    )
    num_in_stock = models.PositiveIntegerField(default=0, verbose_name="На складе")
    num_allocated = models.PositiveIntegerField(default=0, verbose_name="Зарезервировано")
    last_sync = models.ForeignKey(
        "SupplierCatalogSync",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="updated_stock_records",
        verbose_name="Последняя синхронизация",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
        help_text="False — поставщик перестал поставлять этот товар. Данные сохраняются.",
    )

    class Meta:
        verbose_name = "Остаток у поставщика"
        verbose_name_plural = "Остатки у поставщиков"
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "product"],
                name="unique_supplier_product_stock",
            ),
        ]
        indexes = [
            models.Index(fields=["supplier", "is_active"]),
            models.Index(fields=["product", "is_active"]),
            models.Index(fields=["supplier", "supplier_sku"], name="idx_supplier_sku"),
        ]

    def __str__(self):
        return (
            f"{self.supplier.name} | "
            f"{self.product.title} | "
            f"{self.price} {self.currency.currency_code}"
        )

    @property
    def num_available(self):
        """Доступный остаток = на складе − зарезервировано."""
        return max(0, self.num_in_stock - self.num_allocated)

    @property
    def is_available(self):
        """Доступен к заказу = активен И есть доступный остаток."""
        return self.is_active and self.num_available > 0


# ─── 1.5 SupplierStockHistory ─────────────────────────────────────────────────


class SupplierStockHistory(models.Model):
    """
    Append-only история каждого изменения цены или наличия у поставщика.
    FK → PROTECT: физическое удаление невозможно по правилам проекта.
    Снимки полей сохраняют полный контекст навсегда.
    Данные не удаляются.
    """

    stock_record = models.ForeignKey(
        "SupplierStockRecord",
        on_delete=models.PROTECT,
        related_name="history",
        verbose_name="Запись остатка",
    )
    sync = models.ForeignKey(
        "SupplierCatalogSync",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Синхронизация-источник",
    )

    # Снимки — сохраняют контекст навсегда
    snapshot_supplier_name = models.TextField(verbose_name="Поставщик (снимок)")
    snapshot_product_title = models.TextField(verbose_name="Товар (снимок)")
    snapshot_product_upc = models.TextField(blank=True, verbose_name="Артикул товара (снимок)")
    snapshot_supplier_sku = models.TextField(blank=True, verbose_name="Артикул поставщика (снимок)")
    snapshot_currency_code = models.TextField(verbose_name="Код валюты (снимок)")

    # price_before = NULL при первом создании записи
    price_before = models.DecimalField(
        max_digits=18,
        decimal_places=18,
        null=True,
        blank=True,
        verbose_name="Цена до",
    )
    price_after = models.DecimalField(
        max_digits=18,
        decimal_places=18,
        null=False,
        blank=False,
        verbose_name="Цена после",
    )
    num_in_stock_before = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Остаток до",
    )
    num_in_stock_after = models.PositiveIntegerField(verbose_name="Остаток после")

    class ChangeType(models.TextChoices):
        CREATED = "created", "Создана"
        PRICE_CHANGED = "price_changed", "Изменена цена"
        STOCK_CHANGED = "stock_changed", "Изменён остаток"
        BOTH_CHANGED = "both_changed", "Изменены цена и остаток"
        DEACTIVATED = "deactivated", "Деактивирован"

    change_type = models.TextField(
        choices=ChangeType.choices,
        verbose_name="Тип изменения",
        db_index=True,
    )
    recorded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время записи",
        db_index=True,
    )

    class Meta:
        verbose_name = "История остатка поставщика"
        verbose_name_plural = "История остатков поставщиков"
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(
                fields=["stock_record", "-recorded_at"],
                name="idx_supplier_stock_history",
            ),
        ]

    def __str__(self):
        return (
            f"{self.snapshot_supplier_name} | "
            f"{self.snapshot_product_title} | "
            f"{self.get_change_type_display()} | "
            f"{self.recorded_at:%Y-%m-%d %H:%M}"
        )

    @property
    def price_delta(self):
        if self.price_before is not None:
            return self.price_after - self.price_before
        return None

    @property
    def price_delta_pct(self):
        if self.price_before and self.price_before > 0:
            return round(
                float(self.price_after - self.price_before) / float(self.price_before) * 100, 2
            )
        return None
