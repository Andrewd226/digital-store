"""
tests/suppliers/test_service_sync.py

Тесты для сервисов синхронизации поставщиков.
"""

from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from suppliers.models import (
    Supplier,
    SupplierCatalogSync,
    SupplierStockHistory,
    SupplierStockRecord,
)
from suppliers.service.dto import SupplierProductDTO
from suppliers.service.sync import (
    APISupplierSyncService,
    ManualSupplierSyncService,
    get_sync_service,
    sync_supplier,
)

# ─── BaseSupplierSyncService Tests ────────────────────────────────────────────


class TestBaseSupplierSyncService:
    """Тесты для BaseSupplierSyncService."""

    def test_process_item_create_new(
        self,
        supplier_api,
        product_test,
        product_data_valid,
        rub,
    ):
        """Обработка товара создаёт новую запись."""
        service = APISupplierSyncService(supplier_api)
        service.sync_record = SupplierCatalogSync.objects.create(
            supplier=supplier_api,
            status=SupplierCatalogSync.Status.RUNNING,
        )

        result = service.process_item(product_data_valid)

        assert result.created is True
        assert result.updated is False
        assert SupplierStockRecord.objects.filter(
            supplier=supplier_api,
            product=product_test,
        ).exists()

    def test_process_item_update_existing(
        self,
        supplier_api,
        product_test,
        rub,
    ):
        """Обработка товара обновляет существующую запись."""
        SupplierStockRecord.objects.create(
            supplier=supplier_api,
            product=product_test,
            supplier_sku="ART-OLD",
            price=Decimal("500.00"),
            currency=rub,
            num_in_stock=50,
        )

        service = APISupplierSyncService(supplier_api)
        service.sync_record = SupplierCatalogSync.objects.create(
            supplier=supplier_api,
            status=SupplierCatalogSync.Status.RUNNING,
        )

        product_data = SupplierProductDTO(
            supplier_sku="ART-NEW",
            price=Decimal("999.99"),
            currency_code="RUB",
            num_in_stock=100,
            product_upc="123456789012",
        )

        result = service.process_item(product_data)

        assert result.updated is True
        assert result.price_changed is True
        assert result.stock_changed is True
        assert result.price_before == Decimal("500.00")
        assert result.price_after == Decimal("999.99")

    def test_process_item_no_changes(
        self,
        supplier_api,
        product_test,
        rub,
    ):
        """Обработка товара без изменений."""
        SupplierStockRecord.objects.create(
            supplier=supplier_api,
            product=product_test,
            supplier_sku="ART-001",
            price=Decimal("999.99"),
            currency=rub,
            num_in_stock=100,
        )

        service = APISupplierSyncService(supplier_api)
        service.sync_record = SupplierCatalogSync.objects.create(
            supplier=supplier_api,
            status=SupplierCatalogSync.Status.RUNNING,
        )

        product_data = SupplierProductDTO(
            supplier_sku="ART-001",
            price=Decimal("999.99"),
            currency_code="RUB",
            num_in_stock=100,
            product_upc="123456789012",
        )

        result = service.process_item(product_data)

        assert result.skipped is True
        assert result.created is False
        assert result.updated is False

    def test_process_item_currency_not_found(self, supplier_api, product_data_valid):
        """Обработка товара с несуществующей валютой."""
        service = APISupplierSyncService(supplier_api)
        service.sync_record = SupplierCatalogSync.objects.create(
            supplier=supplier_api,
            status=SupplierCatalogSync.Status.RUNNING,
        )

        product_data = SupplierProductDTO(
            supplier_sku="ART-001",
            price=Decimal("100"),
            currency_code="XXX",
            num_in_stock=10,
            product_upc="123456789012",
        )

        result = service.process_item(product_data)

        assert result.failed is True
        assert "Валюта не найдена" in result.error_message

    def test_process_item_product_not_found(self, supplier_api, rub):
        """Обработка товара с несуществующим продуктом."""
        service = APISupplierSyncService(supplier_api)
        service.sync_record = SupplierCatalogSync.objects.create(
            supplier=supplier_api,
            status=SupplierCatalogSync.Status.RUNNING,
        )

        product_data = SupplierProductDTO(
            supplier_sku="ART-001",
            price=Decimal("100"),
            currency_code="RUB",
            num_in_stock=10,
            product_upc="NONEXISTENT123",
        )

        result = service.process_item(product_data)

        assert result.skipped is True

    def test_history_record_created(
        self,
        supplier_api,
        product_test,
        rub,
    ):
        """История создаётся при изменении."""
        stock_record = SupplierStockRecord.objects.create(
            supplier=supplier_api,
            product=product_test,
            supplier_sku="ART-OLD",
            price=Decimal("500.00"),
            currency=rub,
            num_in_stock=50,
        )

        service = APISupplierSyncService(supplier_api)
        service.sync_record = SupplierCatalogSync.objects.create(
            supplier=supplier_api,
            status=SupplierCatalogSync.Status.RUNNING,
        )

        product_data = SupplierProductDTO(
            supplier_sku="ART-NEW",
            price=Decimal("999.99"),
            currency_code="RUB",
            num_in_stock=100,
            product_upc="123456789012",
        )

        service.process_item(product_data)

        assert SupplierStockHistory.objects.filter(
            stock_record=stock_record,
        ).exists()


