"""
tests/suppliers/test_service_base.py

Тесты для базового сервиса синхронизации.
"""

import pytest

from suppliers.models import Supplier, SupplierCatalogSync
from suppliers.service.base import BaseService
from suppliers.service.dto import SupplierProductDTO, SyncResultDTO, SyncStatsDTO

# ─── Mock Service for Testing ─────────────────────────────────────────────────


class MockSyncService(BaseService[SupplierProductDTO, SyncResultDTO]):
    """Моковый сервис для тестирования базового класса."""

    def __init__(self, supplier: Supplier, fetch_data_result: list[SupplierProductDTO] = None):
        super().__init__(supplier)
        self._fetch_data_result = fetch_data_result or []
        self._process_item_result = SyncResultDTO(supplier_sku="test")

    def fetch_data(self) -> list[SupplierProductDTO]:
        return self._fetch_data_result

    def process_item(self, item: SupplierProductDTO) -> SyncResultDTO:
        return self._process_item_result


# ─── BaseService Tests ────────────────────────────────────────────────────────


class TestBaseService:
    """Тесты для BaseService."""

    def test_init(self, supplier_api):
        """Инициализация сервиса."""
        service = MockSyncService(supplier_api)
        assert service.supplier == supplier_api
        assert service.sync_record is None
        assert isinstance(service.stats, SyncStatsDTO)
        assert service.errors == []

    def test_start_sync(self, supplier_api):
        """Запуск синхронизации создаёт запись."""
        service = MockSyncService(supplier_api)
        sync_record = service.start_sync(triggered_by="pytest")

        assert sync_record is not None
        assert sync_record.supplier == supplier_api
        assert sync_record.status == SupplierCatalogSync.Status.RUNNING
        assert sync_record.triggered_by == "pytest"
        assert service.sync_record == sync_record

    def test_complete_sync_success(self, supplier_api):
        """Завершение синхронизации с успехом."""
        service = MockSyncService(supplier_api)
        service.start_sync()
        service.stats.total = 10
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
        """Завершение синхронизации частично."""
        service = MockSyncService(supplier_api)
        service.start_sync()
        service.stats.total = 10
        service.stats.created = 5
        service.stats.failed = 2

        sync_record = service.complete_sync()

        assert sync_record.status == SupplierCatalogSync.Status.PARTIAL

    def test_complete_sync_failed(self, supplier_api):
        """Завершение синхронизации с ошибкой."""
        service = MockSyncService(supplier_api)
        service.start_sync()
        service.stats.total = 10
        service.stats.failed = 10

        sync_record = service.complete_sync()

        assert sync_record.status == SupplierCatalogSync.Status.FAILED

    def test_complete_sync_without_start(self, supplier_api):
        """Завершение без запуска вызывает ошибку."""
        service = MockSyncService(supplier_api)

        with pytest.raises(RuntimeError, match="Синхронизация не была начата"):
            service.complete_sync()

    def test_sync_template_method(self, supplier_api, product_data_list):
        """Шаблонный метод sync обрабатывает все элементы."""
        service = MockSyncService(supplier_api, product_data_list)
        service._process_item_result = SyncResultDTO(supplier_sku="test", created=True)

        sync_record = service.sync(triggered_by="pytest")

        assert sync_record.status == SupplierCatalogSync.Status.SUCCESS
        assert service.stats.total == len(product_data_list)
        assert service.stats.created == len(product_data_list)

    def test_sync_with_errors(self, supplier_api, product_data_list):
        """Синхронизация с ошибками обработки."""
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

    def test_update_stats_created(self, supplier_api):
        """Обновление статистики для created."""
        service = MockSyncService(supplier_api)
        result = SyncResultDTO(supplier_sku="ART-001", created=True)
        service._update_stats(result)
        assert service.stats.created == 1

    def test_update_stats_updated(self, supplier_api):
        """Обновление статистики для updated."""
        service = MockSyncService(supplier_api)
        result = SyncResultDTO(supplier_sku="ART-001", updated=True)
        service._update_stats(result)
        assert service.stats.updated == 1

    def test_update_stats_skipped(self, supplier_api):
        """Обновление статистики для skipped."""
        service = MockSyncService(supplier_api)
        result = SyncResultDTO(supplier_sku="ART-001", skipped=True)
        service._update_stats(result)
        assert service.stats.skipped == 1

    def test_update_stats_failed(self, supplier_api):
        """Обновление статистики для failed."""
        service = MockSyncService(supplier_api)
        result = SyncResultDTO(supplier_sku="ART-001", failed=True)
        service._update_stats(result)
        assert service.stats.failed == 1

    def test_get_stats(self, supplier_api):
        """Получение статистики."""
        service = MockSyncService(supplier_api)
        service.stats.total = 10
        service.stats.created = 5
        stats = service.get_stats()
        assert stats.total == 10
        assert stats.created == 5
        assert isinstance(stats, SyncStatsDTO)
