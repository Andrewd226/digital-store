"""
tests/suppliers/test_tasks.py

Тесты для Celery задач модуля suppliers.
"""

from unittest.mock import Mock, patch

import pytest

from suppliers.models import SupplierCatalogSync

# ─── Celery Task Tests ────────────────────────────────────────────────────────


class TestSupplierSyncTasks:
    """Тесты для задач синхронизации поставщиков."""

    @pytest.mark.skip(reason="Celery задачи ещё не реализованы")
    def test_sync_supplier_task(self, supplier_api):
        """Задача синхронизации одного поставщика."""
        from suppliers.tasks import sync_supplier_task

        with patch("suppliers.service.sync.sync_supplier") as mock_sync:
            mock_sync.return_value = Mock(spec=SupplierCatalogSync)
            result = sync_supplier_task.delay(supplier_api.id)

            assert result is not None
            mock_sync.assert_called_once()

    @pytest.mark.skip(reason="Celery задачи ещё не реализованы")
    def test_sync_all_suppliers_task(self, supplier_api, supplier_manual):
        """Задача синхронизации всех активных поставщиков."""
        from suppliers.tasks import sync_all_suppliers_task

        with patch("suppliers.service.sync.sync_all_active_suppliers") as mock_sync:
            mock_sync.return_value = [Mock(spec=SupplierCatalogSync)]
            result = sync_all_suppliers_task.delay()

            assert result is not None
            mock_sync.assert_called_once()

    @pytest.mark.skip(reason="Celery задачи ещё не реализованы")
    def test_sync_supplier_inactive(self, supplier_inactive):
        """Задача синхронизации неактивного поставщика."""
        from suppliers.tasks import sync_supplier_task

        with pytest.raises(ValueError):
            sync_supplier_task.delay(supplier_inactive.id)


# ─── Celery Beat Schedule Tests ───────────────────────────────────────────────


class TestCeleryBeatSchedule:
    """Тесты для расписания Celery Beat."""

    @pytest.mark.skip(reason="Celery задачи ещё не реализованы")
    def test_sync_schedule_from_model(self, supplier_api):
        """Расписание синхронизации из модели поставщика."""
        assert supplier_api.sync_schedule == "0 6 * * *"

    @pytest.mark.skip(reason="Celery задачи ещё не реализованы")
    def test_crontab_parsing(self):
        """Парсинг cron-расписания."""
        from datetime import datetime

        from croniter import croniter

        cron = croniter("0 6 * * *", datetime.now())
        next_run = cron.get_next(datetime)
        assert next_run.hour == 6
        assert next_run.minute == 0
