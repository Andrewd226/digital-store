"""
suppliers/service/base.py

Базовый класс для всех сервисов приложения.
Содержит общую логику: логирование, транзакции, обработку ошибок.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, TypeVar

from django.db import transaction
from django.utils import timezone

from suppliers.service.dto import SyncStatsDTO
from suppliers.models import Supplier, SupplierCatalogSync
from suppliers.service.dao import SupplierCatalogSyncDAO

logger = logging.getLogger(__name__)

# Типы для дженериков
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
        self.sync_record: Optional[SupplierCatalogSync] = None
        self.stats = SyncStatsDTO()
        self.errors: List[str] = []

    @abstractmethod
    def fetch_data(self) -> List[TDTO]:
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
        logger.info(f"Начало синхронизации для поставщика {self.supplier.name} (ID={self.supplier.id})")
        return self.sync_record

    @transaction.atomic
    def complete_sync(
        self,
        status: Optional[str] = None,
        error_log: str = "",
    ) -> SupplierCatalogSync:
        """
        Завершает синхронизацию, обновляет статистику.
        """
        if not self.sync_record:
            raise RuntimeError("Синхронизация не была начата. Вызовите start_sync()")

        # Определяем статус
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
            f"Завершение синхронизации для {self.supplier.name}: "
            f"статус={status}, всего={self.stats.total}, "
            f"создано={self.stats.created}, обновлено={self.stats.updated}, "
            f"ошибок={self.stats.failed}"
        )

        return sync_record

    def sync(self, triggered_by: str = "celery") -> SupplierCatalogSync:
        """
        Основной метод синхронизации.
        Шаблонный метод (Template Method Pattern).
        """
        try:
            # Начинаем синхронизацию
            self.start_sync(triggered_by=triggered_by)

            # Загружаем данные
            items = self.fetch_data()
            self.stats.total = len(items)

            logger.debug(f"Загружено {len(items)} элементов для поставщика {self.supplier.name}")

            # Обрабатываем каждый элемент
            for item in items:
                try:
                    result = self.process_item(item)
                    self._update_stats(result)
                except Exception as e:
                    self.stats.failed += 1
                    error_msg = f"{getattr(item, 'supplier_sku', 'unknown')}: {str(e)}"
                    self.errors.append(error_msg)
                    logger.error(f"Ошибка обработки элемента: {error_msg}")

            # Завершаем синхронизацию
            self.complete_sync(error_log="\n".join(self.errors))

        except Exception as e:
            # Критическая ошибка
            logger.exception(f"Критическая ошибка синхронизации: {str(e)}")
            self.complete_sync(
                status=SupplierCatalogSync.Status.FAILED,
                error_log=f"CRITICAL: {str(e)}",
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
