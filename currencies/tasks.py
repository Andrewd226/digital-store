"""
currencies/tasks.py

Задачи синхронизации курсов валют.

Архитектура:
    sync_all_currency_rates()      — диспетчер, запускает задачу на каждый активный источник
    sync_currency_rates(source_id) — задача на один источник

Fetcher'ы:
    CoinCapFetcher — CoinCap Pro API (JSON, требует api_key), кросс-курсы через USD
    FixerFetcher   — заглушка для Fixer.io

Слои:
    Fetcher  → возвращает list[RateDTO]
    DAO      → сохраняет в БД, управляет логом синхронизации
    tasks    → оркестрирует fetcher + dao, не обращается к ORM напрямую
"""

import logging
import traceback
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation

import requests
from django.utils import timezone

from currencies.dao import CurrencyRateSyncDAO, ExchangeRateDAO
from currencies.dto import RateDTO, SyncResultDTO

logger = logging.getLogger(__name__)

_rate_dao = ExchangeRateDAO()
_sync_dao = CurrencyRateSyncDAO()


# ─── Base Fetcher ─────────────────────────────────────────────────────────────


class BaseFetcher(ABC):
    """
    Базовый класс для получения курсов из внешнего источника.
    Возвращает list[RateDTO].
    """

    def __init__(self, source):
        self.source = source
        self.api_url = source.api_url
        self.api_key = self._get_api_key()

    def _get_api_key(self) -> str:
        try:
            return self.source.credential.api_key
        except Exception:
            return ""

    @abstractmethod
    def fetch(self) -> list[RateDTO]:
        raise NotImplementedError

    def _get(self, url: str, **kwargs) -> requests.Response:
        response = requests.get(url, timeout=30, **kwargs)
        response.raise_for_status()
        return response

    def _tracked_codes(self) -> set:
        return set(
            self.source.tracked_currencies.values_list("currency_code", flat=True)
        )


# ─── CoinCap ──────────────────────────────────────────────────────────────────


