"""
currencies/dao.py

Data Access Objects для работы с курсами валют.
Единственный слой, который обращается к ORM напрямую.
Принимает и возвращает DTO — никаких ORM-объектов за пределами этого файла.
"""

import logging

from currencies.dto import RateDTO

logger = logging.getLogger(__name__)


class ExchangeRateDAO:
    """
    Сохранение курсов валют в БД.
    """

    def save_rates(self, source_id: int, rates: list[RateDTO]) -> int:
        """
        Сохраняет список RateDTO в БД.
        Для каждой пары:
            - обновляет ExchangeRate (UPDATE) или создаёт (INSERT)
            - всегда создаёт запись ExchangeRateHistory (append-only)
        Возвращает количество обновлённых/созданных курсов.
        """
        from core.models import Currency
        from currencies.models import CurrencyRateSource, ExchangeRate, ExchangeRateHistory

        if not rates:
            return 0

        source = CurrencyRateSource.objects.get(id=source_id)

        # Загружаем все нужные валюты одним запросом
        all_codes = {r.from_code for r in rates} | {r.to_code for r in rates}
        currency_map = {
            c.currency_code: c for c in Currency.objects.filter(currency_code__in=all_codes)
        }

        updated = 0

        for dto in rates:
            from_currency = currency_map.get(dto.from_code)
            to_currency = currency_map.get(dto.to_code)

            if not from_currency or not to_currency:
                logger.debug(
                    "Пропуск курса %s/%s — валюта не найдена в справочнике",
                    dto.from_code,
                    dto.to_code,
                )
                continue

            rate_record, created = ExchangeRate.objects.get_or_create(
                source=source,
                from_currency=from_currency,
                to_currency=to_currency,
                defaults={
                    "rate": dto.rate,
                    "rate_datetime": dto.rate_datetime,
                },
            )

            previous_rate = None if created else rate_record.rate

            if not created:
                rate_record.rate = dto.rate
                rate_record.rate_datetime = dto.rate_datetime
                rate_record.save(update_fields=["rate", "rate_datetime", "updated_at"])

            ExchangeRateHistory.objects.create(
                rate_record=rate_record,
                snapshot_source_name=source.name,
                snapshot_from_currency=from_currency.currency_code,
                snapshot_to_currency=to_currency.currency_code,
                rate=dto.rate,
                rate_datetime=dto.rate_datetime,
                previous_rate=previous_rate,
            )

            updated += 1

        return updated


class CurrencyRateSyncDAO:
    """
    Управление логом синхронизаций CurrencyRateSync.
    """

    def create_running(self, source_id: int) -> int:
        """
        Создаёт запись синхронизации со статусом RUNNING.
        Возвращает id созданной записи.
        """
        from currencies.models import CurrencyRateSource, CurrencyRateSync

        source = CurrencyRateSource.objects.get(id=source_id, is_active=True)
        sync = CurrencyRateSync.objects.create(
            source=source,
            status=CurrencyRateSync.Status.RUNNING,
        )
        return sync.id

    def mark_success(self, sync_id: int, rates_updated: int) -> None:
        from django.utils import timezone

        from currencies.models import CurrencyRateSync

        CurrencyRateSync.objects.filter(id=sync_id).update(
            status=CurrencyRateSync.Status.SUCCESS,
            rates_updated=rates_updated,
            finished_at=timezone.now(),
        )

    def mark_failed(self, sync_id: int, error_log: str) -> None:
        from django.utils import timezone

        from currencies.models import CurrencyRateSync

        CurrencyRateSync.objects.filter(id=sync_id).update(
            status=CurrencyRateSync.Status.FAILED,
            error_log=error_log,
            finished_at=timezone.now(),
        )

    def get_active_source_ids(self) -> list[int]:
        """Возвращает список id всех активных источников курсов."""
        from currencies.models import CurrencyRateSource

        return list(CurrencyRateSource.objects.filter(is_active=True).values_list("id", flat=True))

    def get_source_name(self, source_id: int) -> str:
        from currencies.models import CurrencyRateSource

        return CurrencyRateSource.objects.values_list("name", flat=True).get(id=source_id)
