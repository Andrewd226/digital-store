"""
suppliers/service/base.py

Базовый класс для всех сервисов приложения.
Содержит общую логику: логирование, транзакции, обработку ошибок.
"""

import logging
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from django.db import transaction

from suppliers.models import Supplier, SupplierCatalogSync
from suppliers.service.dao import SupplierCatalogSyncDAO
from suppliers.service.dto import SyncStatsDTO

logger = logging.getLogger(__name__)

TDTO = TypeVar("TDTO")
TResult = TypeVar("TResult")


class BaseService(ABC, Generic[TDTO, TResult]):
    """
    Базовый класс для всех сервисов.

    Предоставляет:
    - Транзакционность операций
    - Логирование
    - Обработку ошибок
    - Статистику выполнения
    """

    def __init__(self, supplier: Supplier):
        self.supplier = supplier
        self.sync_record: SupplierCatalogSync | None = None
        self.stats = SyncStatsDTO()
        self.errors: list[str] = []

    @abstractmethod
    def fetch_data(self) -> list[TDTO]:
        """
        Загружает данные от источника.
        Должен быть реализован в наследнике.
        """
        raise NotImplementedError("Метод fetch_data должен быть реализован в наследнике")

    @abstractmethod
    def process_item(self, item: TDTO) -> TResult:
        """
        Обрабатывает один элемент данных.
        Должен быть реализован в наследнике.
        """
        raise NotImplementedError("Метод process_item должен быть реализован в наследнике")

    @transaction.atomic
    def start_sync(self, triggered_by: str = "celery") -> SupplierCatalogSync:
        """
        Создаёт запись о начале синхронизации.
        """
        self.sync_record = SupplierCatalogSyncDAO.create_running(
            supplier=self.supplier,
            triggered_by=triggered_by,
        )
        logger.info(
            "Начало синхронизации для поставщика %s (ID=%s)",
            self.supplier.name,
            self.supplier.id,
        )
        return self.sync_record

    @transaction.atomic
    def complete_sync(
        self,
        status: str | None = None,
        error_log: str = "",
    ) -> SupplierCatalogSync:
        """
        Завершает синхронизацию, обновляет статистику.
        """
        if not self.sync_record:
            raise RuntimeError("Синхронизация не была начата. Вызовите start_sync()")

        if status is None:
            if self.stats.failed == 0:
                status = SupplierCatalogSync.Status.SUCCESS
            elif self.stats.failed < self.stats.total:
                status = SupplierCatalogSync.Status.PARTIAL
            else:
                status = SupplierCatalogSync.Status.FAILED

        sync_record = SupplierCatalogSyncDAO.complete(
            sync_record=self.sync_record,
            status=status,
            total_items=self.stats.total,
            created_items=self.stats.created,
            updated_items=self.stats.updated,
            skipped_items=self.stats.skipped,
            failed_items=self.stats.failed,
            error_log=error_log,
        )

        logger.info(
            "Завершение синхронизации для %s: статус=%s, всего=%s, "
            "создано=%s, обновлено=%s, ошибок=%s",
            self.supplier.name,
            status,
            self.stats.total,
            self.stats.created,
            self.stats.updated,
            self.stats.failed,
        )

        return sync_record

    def sync(self, triggered_by: str = "celery") -> SupplierCatalogSync:
        """
        Основной метод синхронизации.
        Шаблонный метод (Template Method Pattern).
        """
        try:
            self.start_sync(triggered_by=triggered_by)

            items = self.fetch_data()

            logger.debug(
                "Загружено %d элементов для поставщика %s",
                len(items),
                self.supplier.name,
            )

            for item in items:
                try:
                    result = self.process_item(item)
                    self._update_stats(result)
                    if result.failed and result.error_message:
                        error_msg = f"{getattr(item, 'supplier_sku', 'unknown')}: {result.error_message}"
                        self.errors.append(error_msg)
                        logger.error("Ошибка обработки элемента: %s", error_msg)
                except Exception as e:
                    self.stats.failed += 1
                    error_msg = f"{getattr(item, 'supplier_sku', 'unknown')}: {e}"
                    self.errors.append(error_msg)
                    logger.error("Исключение при обработке элемента: %s", error_msg)

            self.complete_sync(error_log="\n".join(self.errors))

        except Exception as e:
            logger.exception("Критическая ошибка синхронизации: %s", e)
            self.complete_sync(
                status=SupplierCatalogSync.Status.FAILED,
                error_log=f"CRITICAL: {e}",
            )
            raise

        return self.sync_record

    def _update_stats(self, result: TResult) -> None:
        """
        Обновляет статистику на основе результата обработки.
        Ожидает, что результат имеет атрибуты created/updated/skipped/failed.
        """
        if hasattr(result, "created") and result.created:
            self.stats.created += 1
        if hasattr(result, "updated") and result.updated:
            self.stats.updated += 1
        if hasattr(result, "skipped") and result.skipped:
            self.stats.skipped += 1
        if hasattr(result, "failed") and result.failed:
            self.stats.failed += 1

    def get_stats(self) -> SyncStatsDTO:
        """Возвращает текущую статистику."""
        return self.stats
