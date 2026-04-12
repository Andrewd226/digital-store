"""
catalogue/dao.py

Data Access Object для товаров каталога.
Все методы принимают и возвращают только DTO или скалярные значения.
"""

from __future__ import annotations

from catalogue.dto import ProductDTO
from catalogue.models import Product


class ProductDAO:
    """DAO для операций с товарами каталога."""

    @staticmethod
    def get_by_upc(upc: str | None) -> ProductDTO | None:
        """
        Получает товар по универсальному коду (UPC).
        Безопасно обрабатывает None и пустые строки.
        """
        if not upc:
            return None
        try:
            return ProductDTO.model_validate(Product.objects.get(upc=upc))
        except Product.DoesNotExist:
            return None

    @staticmethod
    def get_by_upc_list(upc_list: list[str]) -> list[ProductDTO]:
        """Возвращает список DTO товаров по списку UPC."""
        return [ProductDTO.model_validate(p) for p in Product.objects.filter(upc__in=upc_list)]
