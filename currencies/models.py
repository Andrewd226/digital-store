"""
currencies/models.py
"""

from django.db import models
from encrypted_fields.fields import EncryptedCharField
from helpers.arithmetic import round_decimal

# ─── 2.1 CurrencyRateSource ───────────────────────────────────────────────────


class CurrencyRateSource(models.Model):
    """
    Источник курсов валют: ЦБ РФ, ECB, OpenExchangeRates и т.д.
    Данные не удаляются — мягкое отключение через is_active = False.
    """

    class SourceType(models.TextChoices):
        CBR = "cbr", "ЦБ РФ"
        ECB = "ecb", "Европейский ЦБ"
        OPEN_ER = "open_er", "OpenExchangeRates"
        FIXER = "fixer", "Fixer.io"
        CUSTOM_API = "custom_api", "Кастомный API"

    name = models.TextField(unique=True, verbose_name="Название")
    source_type = models.TextField(
        choices=SourceType.choices,
        verbose_name="Тип источника",
    )
    api_url = models.TextField(blank=True, verbose_name="URL API")
    base_currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        verbose_name="Базовая валюта",
        help_text="У ЦБ РФ — RUB, у ECB — EUR",
    )
    tracked_currencies = models.ManyToManyField(
        "core.Currency",
        related_name="tracked_by_sources",
        blank=True,
        verbose_name="Отслеживаемые валюты",
    )
    api_extra_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Доп. конфигурация API",
        help_text=('Для CoinCap: {"ids": {"USD": "united-states-dollar", "RUB": "russian-ruble"}}'),
    )
    sync_schedule = models.TextField(
        default="0 9 * * 1-5",
        verbose_name="Расписание (cron)",
        help_text='"0 9 * * 1-5" — в 09:00 по рабочим дням',
    )
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    priority = models.PositiveSmallIntegerField(
        default=100,
        verbose_name="Приоритет",
        help_text="При конфликте используется источник с меньшим значением",
    )

    class Meta:
        verbose_name = "Источник курсов валют"
        verbose_name_plural = "Источники курсов валют"
        ordering = ["priority", "name"]

    def __str__(self):
        status = "" if self.is_active else " [отключён]"
        return f"{self.name} ({self.base_currency.currency_code}){status}"


# ─── 2.2 CurrencyRateSourceCredential ────────────────────────────────────────


class CurrencyRateSourceCredential(models.Model):
    """
    API-ключи источника курсов. Хранятся зашифрованными.
    Данные не удаляются.
    """

    source = models.OneToOneField(
        "CurrencyRateSource",
        on_delete=models.PROTECT,
        related_name="credential",
        verbose_name="Источник",
    )
    api_key = EncryptedCharField(max_length=512, blank=True, verbose_name="API-ключ")
    api_secret = EncryptedCharField(max_length=512, blank=True, verbose_name="API-секрет")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Учётные данные источника курсов"
        verbose_name_plural = "Учётные данные источников курсов"
        default_permissions = ("view", "change")

    def __str__(self):
        return f"Credentials: {self.source.name}"


# ─── 2.3 ExchangeRate ─────────────────────────────────────────────────────────


class ExchangeRate(models.Model):
    """
    Актуальный курс пары валют от конкретного источника.
    Одна запись = одна пара = один источник.
    При обновлении: UPDATE этой записи + INSERT в ExchangeRateHistory.
    Данные не удаляются.
    """

    source = models.ForeignKey(
        "CurrencyRateSource",
        on_delete=models.PROTECT,
        related_name="rates",
        verbose_name="Источник",
    )
    from_currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="rates_from_currency",
        verbose_name="Из валюты",
    )
    to_currency = models.ForeignKey(
        "core.Currency",
        on_delete=models.PROTECT,
        related_name="rates_to_currency",
        verbose_name="В валюту",
    )
    rate = models.DecimalField(
        max_digits=50,
        decimal_places=25,
        null=False,
        blank=False,
        verbose_name="Курс",
        help_text="Сколько to_currency за 1 from_currency",
    )
    rate_datetime = models.DateTimeField(verbose_name="Дата и время курса")
    updated_at = models.DateTimeField(verbose_name="Обновлён")

    class Meta:
        verbose_name = "Актуальный курс валют"
        verbose_name_plural = "Актуальные курсы валют"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "from_currency", "to_currency"],
                name="unique_rate_per_source",
            ),
            models.CheckConstraint(
                condition=~models.Q(from_currency=models.F("to_currency")),
                name="exchange_rate_different_currencies",
            ),
        ]
        indexes = [
            models.Index(
                fields=["from_currency", "to_currency"],
                name="idx_currency_pair",
            ),
        ]

    def __str__(self):
        return (
            f"{self.from_currency.currency_code}/"
            f"{self.to_currency.currency_code} = {self.rate} "
            f"[{self.source.name}]"
        )


