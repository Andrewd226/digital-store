"""
suppliers/tasks.py

Celery-задачи синхронизации каталогов поставщиков.

Поддерживаются два режима запуска:
- Автоматический: sync_all_supplier_catalogs() — запускается по расписанию Celery Beat,
  обходит всех активных поставщиков.
- Ручной/точечный: sync_supplier_catalog(supplier_id) — запускает синхронизацию
  одного поставщика по id. Может быть вызвана из Django Admin или API.
"""

from __future__ import annotations

import logging

from celery import shared_task

from suppliers.service.dao import SupplierDAO
from suppliers.service.factory import build_sync_service

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def sync_supplier_catalog(self, supplier_id: int) -> dict:
    """
    Синхронизация каталога одного поставщика по id.

    Используется для:
    - ручного запуска из Django Admin / DRF endpoint
    - точечного обновления конкретного поставщика

    При ошибке задача повторяется до max_retries раз с задержкой default_retry_delay секунд.
    Возвращает словарь с итогами для удобства мониторинга в Celery Flower.
    """
    supplier_dao = SupplierDAO()
    supplier = supplier_dao.get_by_id(supplier_id)

    if supplier is None:
        logger.error("sync_supplier_catalog: поставщик id=%d не найден", supplier_id)
        return {"status": "skipped", "reason": "supplier_not_found", "supplier_id": supplier_id}

    if not supplier.sync_method:
        logger.warning(
            "sync_supplier_catalog: поставщик id=%d не имеет sync_method",
            supplier_id,
        )
        return {"status": "skipped", "reason": "no_sync_method", "supplier_id": supplier_id}

    logger.info("sync_supplier_catalog START [supplier=%s]", supplier.code)

    try:
        service = build_sync_service(supplier)
        result = service.run_sync()
        return {
            "status": "success",
            "supplier_id": supplier_id,
            "supplier_code": supplier.code,
            "sync_id": result.sync_id,
            "total_items": result.total_items,
            "created_items": result.created_items,
            "updated_items": result.updated_items,
            "skipped_items": result.skipped_items,
            "failed_items": result.failed_items,
        }
    except NotImplementedError as exc:
        logger.error(
            "sync_supplier_catalog: не реализован сервис для supplier=%s: %s",
            supplier.code,
            exc,
        )
        return {"status": "skipped", "reason": "not_implemented", "supplier_id": supplier_id}
    except Exception as exc:
        logger.exception(
            "sync_supplier_catalog FAILED [supplier=%s]", supplier.code
        )
        raise self.retry(exc=exc)


@shared_task
def sync_all_supplier_catalogs() -> dict:
    """
    Синхронизация каталогов всех активных поставщиков.

    Запускается по расписанию Celery Beat.
    Каждый поставщик обрабатывается в отдельной задаче sync_supplier_catalog,
    что обеспечивает независимость: ошибка одного поставщика не блокирует остальных.

    Возвращает сводку по запущенным задачам.
    """
    supplier_dao = SupplierDAO()
    active_suppliers = supplier_dao.get_active()

    if not active_suppliers:
        logger.info("sync_all_supplier_catalogs: нет активных поставщиков")
        return {"status": "skipped", "reason": "no_active_suppliers"}

    dispatched = []
    for supplier in active_suppliers:
        task = sync_supplier_catalog.delay(supplier.id)
        dispatched.append({"supplier_id": supplier.id, "supplier_code": supplier.code, "task_id": task.id})
        logger.info(
            "sync_all_supplier_catalogs: запущена задача [supplier=%s task_id=%s]",
            supplier.code,
            task.id,
        )

    return {"status": "dispatched", "tasks": dispatched}