class CoinCapFetcher(BaseFetcher):
    """
    CoinCap Pro API — https://pro.coincap.io/api-docs
    Эндпоинт: https://rest.coincap.io/v3/rates?ids=...
    Требует api_key в CurrencyRateSourceCredential.

    Все курсы в CoinCap выражены как количество USD за 1 единицу актива,
    т.е. rateUsd = сколько USD стоит 1 единица валюты.

    Кросс-курс между двумя не-USD валютами считается через доллар:
        rate(A→B) = rateUsd(A) / rateUsd(B)

    Маппинг currency_code → coincap_id задаётся в api_extra_config источника:
        {
            "ids": {
                "RUB": "russian-ruble",
                "USD": "united-states-dollar",
                "EUR": "euro",
                "BTC": "bitcoin",
                "ETH": "ethereum",
                "USDT": "tether"
            }
        }
    Если ids не заданы — fetcher ищет id автоматически через /v3/assets?search=...
    """

    RATES_URL = "https://rest.coincap.io/v3/rates"
    SEARCH_URL = "https://rest.coincap.io/v3/assets"

    def fetch(self) -> list[RateDTO]:
        ids_map = self._build_ids_map()
        if not ids_map:
            logger.warning("CoinCap [%s]: нет валют для синхронизации", self.source.name)
            return []

        ids_param = ",".join(ids_map.values())
        response = self._get(
            self.RATES_URL,
            params={"ids": ids_param},
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        data = response.json()

        # data["data"] — список объектов {"id": "bitcoin", "rateUsd": "85000.123", ...}
        items = data.get("data", [])

        # Инвертируем map: coincap_id → currency_code
        id_to_code = {v: k for k, v in ids_map.items()}

        # Собираем rateUsd для каждой валюты: currency_code → Decimal
        rates_usd: dict[str, Decimal] = {}
        for item in items:
            code = id_to_code.get(item.get("id", ""))
            if not code:
                continue
            try:
                rates_usd[code] = Decimal(str(item["rateUsd"]))
            except (InvalidOperation, KeyError):
                logger.warning("CoinCap: не удалось распарсить rateUsd для %s", item.get("id"))

        rate_datetime = timezone.now()
        results: list[RateDTO] = []

        # Генерируем все кросс-пары через USD
        codes = list(rates_usd.keys())
        for from_code in codes:
            for to_code in codes:
                if from_code == to_code:
                    continue
                try:
                    # rate(from→to) = rateUsd(from) / rateUsd(to)
                    rate = rates_usd[from_code] / rates_usd[to_code]
                    results.append(RateDTO(
                        from_code=from_code,
                        to_code=to_code,
                        rate=rate,
                        rate_datetime=rate_datetime,
                    ))
                except (InvalidOperation, ZeroDivisionError):
                    logger.warning(
                        "CoinCap: не удалось вычислить кросс-курс %s/%s",
                        from_code, to_code,
                    )

        return results

    def _build_ids_map(self) -> dict[str, str]:
        """
        Возвращает {currency_code: coincap_id}.
        Приоритет: api_extra_config["ids"] → tracked_currencies с автопоиском.
        """
        extra = self.source.api_extra_config or {}
        if "ids" in extra:
            return extra["ids"]

        codes = list(self._tracked_codes())
        ids_map = {}
        for code in codes:
            coincap_id = self._search_id(code)
            if coincap_id:
                ids_map[code] = coincap_id
            else:
                logger.warning("CoinCap: не найден id для валюты %s", code)
        return ids_map

    def _search_id(self, currency_code: str) -> str | None:
        """Поиск coincap_id по коду валюты через /v3/assets?search=..."""
        try:
            response = self._get(
                self.SEARCH_URL,
                params={"search": currency_code.lower()},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            items = response.json().get("data", [])
            if items:
                return items[0].get("id")
        except Exception as exc:
            logger.warning("CoinCap: ошибка поиска id для %s: %s", currency_code, exc)
        return None


# ─── Fixer (заглушка) ─────────────────────────────────────────────────────────


class FixerFetcher(BaseFetcher):
    """
    Заглушка для Fixer.io.
    Реализовать при необходимости.
    """

    def fetch(self) -> list[RateDTO]:
        raise NotImplementedError(
            f"Fetcher для источника '{self.source.name}' (fixer) не реализован."
        )


# ─── Fetcher registry ─────────────────────────────────────────────────────────

FETCHER_MAP = {
    "fixer": FixerFetcher,
    "custom_api": CoinCapFetcher,
}


def get_fetcher(source) -> BaseFetcher:
    fetcher_class = FETCHER_MAP.get(source.source_type)
    if not fetcher_class:
        raise ValueError(f"Нет fetcher'а для типа источника: {source.source_type}")
    return fetcher_class(source)


# ─── Celery tasks ─────────────────────────────────────────────────────────────


def sync_currency_rates(source_id: int) -> SyncResultDTO:
    """
    Синхронизация курсов для одного источника.
    Создаёт лог CurrencyRateSync, получает курсы через fetcher,
    сохраняет через DAO.

    После подключения Celery декорировать:
        @shared_task
        def sync_currency_rates(source_id: int) -> dict:
            return sync_currency_rates(source_id).model_dump()
    """
    from currencies.models import CurrencyRateSource

    try:
        source = CurrencyRateSource.objects.get(id=source_id, is_active=True)
    except CurrencyRateSource.DoesNotExist:
        logger.warning("CurrencyRateSource id=%s не найден или неактивен", source_id)
        return SyncResultDTO(status="skipped", source_id=source_id)

    sync_id = _sync_dao.create_running(source_id)

    try:
        fetcher = get_fetcher(source)
        rates: list[RateDTO] = fetcher.fetch()
        updated = _rate_dao.save_rates(source_id, rates)

        _sync_dao.mark_success(sync_id, updated)

        logger.info("Синхронизация курсов [%s]: обновлено %d курсов", source.name, updated)
        return SyncResultDTO(
            status="success",
            source_id=source_id,
            source_name=source.name,
            rates_updated=updated,
        )

    except Exception as exc:
        _sync_dao.mark_failed(sync_id, traceback.format_exc())
        logger.exception("Ошибка синхронизации курсов [%s]: %s", source.name, exc)
        return SyncResultDTO(
            status="failed",
            source_id=source_id,
            source_name=source.name,
            error=str(exc),
        )


def sync_all_currency_rates() -> list[SyncResultDTO]:
    """
    Диспетчер: запускает sync_currency_rates для каждого активного источника.

    После подключения Celery заменить вызов на:
        sync_currency_rates.delay(source_id)
    """
    source_ids = _sync_dao.get_active_source_ids()
    results: list[SyncResultDTO] = []

    for source_id in source_ids:
        logger.info("Запуск синхронизации курсов для source_id=%s", source_id)
        # После подключения Celery: sync_currency_rates.delay(source_id)
        result = sync_currency_rates(source_id)
        results.append(result)

    return results
