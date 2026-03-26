from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.models import Currency


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = [
        "currency_code",
        "name",
        "currency_type",
        "symbol",
        "decimal_places",
    ]
    list_filter = ["currency_type"]
    search_fields = ["currency_code", "name"]
    ordering = ["currency_type", "currency_code"]
    readonly_fields = ["id"]

    fieldsets = (
        (
            _("Основное"),
            {
                "fields": (
                    "id",
                    "currency_code",
                    "name",
                    "currency_type",
                )
            },
        ),
        (
            _("Отображение"),
            {
                "fields": (
                    "symbol",
                    "decimal_places",
                )
            },
        ),
    )
