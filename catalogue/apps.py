from oscar.apps.catalogue.apps import CatalogueConfig as OscarCatalogueConfig


class CatalogueConfig(OscarCatalogueConfig):
    name = "catalogue"
    default_auto_field = "django.db.models.BigAutoField"
