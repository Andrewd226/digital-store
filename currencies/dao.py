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

    CHUNK_SIZE = 500

    def save_rates(self, source_id: int, rates: list[RateDTO]) -> int:
        """
        Массовое сохранение курсов чанками.

        Алгоритм:
            1. Загрузить все существующие ExchangeRate для данного источника одним запросом
            2. Разделить rates на to_create и to_update
            3. bulk_create новых записей чанками
            4. bulk_update существующих записей чанками
            5. bulk_create записей ExchangeRateHistory чанками (append-only)

        Возвращает общее количество обработанных курсов.
        """
        from django.utils import timezone

        from core.models import Currency
        from currencies.models import CurrencyRateSource, ExchangeRate, ExchangeRateHistory

        if not rates:
            return 0

        now = timezone.now()
        source = CurrencyRateSource.objects.get(id=source_id)

        # 1. Загружаем все нужные валюты одним запросом
        all_codes = {r.from_code for r in rates} | {r.to_code for r in rates}
        currency_map: dict[str, object] = {
            c.currency_code: c for c in Currency.objects.filter(currency_code__in=all_codes)
        }

        # 2. Загружаем все существующие записи для этого источника одним запросом
        #    Ключ: (from_currency_id, to_currency_id) → ExchangeRate
        existing_map: dict[tuple, ExchangeRate] = {
            (r.from_currency_id, r.to_currency_id): r
            for r in ExchangeRate.objects.filter(source=source)
        }

        to_create: list[ExchangeRate] = []
        to_update: list[ExchangeRate] = []
        history_items: list[ExchangeRateHistory] = []

        # dto_map нужен чтобы после bulk_create получить id новых записей
        # для истории: (from_currency_id, to_currency_id) → RateDTO
        new_dto_map: dict[tuple, RateDTO] = {}

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

            key = (from_currency.id, to_currency.id)
            existing = existing_map.get(key)

            if existing:
                # Запись существует — обновляем поля
                existing._previous_rate = existing.rate  # сохраняем для истории
                existing.rate = dto.rate
                existing.rate_datetime = dto.rate_datetime
                existing.updated_at = now
                to_update.append(existing)

                history_items.append(
                    ExchangeRateHistory(
                        rate_record=existing,
                        snapshot_source_name=source.name,
                        snapshot_from_currency=dto.from_code,
                        snapshot_to_currency=dto.to_code,
                        rate=dto.rate,
                        rate_datetime=dto.rate_datetime,
                        previous_rate=existing._previous_rate,
                    )
                )
            else:
                # Новая запись
                to_create.append(
                    ExchangeRate(
                        source=source,
                        from_currency=from_currency,
                        to_currency=to_currency,
                        rate=dto.rate,
                        rate_datetime=dto.rate_datetime,
                        updated_at=now,
                    )
                )
                new_dto_map[key] = dto

        # 3. bulk_update существующих записей чанками
        if to_update:
            for i in range(0, len(to_update), self.CHUNK_SIZE):
                ExchangeRate.objects.bulk_update(
                    to_update[i : i + self.CHUNK_SIZE],
                    fields=["rate", "rate_datetime", "updated_at"],
                )

        # 4. bulk_create новых записей чанками
        #    ignore_conflicts=True — пропускать дубли на случай race condition.
        #    ВАЖНО: при ignore_conflicts=True Django не гарантирует заполнение pk
        #    в возвращаемых объектах. Поэтому после bulk_create перечитываем
        #    свежесозданные записи из БД чтобы получить актуальные id для истории.
        for i in range(0, len(to_create), self.CHUNK_SIZE):
            ExchangeRate.objects.bulk_create(
                to_create[i : i + self.CHUNK_SIZE],
                ignore_conflicts=True,
            )

        # Перечитываем только что созданные записи (те у которых не было existing)
        new_keys = set(new_dto_map.keys())
        created_records: list[ExchangeRate] = [
            r for r in ExchangeRate.objects.filter(source=source)
            if (r.from_currency_id, r.to_currency_id) in new_keys
        ]

        # 5. Формируем историю для новых записей (id доступны после bulk_create)
        for record in created_records:
            key = (record.from_currency_id, record.to_currency_id)
            dto = new_dto_map.get(key)
            if dto:
                history_items.append(
                    ExchangeRateHistory(
                        rate_record=record,
                        snapshot_source_name=source.name,
                        snapshot_from_currency=dto.from_code,
                        snapshot_to_currency=dto.to_code,
                        rate=dto.rate,
                        rate_datetime=dto.rate_datetime,
                        previous_rate=None,
                    )
                )

        # 6. bulk_create истории чанками
        for i in range(0, len(history_items), self.CHUNK_SIZE):
            ExchangeRateHistory.objects.bulk_create(
                history_items[i : i + self.CHUNK_SIZE]
            )

        total = len(to_update) + len(created_records)
        logger.debug(
            "save_rates [%s]: создано=%d, обновлено=%d, история=%d",
            source.name,
            len(created_records),
            len(to_update),
            len(history_items),
        )
        return total


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

    def get_active_source(self, source_id: int):
        """
        Возвращает активный источник по id.
        Возвращает None если источник не найден или неактивен.
        """
        from currencies.models import CurrencyRateSource

        try:
            return CurrencyRateSource.objects.get(id=source_id, is_active=True)
        except CurrencyRateSource.DoesNotExist:
            return None
