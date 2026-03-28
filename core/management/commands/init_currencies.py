"""
core/management/commands/init_currencies.py

Django management command для создания начальных данных:
- Валюты (RUB, USD, EUR, BTC, USDT, ETH, KZT, BYN)
- Источник курсов CoinCap
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Currency
from currencies.models import CurrencyRateSource


class Command(BaseCommand):
    help = "Создание начальных данных (валюты и источник курсов CoinCap)"

    CURRENCIES = [
        {
            "currency_code": "RUB",
            "name": "Russian Ruble",
            "currency_type": Currency.CurrencyType.FIAT,
            "symbol": "₽",
            "decimal_places": 2,
        },
        {
            "currency_code": "USD",
            "name": "US Dollar",
            "currency_type": Currency.CurrencyType.FIAT,
            "symbol": "$",
            "decimal_places": 2,
        },
        {
            "currency_code": "EUR",
            "name": "Euro",
            "currency_type": Currency.CurrencyType.FIAT,
            "symbol": "€",
            "decimal_places": 2,
        },
        {
            "currency_code": "BTC",
            "name": "Bitcoin",
            "currency_type": Currency.CurrencyType.CRYPTO,
            "symbol": "₿",
            "decimal_places": 8,
        },
        {
            "currency_code": "USDT",
            "name": "Tether",
            "currency_type": Currency.CurrencyType.CRYPTO,
            "symbol": "₮",
            "decimal_places": 6,
        },
        {
            "currency_code": "ETH",
            "name": "Ethereum",
            "currency_type": Currency.CurrencyType.CRYPTO,
            "symbol": "Ξ",
            "decimal_places": 8,
        },
        {
            "currency_code": "KZT",
            "name": "Kazakhstani Tenge",
            "currency_type": Currency.CurrencyType.FIAT,
            "symbol": "₸",
            "decimal_places": 2,
        },
        {
            "currency_code": "BYN",
            "name": "Belarusian Ruble",
            "currency_type": Currency.CurrencyType.FIAT,
            "symbol": "Br",
            "decimal_places": 2,
        },
    ]

    COINCAP_SOURCE = {
        "name": "CoinCap",
        "source_type": CurrencyRateSource.SourceType.CUSTOM_API,
        "api_url": "https://rest.coincap.io/v3/rates",
        "is_active": True,
        "priority": 100,
        "api_extra_config": {
            "ids": {
                "USD": "united-states-dollar",
                "RUB": "russian-ruble",
                "EUR": "euro",
                "BTC": "bitcoin",
                "USDT": "tether",
                "ETH": "ethereum",
                "KZT": "kazakhstani-tenge",
                "BYN": "belarusian-ruble",
            }
        },
    }

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🚀 Начало создания начальных данных..."))

        # ─── Создание валют ──────────────────────────────────────────────────────
        self.stdout.write("\n📊 Создание валют...")
        created_currencies = []

        for currency_data in self.CURRENCIES:
            currency, created = Currency.objects.get_or_create(
                currency_code=currency_data["currency_code"],
                defaults=currency_data,
            )
            if created:
                created_currencies.append(currency.currency_code)
                self.stdout.write(
                    self.style.SUCCESS(f"  ✅ Создана валюта: {currency.currency_code}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  ⚠️  Уже существует: {currency.currency_code}")
                )

        if created_currencies:
            self.stdout.write(
                self.style.SUCCESS(f"\n✓ Создано валют: {len(created_currencies)}")
            )

        # ─── Создание источника курсов ──────────────────────────────────────────
        self.stdout.write("\n📡 Создание источника курсов CoinCap...")

        usd = Currency.objects.get(currency_code="USD")

        source, created = CurrencyRateSource.objects.get_or_create(
            name=self.COINCAP_SOURCE["name"],
            defaults={
                "source_type": self.COINCAP_SOURCE["source_type"],
                "base_currency": usd,
                "api_url": self.COINCAP_SOURCE["api_url"],
                "is_active": self.COINCAP_SOURCE["is_active"],
                "priority": self.COINCAP_SOURCE["priority"],
                "api_extra_config": self.COINCAP_SOURCE["api_extra_config"],
            },
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"  ✅ Создан источник: {source.name}")
            )

            # Добавить отслеживаемые валюты
            for currency_data in self.CURRENCIES:
                currency = Currency.objects.get(
                    currency_code=currency_data["currency_code"]
                )
                source.tracked_currencies.add(currency)

            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✅ Добавлено отслеживаемых валют: {source.tracked_currencies.count()}"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(f"  ⚠️  Уже существует: {source.name}")
            )

            # Обновить отслеживаемые валюты
            for currency_data in self.CURRENCIES:
                currency = Currency.objects.get(
                    currency_code=currency_data["currency_code"]
                )
                source.tracked_currencies.add(currency)

            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✅ Обновлены отслеживаемые валюты: {source.tracked_currencies.count()}"
                )
            )

        # ─── Итог ────────────────────────────────────────────────────────────────
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("✅ Начальные данные созданы!"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        # Вывод сводки
        self.stdout.write("\n📊 Сводка:")
        self.stdout.write(f"  • Валют: {Currency.objects.count()}")
        self.stdout.write(
            f"  • Источников курсов: {CurrencyRateSource.objects.count()}"
        )

        self.stdout.write("\n📡 Источник CoinCap:")
        self.stdout.write(f"  • URL: {source.api_url}")
        self.stdout.write(f"  • Активен: {source.is_active}")
        self.stdout.write(f"  • Базовая валюта: {source.base_currency.currency_code}")
        self.stdout.write(
            f"  • Отслеживаемых валют: {source.tracked_currencies.count()}"
        )

        self.stdout.write("\n💡 Для синхронизации курсов выполните:")
        self.stdout.write(
            self.style.WARNING(
                f"  uv run python manage.py shell -c \"from currencies.tasks import sync_currency_rates; sync_currency_rates({source.id})\""
            )
        )