"""
catalogue/dao.py

Data Access Object для товаров каталога.
Размещен в catalogue, так как Product — сущность этого домена.
"""

from __future__ import annotations

from django.db.models import QuerySet

from catalogue.models import Product


class ProductDAO:
    """DAO для операций с товарами каталога."""

    @staticmethod
    def get_by_upc(upc: str | None) -> Product | None:
        """
        Получает товар по универсальному коду (UPC).
        Безопасно обрабатывает None и пустые строки.
        """
        if not upc:
            return None
        try:
            return Product.objects.get(upc=upc)
        except Product.DoesNotExist:
            return None

    @staticmethod
    def get_by_upc_list(upc_list: list[str]) -> QuerySet[Product]:
        """Возвращает queryset товаров по списку UPC (использует SQL IN)."""
        return Product.objects.filter(upc__in=upc_list)
