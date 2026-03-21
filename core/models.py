from django.core.validators import MinLengthValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class Currency(models.Model):
    """
    Справочник валют.
    Поддерживает фиатные и криптовалюты.
    Мультиязычность названия — через django-modeltranslation.
    Данные не удаляются.
    """

    class CurrencyType(models.TextChoices):
        FIAT = "FIAT", _("Фиатная валюта")
        CRYPTO = "CRYPTO", _("Криптовалюта")

    # ISO 4217 для фиатных (USD, EUR), тикер для крипто (BTC, ETH)
    currency_code = models.TextField(
        unique=True,
        validators=[MinLengthValidator(3)],
        verbose_name=_("Код валюты"),
    )
    currency_type = models.TextField(
        choices=CurrencyType.choices,
        default=CurrencyType.FIAT,
        verbose_name=_("Тип валюты"),
    )
    # Переводится через django-modeltranslation:
    # автоматически создаёт поля name_ru, name_en и т.д.
    name = models.TextField(
        verbose_name=_("Название"),
    )
    # Символ для отображения в UI: $, €, ₽, ₿
    symbol = models.TextField(
        blank=True,
        verbose_name=_("Символ"),
    )
    # Количество знаков после запятой для отображения
    decimal_places = models.PositiveSmallIntegerField(
        default=2,
        verbose_name=_("Знаков после запятой"),
    )

    class Meta:
        verbose_name = _("Валюта")
        verbose_name_plural = _("Валюты")
        ordering = ["currency_type", "currency_code"]

    def __str__(self):
        return f"{self.currency_code} — {self.name}"
