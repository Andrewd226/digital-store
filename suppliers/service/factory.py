"""
suppliers/service/factory.py

Фабрика сервисов синхронизации каталогов поставщиков.
Создаёт конкретную реализацию AbstractSupplierSyncService
в зависимости от sync_method поставщика.

При добавлении нового типа источника:
1. Создать подкласс AbstractSupplierSyncService в suppliers/service/
2. Зарегистрировать его в _SYNC_SERVICE_REGISTRY.
"""

from __future__ import annotations

from catalogue.dao import ProductDAO
from suppliers.service.base import AbstractSupplierSyncService
from suppliers.service.dao import (
    SupplierCatalogSyncDAO,
    SupplierDAO,
    SupplierStockHistoryDAO,
    SupplierStockRecordDAO,
)
from suppliers.service.dto import SupplierDTO

# Реестр: sync_method → класс сервиса
# Заполняется по мере добавления конкретных реализаций
_SYNC_SERVICE_REGISTRY: dict[str, type[AbstractSupplierSyncService]] = {}


def build_sync_service(supplier: SupplierDTO) -> AbstractSupplierSyncService:
    """
    Создаёт сервис синхронизации для указанного поставщика.

    Инжектирует все необходимые DAO.
    Поднимает NotImplementedError если sync_method не зарегистрирован.
    """
    service_class = _SYNC_SERVICE_REGISTRY.get(supplier.sync_method)
    if service_class is None:
        raise NotImplementedError(
            f"Сервис синхронизации для sync_method='{supplier.sync_method}' не зарегистрирован. "
            f"Зарегистрированные методы: {list(_SYNC_SERVICE_REGISTRY.keys())}"
        )

    return service_class(
        supplier=supplier,
        supplier_dao=SupplierDAO(),
        stock_record_dao=SupplierStockRecordDAO(),
        history_dao=SupplierStockHistoryDAO(),
        sync_dao=SupplierCatalogSyncDAO(),
        product_dao=ProductDAO(),
    )
