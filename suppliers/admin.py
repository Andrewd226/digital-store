"""
suppliers/admin.py
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from suppliers.models import (
    Supplier,
    SupplierCatalogSync,
    SupplierCredential,
    SupplierStockHistory,
    SupplierStockRecord,
)

# ─── Supplier ─────────────────────────────────────────────────────────────────


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "code",
        "sync_method",
        "default_currency",
        "supplier_is_active",
        "priority",
        "sync_schedule",
    ]
    list_filter = ["sync_method", "supplier_is_active", "default_currency"]
    search_fields = ["name", "code", "api_url"]
    ordering = ["priority", "name"]
    readonly_fields = ["id"]
    prepopulated_fields = {"code": ("name",)}

    fieldsets = (
        (
            _("Основное"),
            {
                "fields": (
                    "id",
                    "name",
                    "code",
                    "sync_method",
                    "default_currency",
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
            _("Синхронизация"),
            {
                "fields": (
                    "sync_schedule",
                    "supplier_is_active",
                    "priority",
                ),
            },
        ),
    )


# ─── SupplierCredential ───────────────────────────────────────────────────────


@admin.register(SupplierCredential)
class SupplierCredentialAdmin(admin.ModelAdmin):
    list_display = ["supplier", "updated_at", "api_key_status", "api_secret_status"]
    search_fields = ["supplier__name", "supplier__code"]
    readonly_fields = ["id", "updated_at", "api_key_display", "api_secret_display"]

    fieldsets = (
        (
            _("Основное"),
            {
                "fields": (
                    "id",
                    "supplier",
                )
            },
        ),
        (
            _("Учётные данные"),
            {
                "fields": (
                    "api_key",
                    "api_secret",
                    "extra",
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

    @admin.display(description=_("Статус ключа"))
    def api_key_status(self, obj):
        return "✓" if obj.api_key else "✗"

    @admin.display(description=_("Статус секрета"))
    def api_secret_status(self, obj):
        return "✓" if obj.api_secret else "✗"


# ─── SupplierStockRecord ──────────────────────────────────────────────────────


@admin.register(SupplierStockRecord)
class SupplierStockRecordAdmin(admin.ModelAdmin):
    list_display = [
        "product",
        "supplier",
        "supplier_sku",
        "price",
        "currency",
        "num_available",
        "num_in_stock",
        "is_active",
        "updated_at",
    ]
    list_filter = [
        "supplier",
        "currency",
        "is_active",
    ]  # ← Исправлено: удалено product__is_available
    search_fields = [
        "product__title",
        "product__upc",
        "supplier__name",
        "supplier_sku",
    ]
    ordering = ["supplier", "product"]
    readonly_fields = ["id", "created_at", "updated_at"]
    date_hierarchy = "updated_at"

    fieldsets = (
        (
            _("Основное"),
            {
                "fields": (
                    "id",
                    "supplier",
                    "product",
                    "supplier_sku",
                )
            },
        ),
        (
            _("Цена и валюта"),
            {
                "fields": (
                    "price",
                    "currency",
                ),
            },
        ),
        (
            _("Остатки"),
            {
                "fields": (
                    "num_in_stock",
                    "num_allocated",
                    "num_available",
                ),
            },
        ),
        (
            _("Статус"),
            {
                "fields": (
                    "is_active",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    @admin.display(description=_("Доступно"))
    def num_available(self, obj):
        return obj.num_available

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("supplier", "product", "currency")


# ─── SupplierStockHistory ─────────────────────────────────────────────────────


@admin.register(SupplierStockHistory)
class SupplierStockHistoryAdmin(admin.ModelAdmin):
    list_display = [
        "snapshot_product_title",
        "snapshot_supplier_name",
        "change_type",
        "price_before_display",
        "price_after_display",
        "price_delta_display",
        "stock_before_display",
        "stock_after_display",
        "recorded_at",
    ]
    list_filter = ["change_type", "snapshot_supplier_name", "recorded_at"]
    search_fields = [
        "snapshot_product_title",
        "snapshot_supplier_name",
        "snapshot_supplier_sku",
    ]
    ordering = ["-recorded_at"]
    readonly_fields = [
        "id",
        "stock_record",
        "sync",
        "snapshot_supplier_name",
        "snapshot_product_title",
        "snapshot_product_upc",
        "snapshot_supplier_sku",
        "snapshot_currency_code",
        "price_before",
        "price_after",
        "price_delta_display",
        "price_delta_pct_display",
        "num_in_stock_before",
        "num_in_stock_after",
        "stock_delta_display",
        "change_type",
        "recorded_at",
    ]
    date_hierarchy = "recorded_at"

    fieldsets = (
        (
            _("Основное"),
            {
                "fields": (
                    "id",
                    "stock_record",
                    "sync",
                    "change_type",
                )
            },
        ),
        (
            _("Снимки данных"),
            {
                "fields": (
                    "snapshot_supplier_name",
                    "snapshot_product_title",
                    "snapshot_product_upc",
                    "snapshot_supplier_sku",
                    "snapshot_currency_code",
                ),
                "classes": ["collapse"],
            },
        ),
        (
            _("Цена"),
            {
                "fields": (
                    "price_before",
                    "price_after",
                    "price_delta_display",
                    "price_delta_pct_display",
                ),
            },
        ),
        (
            _("Остаток"),
            {
                "fields": (
                    "num_in_stock_before",
                    "num_in_stock_after",
                    "stock_delta_display",
                ),
            },
        ),
        (
            _("Время"),
            {
                "fields": ("recorded_at",),
            },
        ),
    )

    @admin.display(description=_("Цена до"))
    def price_before_display(self, obj):
        if obj.price_before is not None:
            return f"{obj.price_before:.6f} {obj.snapshot_currency_code}"
        return "—"

    @admin.display(description=_("Цена после"))
    def price_after_display(self, obj):
        return f"{obj.price_after:.6f} {obj.snapshot_currency_code}"

    @admin.display(description=_("Изменение цены"))
    def price_delta_display(self, obj):
        if obj.price_delta is not None:
            color = "green" if obj.price_delta > 0 else "red" if obj.price_delta < 0 else "gray"
            sign = "+" if obj.price_delta > 0 else ""
            return format_html(
                f'<span style="color: {color}; font-weight: bold;">{sign}{obj.price_delta:.6f}</span>'
            )
        return "—"

    @admin.display(description=_("Изменение цены %"))
    def price_delta_pct_display(self, obj):
        if obj.price_delta_pct is not None:
            color = (
                "green" if obj.price_delta_pct > 0 else "red" if obj.price_delta_pct < 0 else "gray"
            )
            sign = "+" if obj.price_delta_pct > 0 else ""
            return format_html(
                f'<span style="color: {color};">{sign}{obj.price_delta_pct:.2f}%</span>'
            )
        return "—"

    @admin.display(description=_("Остаток до"))
    def stock_before_display(self, obj):
        if obj.num_in_stock_before is not None:
            return str(obj.num_in_stock_before)
        return "—"

    @admin.display(description=_("Остаток после"))
    def stock_after_display(self, obj):
        return str(obj.num_in_stock_after)

    @admin.display(description=_("Изменение остатка"))
    def stock_delta_display(self, obj):
        if obj.num_in_stock_before is not None:
            delta = obj.num_in_stock_after - obj.num_in_stock_before
            color = "green" if delta > 0 else "red" if delta < 0 else "gray"
            sign = "+" if delta > 0 else ""
            return format_html(f'<span style="color: {color};">{sign}{delta}</span>')
        return "—"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("stock_record", "sync")


# ─── SupplierCatalogSync ──────────────────────────────────────────────────────


@admin.register(SupplierCatalogSync)
class SupplierCatalogSyncAdmin(admin.ModelAdmin):
    list_display = [
        "supplier",
        "status",
        "total_items",
        "created_items",
        "updated_items",
        "failed_items",
        "started_at",
        "finished_at",
        "duration_display",
    ]
    list_filter = ["status", "supplier", "triggered_by", "started_at"]
    search_fields = ["supplier__name", "supplier__code", "task_id", "error_log"]
    ordering = ["-started_at"]
    readonly_fields = [
        "id",
        "supplier",
        "status",
        "started_at",
        "finished_at",
        "task_id",
        "total_items",
        "created_items",
        "updated_items",
        "skipped_items",
        "failed_items",
        "duration_display",
        "triggered_by",
        "error_log",
    ]
    date_hierarchy = "started_at"

    fieldsets = (
        (
            _("Основное"),
            {
                "fields": (
                    "id",
                    "supplier",
                    "status",
                    "triggered_by",
                )
            },
        ),
        (
            _("Результаты"),
            {
                "fields": (
                    "total_items",
                    "created_items",
                    "updated_items",
                    "skipped_items",
                    "failed_items",
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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("supplier")
