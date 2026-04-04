"""
tests/suppliers/test_service_base.py

Тесты для базового класса сервиса синхронизации.
Проверяют транзакционность, сбор статистики и обработку ошибок.
"""

from __future__ import annotations

import pytest

from suppliers.models import Supplier, SupplierCatalogSync
from suppliers.service.base import BaseService
from suppliers.service.dto import SupplierProductDTO, SyncResultDTO, SyncStatsDTO


class MockSyncService(BaseService[SupplierProductDTO, SyncResultDTO]):
    """
    Моковый сервис для изолированного тестирования базовой логики.
    Переопределяет абстрактные методы, не затрагивая БД.
    """

    def __init__(
        self, supplier: Supplier, fetch_data_result: list[SupplierProductDTO] | None = None
    ):
        super().__init__(supplier)
        self._fetch_data_result = fetch_data_result or []
        self._process_item_result = SyncResultDTO(supplier_sku="mock")

    def fetch_data(self) -> list[SupplierProductDTO]:
        return self._fetch_data_result

    def process_item(self, item: SupplierProductDTO) -> SyncResultDTO:
        return self._process_item_result


class TestBaseService:
    """Тесты шаблона BaseService."""

    def test_init(self, supplier_api):
        """Корректная инициализация состояния сервиса."""
        service = MockSyncService(supplier_api)
        assert service.supplier == supplier_api
        assert service.sync_record is None
        assert isinstance(service.stats, SyncStatsDTO)
        assert service.errors == []

    def test_start_sync(self, supplier_api):
        """start_sync создаёт запись синхронизации в БД."""
        service = MockSyncService(supplier_api)
        sync_record = service.start_sync(triggered_by="pytest")

        assert sync_record is not None
        assert sync_record.supplier == supplier_api
        assert sync_record.status == SupplierCatalogSync.Status.RUNNING
        assert sync_record.triggered_by == "pytest"
        assert service.sync_record == sync_record

    def test_complete_sync_success(self, supplier_api):
        """Завершение с успешным статусом и корректной статистикой."""
        service = MockSyncService(supplier_api)
        service.start_sync()

        service.stats.created = 5
        service.stats.updated = 3
        service.stats.skipped = 2
        service.stats.failed = 0

        sync_record = service.complete_sync()

        assert sync_record.status == SupplierCatalogSync.Status.SUCCESS
        assert sync_record.finished_at is not None
        assert sync_record.total_items == 10
        assert sync_record.created_items == 5
        assert sync_record.updated_items == 3

    def test_complete_sync_partial(self, supplier_api):
        """Частичный успех: есть ошибки, но не все элементы упали."""
        service = MockSyncService(supplier_api)
        service.start_sync()
        service.stats.created = 5
        service.stats.failed = 2

        sync_record = service.complete_sync()
        assert sync_record.status == SupplierCatalogSync.Status.PARTIAL

    def test_complete_sync_failed(self, supplier_api):
        """Полный провал: все элементы обработаны с ошибкой."""
        service = MockSyncService(supplier_api)
        service.start_sync()
        service.stats.failed = 10

        sync_record = service.complete_sync()
        assert sync_record.status == SupplierCatalogSync.Status.FAILED

    def test_complete_sync_without_start(self, supplier_api):
        """Попытка завершения без запуска вызывает RuntimeError."""
        service = MockSyncService(supplier_api)
        with pytest.raises(RuntimeError, match="Синхронизация не была начата"):
            service.complete_sync()

    def test_sync_template_method(self, supplier_api, product_data_list):
        """Шаблонный метод sync обрабатывает весь список и собирает статистику."""
        service = MockSyncService(supplier_api, product_data_list)
        service._process_item_result = SyncResultDTO(supplier_sku="test", created=True)

        sync_record = service.sync(triggered_by="pytest")
        assert sync_record.status == SupplierCatalogSync.Status.SUCCESS
        assert service.stats.total == len(product_data_list)
        assert service.stats.created == len(product_data_list)

    def test_sync_with_errors(self, supplier_api, product_data_list):
        """
        Ошибки из result.error_message корректно собираются в service.errors.
        """
        service = MockSyncService(supplier_api, product_data_list)

        def process_with_error(item):
            result = SyncResultDTO(supplier_sku=item.supplier_sku)
            result.failed = True
            result.error_message = "Test error"
            return result

        service.process_item = process_with_error
        sync_record = service.sync()

        assert sync_record.status == SupplierCatalogSync.Status.FAILED
        assert service.stats.failed == len(product_data_list)
        assert len(service.errors) == len(product_data_list)
        assert "Test error" in service.errors[0]

    def test_update_stats(self, supplier_api):
        """_update_stats инкрементирует соответствующие счётчики."""
        service = MockSyncService(supplier_api)

        service._update_stats(SyncResultDTO(supplier_sku="1", created=True))
        assert service.stats.created == 1

        service._update_stats(SyncResultDTO(supplier_sku="2", updated=True))
        assert service.stats.updated == 1

        service._update_stats(SyncResultDTO(supplier_sku="3", skipped=True))
        assert service.stats.skipped == 1

        service._update_stats(SyncResultDTO(supplier_sku="4", failed=True))
        assert service.stats.failed == 1

    def test_get_stats(self, supplier_api):
        """get_stats возвращает актуальный экземпляр SyncStatsDTO."""
        service = MockSyncService(supplier_api)
        service.stats.created = 5
        service.stats.updated = 3

        stats = service.get_stats()
        assert stats.total == 8
        assert stats.created == 5
        assert isinstance(stats, SyncStatsDTO)

    def test_total_is_readonly(self, supplier_api):
        """
        total — расчётное поле (@property).
        Прямое присваивание должно вызывать AttributeError.
        """
        service = MockSyncService(supplier_api)
        with pytest.raises(AttributeError):
            service.stats.total = 100

    def test_total_calculation(self, supplier_api):
        """total всегда равен сумме четырёх счётчиков."""
        service = MockSyncService(supplier_api)
        service.stats.created = 10
        service.stats.updated = 5
        service.stats.skipped = 3
        service.stats.failed = 2

        assert service.stats.total == 20
