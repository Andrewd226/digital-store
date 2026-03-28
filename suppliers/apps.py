"""
suppliers/apps.py
"""
from django.apps import AppConfig


class SuppliersConfig(AppConfig):
    name = "suppliers"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Поставщики"

    def ready(self):
        from django.db.models.signals import post_save

        from suppliers.models import SupplierStockRecord
        from suppliers.signals import sync_master_stock_on_supplier_change

        post_save.connect(
            sync_master_stock_on_supplier_change,
            sender=SupplierStockRecord,
            dispatch_uid="sync_master_stock_on_supplier_change",
        )
