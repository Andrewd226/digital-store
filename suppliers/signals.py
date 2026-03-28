"""
suppliers/signals.py
"""
def sync_master_stock_on_supplier_change(sender, instance, **kwargs):
    """
    При каждом сохранении SupplierStockRecord пересчитываем
    суммарный остаток в MasterStockRecord.
    Регистрируется через post_save.connect() в SuppliersConfig.ready() —
    @receiver со строковым sender не работает.
    """
    from catalogue.models import MasterStockRecord

    try:
        master = instance.product.master_stock
    except MasterStockRecord.DoesNotExist:
        return
    master.recalculate_stock()
    master.save(update_fields=["num_in_stock", "num_allocated", "suppliers_count", "updated_at"])
