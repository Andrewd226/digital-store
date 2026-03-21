from modeltranslation.translator import TranslationOptions, register

from .models import Currency


@register(Currency)
class CurrencyTranslationOptions(TranslationOptions):
    fields = ("name",)