# ─── 2.4 ExchangeRateHistory ──────────────────────────────────────────────────


class ExchangeRateHistory(models.Model):
    """
    Append-only история курсов валют.
    FK → PROTECT: физическое удаление невозможно по правилам проекта.
    Снимки полей сохраняют полный контекст навсегда.
    Данные не удаляются.
    """

    rate_record = models.ForeignKey(
        "ExchangeRate",
        on_delete=models.PROTECT,
        related_name="history",
        verbose_name="Запись курса",
    )

    # Снимки — сохраняют контекст навсегда
    snapshot_source_name = models.TextField(verbose_name="Источник (снимок)")
    snapshot_from_currency = models.TextField(verbose_name="Из валюты (снимок)")
    snapshot_to_currency = models.TextField(verbose_name="В валюту (снимок)")

    rate = models.DecimalField(
        max_digits=50,
        decimal_places=25,
        null=False,
        blank=False,
        verbose_name="Курс",
    )
    rate_datetime = models.DateTimeField(verbose_name="Дата и время курса")
    # NULL при первой записи
    previous_rate = models.DecimalField(
        max_digits=50,
        decimal_places=25,
        null=True,
        blank=True,
        verbose_name="Предыдущий курс",
    )
    recorded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время записи",
        db_index=True,
    )

    class Meta:
        verbose_name = "История курсов валют"
        verbose_name_plural = "История курсов валют"
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(
                fields=["snapshot_from_currency", "snapshot_to_currency", "-rate_datetime"],
                name="idx_rate_history_pair_date",
            ),
            models.Index(
                fields=["snapshot_source_name", "-recorded_at"],
                name="idx_rate_history_source",
            ),
        ]

    def __str__(self):
        return (
            f"{self.snapshot_from_currency}/{self.snapshot_to_currency} = {self.rate} | "
            f"{self.rate_datetime:%Y-%m-%d %H:%M:%S} | {self.snapshot_source_name}"
        )

    @property
    def delta(self):
        if self.previous_rate is not None:
            return self.rate - self.previous_rate
        return None

    @property
    def delta_pct(self):
        if self.previous_rate and self.previous_rate > 0:
            return round_decimal((self.rate - self.previous_rate) / self.previous_rate * 100, 2)
        return None


# ─── 2.5 CurrencyRateSync ─────────────────────────────────────────────────────


class CurrencyRateSync(models.Model):
    """
    Лог каждого запуска обновления курсов.
    Данные не удаляются.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        RUNNING = "running", "Выполняется"
        SUCCESS = "success", "Успешно"
        FAILED = "failed", "Ошибка"

    source = models.ForeignKey(
        "CurrencyRateSource",
        on_delete=models.PROTECT,
        related_name="syncs",
        verbose_name="Источник",
    )
    status = models.TextField(
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Статус",
    )
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Начало")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Конец")
    task_id = models.TextField(blank=True, verbose_name="ID задачи Celery")
    rates_updated = models.PositiveIntegerField(default=0, verbose_name="Курсов обновлено")
    error_log = models.TextField(blank=True, verbose_name="Лог ошибок")

    class Meta:
        verbose_name = "Синхронизация курсов"
        verbose_name_plural = "Синхронизации курсов"
        ordering = ["-started_at"]
        indexes = [
            models.Index(
                fields=["source", "-started_at"],
                name="idx_currency_sync_source",
            ),
        ]

    def __str__(self):
        return (
            f"{self.source.name} | {self.started_at:%Y-%m-%d %H:%M} | {self.get_status_display()}"
        )

    @property
    def duration_seconds(self):
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None
