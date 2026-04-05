"""
suppliers/service/base.py

Базовый класс сервиса. Работает исключительно с DTO и скалярами.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Generic, TypeVar

from suppliers.service.dao import SyncLogDAO
from suppliers.service.dto import SyncLogDTO, SyncStatsDTO

logger = logging.getLogger(__name__)
TDTO = TypeVar("TDTO")
TResult = TypeVar("TResult")


class BaseService(ABC, Generic[TDTO, TResult]):
    def __init__(self, supplier_code: str):
        self.supplier_code = supplier_code
        self.sync_log: SyncLogDTO | None = None
        self.stats = SyncStatsDTO()
        self.errors: list[str] = []

    @abstractmethod
    def fetch_data(self) -> Iterable[TDTO]:
        raise NotImplementedError

    @abstractmethod
    def process_item(self, item: TDTO) -> TResult:
        raise NotImplementedError

    def start_sync(self, triggered_by: str = "celery") -> SyncLogDTO:
        self.sync_log = SyncLogDAO.create_running(self.supplier_code, triggered_by)
        logger.info("Начало синхронизации: %s", self.supplier_code)
        return self.sync_log

    def complete_sync(self, status: str | None = None, error_log: str = "") -> SyncLogDTO:
        if not self.sync_log:
            raise RuntimeError("Синхронизация не начата")
        if status is None:
            if self.stats.failed == 0:
                status = "SUCCESS"
            elif self.stats.failed < self.stats.total:
                status = "PARTIAL"
            else:
                status = "FAILED"
        
        return SyncLogDAO.complete(self.sync_log.id, status, self.stats, error_log)

    def sync(self, triggered_by: str = "celery") -> SyncLogDTO:
        try:
            self.start_sync(triggered_by)
            for item in self.fetch_data():
                try:
                    result = self.process_item(item)
                    self._update_stats(result)
                    if result.failed and result.error_message:
                        self.errors.append(f"{getattr(item, 'supplier_sku', '?')}: {result.error_message}")
                        if len(self.errors) > 1000:
                            self.errors = self.errors[-1000:] + ["... (лимит логов)"]
                except Exception as e:
                    self.stats.failed += 1
                    self.errors.append(f"{getattr(item, 'supplier_sku', '?')}: {e}")
            return self.complete_sync(error_log="\n".join(self.errors))
        except Exception as e:
            logger.exception("Критическая ошибка синхронизации")
            return self.complete_sync(status="FAILED", error_log=str(e)[:65535])

    def _update_stats(self, result: TResult) -> None:
        if getattr(result, "created", False): self.stats.created += 1
        if getattr(result, "updated", False): self.stats.updated += 1
        if getattr(result, "skipped", False): self.stats.skipped += 1
        if getattr(result, "failed", False): self.stats.failed += 1

    def get_stats(self) -> SyncStatsDTO:
        return self.stats
