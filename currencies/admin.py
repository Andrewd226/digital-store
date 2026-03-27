"""
currencies/admin.py
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from currencies.models import (
    CurrencyRateSource,
    CurrencyRateSourceCredential,
    CurrencyRateSync,
    ExchangeRate,
    ExchangeRateHistory,
)

# ─── CurrencyRateSource ───────────────────────────────────────────────────────


@admin.register(CurrencyRateSource)
class CurrencyRateSourceAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "source_type",
        "base_currency",
        "is_active",
        "priority",
        "sync_schedule",
    ]
    list_filter = ["source_type", "is_active"]
    search_fields = ["name", "api_url"]
    ordering = ["priority", "name"]
    readonly_fields = ["id"]

    fieldsets = (
        (
            _("Основное"),
            {
                "fields": (
                    "id",
                    "name",
                    "source_type",
                    "base_currency",
                )
            },
        ),
        (
            _("API конфигурация"),
            {
                "fields": (
                    "api_url",
                    "api_extra_config",
                ),
                "classes": ["collapse"],
            },
        ),
        (
            _("Отслеживаемые валюты"),
            {
                "fields": ("tracked_currencies",),
            },
        ),
        (
            _("Синхронизация"),
            {
                "fields": (
                    "sync_schedule",
                    "is_active",
                    "priority",
                ),
            },
        ),
    )

    filter_horizontal = ["tracked_currencies"]


# ─── CurrencyRateSourceCredential ─────────────────────────────────────────────


@admin.register(CurrencyRateSourceCredential)
class CurrencyRateSourceCredentialAdmin(admin.ModelAdmin):
    list_display = ["source", "updated_at"]
    search_fields = ["source__name"]
    readonly_fields = ["id", "updated_at", "api_key_display", "api_secret_display"]

    fieldsets = (
        (
            _("Основное"),
            {
                "fields": (
                    "id",
                    "source",
                )
            },
        ),
        (
            _("Учётные данные"),
            {
                "fields": (
                    "api_key",
                    "api_secret",
                    "api_key_display",
                    "api_secret_display",
                ),
                "classes": ["collapse"],
            },
        ),
        (
            _("Метаданные"),
            {
                "fields": ("updated_at",),
            },
        ),
    )

    @admin.display(description=_("API-ключ (зашифрован)"))
    def api_key_display(self, obj):
        if obj.api_key:
            return format_html('<span style="color: green;">✓ Установлен</span>')
        return format_html('<span style="color: red;">✗ Не установлен</span>')

    @admin.display(description=_("API-секрет (зашифрован)"))
    def api_secret_display(self, obj):
        if obj.api_secret:
            return format_html('<span style="color: green;">✓ Установлен</span>')
        return format_html('<span style="color: red;">✗ Не установлен</span>')


# ─── ExchangeRate ─────────────────────────────────────────────────────────────


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = [
        "from_currency",
        "to_currency",
        "rate",
        "source",
        "rate_datetime",
        "updated_at",
    ]
    list_filter = ["source", "from_currency", "to_currency"]
    search_fields = [
        "from_currency__currency_code",
        "to_currency__currency_code",
        "source__name",
    ]
    ordering = ["-updated_at"]
    readonly_fields = ["id", "updated_at"]
    date_hierarchy = "rate_datetime"

    fieldsets = (
        (
            _("Основное"),
            {
                "fields": (
                    "id",
                    "source",
                    "from_currency",
                    "to_currency",
                    "rate",
                )
            },
        ),
        (
            _("Время"),
            {
                "fields": (
                    "rate_datetime",
                    "updated_at",
                ),
            },
        ),
    )


# ─── ExchangeRateHistory ──────────────────────────────────────────────────────


@admin.register(ExchangeRateHistory)
class ExchangeRateHistoryAdmin(admin.ModelAdmin):
    list_display = [
        "snapshot_from_currency",
        "snapshot_to_currency",
        "rate",
        "previous_rate",
        "delta_display",
        "rate_datetime",
        "recorded_at",
        "snapshot_source_name",
    ]
    list_filter = ["snapshot_source_name", "recorded_at"]
    search_fields = [
        "snapshot_from_currency",
        "snapshot_to_currency",
        "snapshot_source_name",
    ]
    ordering = ["-recorded_at"]
    readonly_fields = [
        "id",
        "rate_record",
        "snapshot_source_name",
        "snapshot_from_currency",
        "snapshot_to_currency",
        "rate",
        "previous_rate",
        "delta_display",
        "delta_pct_display",
        "rate_datetime",
        "recorded_at",
    ]
    date_hierarchy = "recorded_at"

    fieldsets = (
        (
            _("Основное"),
            {
                "fields": (
                    "id",
                    "rate_record",
                    "snapshot_source_name",
                    "snapshot_from_currency",
                    "snapshot_to_currency",
                )
            },
        ),
        (
            _("Курсы"),
            {
                "fields": (
                    "rate",
                    "previous_rate",
                    "delta_display",
                    "delta_pct_display",
                ),
            },
        ),
        (
            _("Время"),
            {
                "fields": (
                    "rate_datetime",
                    "recorded_at",
                ),
            },
        ),
    )

    @admin.display(description=_("Изменение"))
    def delta_display(self, obj):
        if obj.delta is not None:
            color = "green" if obj.delta > 0 else "red" if obj.delta < 0 else "gray"
            sign = "+" if obj.delta > 0 else ""
            return format_html(f'<span style="color: {color};">{sign}{obj.delta:.6f}</span>')
        return "—"

    @admin.display(description=_("Изменение %"))
    def delta_pct_display(self, obj):
        if obj.delta_pct is not None:
            color = "green" if obj.delta_pct > 0 else "red" if obj.delta_pct < 0 else "gray"
            sign = "+" if obj.delta_pct > 0 else ""
            return format_html(f'<span style="color: {color};">{sign}{obj.delta_pct:.4f}%</span>')
        return "—"


# ─── CurrencyRateSync ─────────────────────────────────────────────────────────


@admin.register(CurrencyRateSync)
class CurrencyRateSyncAdmin(admin.ModelAdmin):
    list_display = [
        "source",
        "status",
        "rates_updated",
        "started_at",
        "finished_at",
        "duration_display",
    ]
    list_filter = ["status", "source", "started_at"]
    search_fields = ["source__name", "task_id", "error_log"]
    ordering = ["-started_at"]
    readonly_fields = [
        "id",
        "source",
        "status",
        "started_at",
        "finished_at",
        "task_id",
        "rates_updated",
        "duration_display",
        "error_log",
    ]
    date_hierarchy = "started_at"

    fieldsets = (
        (
            _("Основное"),
            {
                "fields": (
                    "id",
                    "source",
                    "status",
                )
            },
        ),
        (
            _("Результаты"),
            {
                "fields": (
                    "rates_updated",
                    "duration_display",
                ),
            },
        ),
        (
            _("Время"),
            {
                "fields": (
                    "started_at",
                    "finished_at",
                    "task_id",
                ),
            },
        ),
        (
            _("Ошибки"),
            {
                "fields": ("error_log",),
                "classes": ["collapse"],
            },
        ),
    )

    @admin.display(description=_("Длительность"))
    def duration_display(self, obj):
        if obj.duration_seconds is not None:
            return f"{obj.duration_seconds:.2f} сек"
        return "—"
