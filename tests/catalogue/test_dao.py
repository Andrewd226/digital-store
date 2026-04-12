"""
tests/catalogue/test_dao.py

Тесты для слоя доступа к данным (DAO) модуля catalogue.
"""

from __future__ import annotations

from catalogue.dao import ProductDAO
from catalogue.dto import ProductDTO


class TestProductDAO:
    """Тесты поиска товаров по UPC. Проверяют безопасность передачи параметров."""

    def test_get_by_upc(self, product_test):
        product = ProductDAO.get_by_upc("123456789012")
        assert product == ProductDTO.model_validate(product_test)

    def test_get_by_upc_not_found(self):
        product = ProductDAO.get_by_upc("NONEXISTENT123")
        assert product is None

    def test_get_by_upc_empty_string(self):
        """get_by_upc безопасно возвращает None при пустой строке."""
        product = ProductDAO.get_by_upc("")
        assert product is None

    def test_get_by_upc_list(self, product_test, product_test_2):
        products = ProductDAO.get_by_upc_list(["123456789012", "123456789013"])
        assert len(products) == 2