# ─── APISupplierSyncService Tests ─────────────────────────────────────────────


class TestAPISupplierSyncService:
    """Тесты для APISupplierSyncService."""

    @patch("httpx.Client")
    def test_fetch_data_success(
        self,
        mock_client_class,
        supplier_api,
        supplier_credential,
        rub,
    ):
        """Загрузка данных через API успешна."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "items": [
                {
                    "sku": "ART-001",
                    "price": "999.99",
                    "currency": "RUB",
                    "stock": 100,
                    "upc": "123456789012",
                    "title": "Test Product",
                }
            ]
        }
        mock_response.raise_for_status = Mock()

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get = Mock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        service = APISupplierSyncService(supplier_api)
        data = service.fetch_data()

        assert len(data) == 1
        assert data[0].supplier_sku == "ART-001"
        assert data[0].price == Decimal("999.99")
        mock_client.get.assert_called_once()

    @patch("httpx.Client")
    def test_fetch_data_api_error(self, mock_client_class, supplier_api):
        """Загрузка данных через API с ошибкой."""
        import httpx

        mock_client = Mock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get = Mock(
            side_effect=httpx.HTTPStatusError(
                "Error",
                request=Mock(),
                response=Mock(status_code=500),
            )
        )
        mock_client_class.return_value = mock_client

        service = APISupplierSyncService(supplier_api)

        with pytest.raises(httpx.HTTPStatusError):
            service.fetch_data()

    def test_fetch_data_no_api_url(self, supplier_manual):
        """Загрузка данных без настроенного API URL."""
        supplier_manual.sync_method = Supplier.SyncMethod.API
        supplier_manual.api_url = ""
        supplier_manual.save()

        service = APISupplierSyncService(supplier_manual)

        with pytest.raises(ValueError, match="API URL не настроен"):
            service.fetch_data()


# ─── ManualSupplierSyncService Tests ──────────────────────────────────────────


class TestManualSupplierSyncService:
    """Тесты для ManualSupplierSyncService."""

    def test_fetch_data_returns_provided_data(self, supplier_manual, product_data_list):
        """Ручная синхронизация возвращает переданные данные."""
        service = ManualSupplierSyncService(supplier_manual, product_data_list)
        data = service.fetch_data()

        assert data == product_data_list
        assert len(data) == 3


# ─── Factory Function Tests ───────────────────────────────────────────────────


class TestGetSyncService:
    """Тесты для фабрики сервисов."""

    def test_get_api_service(self, supplier_api):
        """Фабрика создаёт API сервис."""
        service = get_sync_service(supplier_api)
        assert isinstance(service, APISupplierSyncService)

    def test_get_manual_service(self, supplier_manual, product_data_list):
        """Фабрика создаёт ручной сервис."""
        service = get_sync_service(supplier_manual, product_data_list)
        assert isinstance(service, ManualSupplierSyncService)

    def test_get_manual_service_no_data(self, supplier_manual):
        """Фабрика требует данные для ручного сервиса."""
        with pytest.raises(ValueError, match="необходимо передать products_data"):
            get_sync_service(supplier_manual)

    def test_get_unsupported_method(self, supplier_inactive):
        """Фабрика не поддерживает неподдерживаемые методы."""
        supplier_inactive.sync_method = Supplier.SyncMethod.FTP
        supplier_inactive.save()

        with pytest.raises(NotImplementedError):
            get_sync_service(supplier_inactive)


# ─── Helper Function Tests ────────────────────────────────────────────────────


class TestSyncSupplier:
    """Тесты для helper-функций."""

    def test_sync_supplier_success(self, supplier_manual, product_data_list):
        """Синхронизация поставщика успешна."""
        with patch("suppliers.service.sync.get_sync_service") as mock_get_service:
            mock_service = Mock()
            mock_service.sync.return_value = Mock(spec=SupplierCatalogSync)
            mock_get_service.return_value = mock_service

            sync_record = sync_supplier(supplier_manual.id, triggered_by="pytest")

            assert sync_record is not None
            mock_service.sync.assert_called_once_with(triggered_by="pytest")

    def test_sync_supplier_not_found(self):
        """Синхронизация несуществующего поставщика."""
        with pytest.raises(ValueError, match="не найден"):
            sync_supplier(99999)

    def test_sync_supplier_inactive(self, supplier_inactive):
        """Синхронизация неактивного поставщика вызывает ошибку."""
        with pytest.raises(ValueError, match="отключён"):
            sync_supplier(supplier_inactive.id)
