"""
catalogue/models.py
"""

from django.db import models
from oscar.apps.catalogue.abstract_models import AbstractProduct

from helpers.arithmetic import round_decimal

# ─── Форк Oscar Product ───────────────────────────────────────────────────────


class Product(AbstractProduct):
    """
    Форк Oscar Product.
    Данные не удаляются — мягкое отключение через is_active Oscar.
    """

    pass


# ─── 3.1 MasterCatalogSync ────────────────────────────────────────────────────


class MasterCatalogSync(models.Model):
    """
    Лог каждого обновления основного каталога товаров.
    Данные не удаляются.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Ожидает"
        RUNNING = "RUNNING", "Выполняется"
        SUCCESS = "SUCCESS", "Успешно"
        PARTIAL = "PARTIAL", "Частично"
        FAILED = "FAILED", "Ошибка"

    class SyncSource(models.TextChoices):
        MANUAL = "MANUAL", "Вручную"
        IMPORT = "IMPORT", "Импорт файла"
        API = "API", "Внешний API"
        CELERY = "CELERY", "Планировщик"

    status = models.TextField(
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Статус",
    )
    sync_source = models.TextField(
        choices=SyncSource.choices,
        default=SyncSource.CELERY,
        verbose_name="Источник синхронизации",
    )
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Начало")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Конец")
    task_id = models.TextField(blank=True, verbose_name="ID задачи Celery")
    triggered_by = models.TextField(blank=True, verbose_name="Инициатор")

    total_items = models.PositiveIntegerField(default=0, verbose_name="Всего")
    created_items = models.PositiveIntegerField(default=0, verbose_name="Создано")
    updated_items = models.PositiveIntegerField(default=0, verbose_name="Обновлено")
    failed_items = models.PositiveIntegerField(default=0, verbose_name="Ошибок")
    error_log = models.TextField(blank=True, verbose_name="Лог ошибок")

    class Meta:
        verbose_name = "Синхронизация основного каталога"
        verbose_name_plural = "Синхронизации основного каталога"
        ordering = ["-started_at"]

    def __str__(self):
        return (
            f"{self.get_sync_source_display()} | "
            f"{self.started_at:%Y-%m-%d %H:%M} | "
            f"{self.get_status_display()}"
        )

    @property
    def duration_seconds(self):
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


# ─── 3.2 MasterStockRecord ───────────────────────────────────────────────────


class MasterStockRecord(models.Model):
    """
    Суммарное наличие товара по всем активным поставщикам.
    Обновляется автоматически через сигнал в suppliers/signals.py.
    Данные не удаляются.
    """

    product = models.OneToOneField(
        "catalogue.Product",
        on_delete=models.PROTECT,
        related_name="master_stock",
        verbose_name="Товар",
    )
    # Суммарный остаток — обновляется через сигнал, не редактировать вручную
    num_in_stock = models.PositiveIntegerField(default=0, verbose_name="На складе (итого)")
    num_allocated = models.PositiveIntegerField(default=0, verbose_name="Зарезервировано (итого)")
    suppliers_count = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="Кол-во активных поставщиков",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    last_sync = models.ForeignKey(
        "MasterCatalogSync",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        verbose_name="Последняя синхронизация",
    )

    class Meta:
        verbose_name = "Основной остаток"
        verbose_name_plural = "Основные остатки"

    def __str__(self):
        return f"{self.product.title} | {self.num_in_stock} шт."

    @property
    def num_available(self):
        return max(0, self.num_in_stock - self.num_allocated)

    def recalculate_stock(self):
        """
        Пересчитывает суммарный остаток по всем активным поставщикам.
        Не сохраняет — только обновляет поля объекта.
        Диапазон цен не агрегируется здесь — поставщики работают в разных
        валютах, сравнивать сырые числа без конвертации некорректно.
        Диапазон цен доступен через product.master_prices по нужной валюте.
        """
        from django.db.models import Count, Sum

        result = self.product.supplier_stock_records.filter(is_active=True).aggregate(
            total_stock=Sum("num_in_stock"),
            total_allocated=Sum("num_allocated"),
            cnt=Count("id"),
        )
        self.num_in_stock = result["total_stock"] or 0
        self.num_allocated = result["total_allocated"] or 0
        self.suppliers_count = result["cnt"] or 0


# ─── 3.3 MasterPrice ─────────────────────────────────────────────────────────


class MasterPrice(models.Model):
    """
    Витринная цена товара в конкретной валюте.
    Один товар может иметь цены в нескольких валютах,
    но только одну цену в каждой валюте — (product, currency) уникальны.

    Запись создаётся только после первой синхронизации поставщика.
    price: null=False — не создавать запись без актуальной цены.
    Данные не удаляются.
    """

    product = models.ForeignKey(
        "catalogue.Product",
        on_delete=models.PROTECT,
        related_name="master_prices",
        verbose_name="Товар",
    )
    price = models.DecimalField(
        max_digits=50,
        decimal_places=25,
        null=False,
        blank=False,
        verbose_name="Цена",
    )
    currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        verbose_name="Валюта",
    )
    # Из какого SupplierStockRecord взята цена
    source_stock_record = models.ForeignKey(
        "suppliers.SupplierStockRecord",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        related_name="used_as_master_price",
        verbose_name="Источник цены (поставщик)",
    )
    # FK на курс + денормализованный снимок значения курса
    applied_exchange_rate = models.ForeignKey(
        "currencies.ExchangeRateHistory",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        verbose_name="Применённый курс (FK)",
    )
    applied_rate_value = models.DecimalField(
        max_digits=50,
        decimal_places=25,
        null=False,
        blank=False,
        verbose_name="Значение курса на момент пересчёта",
        help_text="Денормализованный снимок — не меняется при обновлении курса",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    last_sync = models.ForeignKey(
        "MasterCatalogSync",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        verbose_name="Последняя синхронизация",
    )

    class Meta:
        verbose_name = "Витринная цена"
        verbose_name_plural = "Витринные цены"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "currency"],
                name="unique_master_price_product_currency",
            ),
        ]
        # indexes не нужен — UniqueConstraint уже создаёт индекс в PostgreSQL

    def __str__(self):
        return f"{self.product.title} | {self.price} {self.currency.currency_code}"


# ─── 3.4 MasterPriceHistory ──────────────────────────────────────────────────


class MasterPriceHistory(models.Model):
    """
    Append-only история изменений витринной цены.
    Снимки полей сохраняют полный аудит навсегда.
    Данные не удаляются.
    """

    master_price = models.ForeignKey(
        "MasterPrice",
        on_delete=models.PROTECT,
        related_name="history",
        verbose_name="Витринная цена",
    )
    sync = models.ForeignKey(
        "MasterCatalogSync",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Синхронизация",
    )

    # NULL при первом создании записи
    price_before = models.DecimalField(
        max_digits=50,
        decimal_places=25,
        null=True,
        blank=True,
        verbose_name="Цена до",
    )
    price_after = models.DecimalField(
        max_digits=50,
        decimal_places=25,
        null=False,
        blank=False,
        verbose_name="Цена после",
    )

    class ChangeReason(models.TextChoices):
        CREATED = "CREATED", "Создана"
        SUPPLIER_PRICE = "SUPPLIER_PRICE", "Изменилась цена поставщика"
        EXCHANGE_RATE = "EXCHANGE_RATE", "Изменился курс валют"
        SUPPLIER_CHANGED = "SUPPLIER_CHANGED", "Смена поставщика-источника"
        MANUAL = "MANUAL", "Ручное изменение"

    change_reason = models.TextField(
        choices=ChangeReason.choices,
        verbose_name="Причина изменения",
        db_index=True,
    )

    # Снимки на момент записи
    snapshot_product_title = models.TextField(verbose_name="Товар (снимок)")
    snapshot_currency_code = models.TextField(verbose_name="Код валюты (снимок)")
    snapshot_supplier_name = models.TextField(blank=True, verbose_name="Поставщик (снимок)")
    snapshot_supplier_price = models.DecimalField(
        max_digits=50,
        decimal_places=25,
        null=True,
        blank=True,
        verbose_name="Цена поставщика (снимок)",
    )
    snapshot_source_currency = models.TextField(
        blank=True, verbose_name="Валюта поставщика (снимок)"
    )
    snapshot_applied_rate = models.DecimalField(
        max_digits=50,
        decimal_places=25,
        null=True,
        blank=True,
        verbose_name="Курс на момент изменения (снимок)",
    )
    recorded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время записи",
        db_index=True,
    )

    class Meta:
        verbose_name = "История витринной цены"
        verbose_name_plural = "История витринных цен"
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(
                fields=["master_price", "-recorded_at"],
                name="idx_master_price_history",
            ),
        ]

    def __str__(self):
        return (
            f"{self.snapshot_product_title} | "
            f"{self.get_change_reason_display()} | "
            f"{self.recorded_at:%Y-%m-%d %H:%M}"
        )

    @property
    def price_delta_pct(self):
        if self.price_before and self.price_before > 0:
            return round_decimal(
                (self.price_after - self.price_before) / self.price_before * 100, 2
            )
        return None


# ВСЕГДА В КОНЦЕ — после всех наших классов
from oscar.apps.catalogue.models import *  # noqa: E402, F401, F403
