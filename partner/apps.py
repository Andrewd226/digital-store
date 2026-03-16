from oscar.apps.partner.apps import PartnerConfig as OscarPartnerConfig


class PartnerConfig(OscarPartnerConfig):
    name = "partner"
    default_auto_field = "django.db.models.BigAutoField"
