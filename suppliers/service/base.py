"""
suppliers/service/base.py

Абстрактный сервис синхронизации каталога поставщика.
Реализует шаблонный метод run_sync(), делегируя получение данных
конкретным подклассам через fetch_catalog().
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from catalogue.dao import ProductDAO
from suppliers.service.dao import (
    SupplierCatalogSyncDAO,
    SupplierDAO,
    SupplierStockHistoryDAO,
    SupplierStockRecordDAO,
)
from suppliers.service.dto import (
    CatalogSyncResultDTO,
    RawCatalogItemDTO,
    SupplierCredentialDTO,
    SupplierDTO,
)
from suppliers.service.sync import process_catalog

logger = logging.getLogger(__name__)


class AbstractSupplierSyncService(ABC):
    """
    Базовый класс сервиса синхронизации каталога поставщика.

    Подкласс обязан реализовать fetch_catalog() — получение сырых позиций
    от конкретного источника (REST API, FTP, ручная загрузка и т.д.).

    DAO инжектируются в конструктор, что обеспечивает тестируемость
    без обращения к БД.
    """

    def __init__(
        self,
        supplier: SupplierDTO,
        supplier_dao=SupplierDAO,
        stock_record_dao: SupplierStockRecordDAO,
        history_dao: SupplierStockHistoryDAO,
        sync_dao: SupplierCatalogSyncDAO,
        product_dao: ProductDAO,
    ) -> None:
        self.supplier = supplier
        self.supplier_dao = supplier_dao
        self.stock_record_dao = stock_record_dao
        self.history_dao = history_dao
        self.sync_dao = sync_dao
        self.product_dao = product_dao

    @abstractmethod
    def fetch_catalog(self) -> list[RawCatalogItemDTO]:
        """
        Получить сырые позиции каталога от источника поставщика.
        Реализуется в конкретном подклассе под каждый тип источника.
        """

    def run_sync(self) -> CatalogSyncResultDTO:
        """
        Шаблонный метод оркестрации синхронизации:
        1. Создать запись лога со статусом RUNNING.
        2. Получить сырые позиции через fetch_catalog().
        3. Обработать позиции через process_catalog() (внутри транзакции).
        4. Пометить лог как SUCCESS с итоговой статистикой.
        5. Вернуть CatalogSyncResultDTO.

        При любом исключении на шагах 2–3 помечает лог как FAILED и пробрасывает исключение.
        """
        sync_id = self.sync_dao.create_running(self.supplier.id)

        try:
            raw_items = self.fetch_catalog()
            logger.info(
                "fetch_catalog [supplier=%s]: получено %d позиций",
                self.supplier.code,
                len(raw_items),
            )

            result = process_catalog(
                supplier=self.supplier,
                raw_items=raw_items,
                sync_id=sync_id,
                stock_record_dao=self.stock_record_dao,
                history_dao=self.history_dao,
                product_dao=self.product_dao,
            )

            self.sync_dao.mark_success(sync_id, result)
            logger.info(
                "run_sync SUCCESS [supplier=%s]: "
                "total=%d created=%d updated=%d skipped=%d failed=%d",
                self.supplier.code,
                result.total_items,
                result.created_items,
                result.updated_items,
                result.skipped_items,
                result.failed_items,
            )
            return result

        except Exception as exc:
            error_log = f"{type(exc).__name__}: {exc}"
            logger.exception("run_sync FAILED [supplier=%s]", self.supplier.code)
            self.sync_dao.mark_failed(sync_id, error_log)
            raise
