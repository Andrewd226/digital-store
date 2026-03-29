"""
digital_store/settings.py

Django settings for digital_store project using Django 5.2.
"""
from pathlib import Path
from dynaconf import DjangoDynaconf

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

settings = DjangoDynaconf(
    __name__,
    SETTINGS_FILE_FOR_DYNACONF=BASE_DIR / "settings.yaml",
    lowercase_read=True,
)

# ─── Apps ─────────────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    "modeltranslation",  # ← must be BEFORE django.contrib.admin
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.contrib.flatpages",
    # Oscar
    "oscar.config.Shop",
    "oscar.apps.analytics.apps.AnalyticsConfig",
    "oscar.apps.checkout.apps.CheckoutConfig",
    "oscar.apps.address.apps.AddressConfig",
    "oscar.apps.shipping.apps.ShippingConfig",
    # 'oscar.apps.catalogue.apps.CatalogueConfig',
    "catalogue.apps.CatalogueConfig",  # ← fork
    "oscar.apps.catalogue.reviews.apps.CatalogueReviewsConfig",
    "oscar.apps.communication.apps.CommunicationConfig",
    # 'oscar.apps.partner.apps.PartnerConfig',
    "partner.apps.PartnerConfig",  # ← fork
    "oscar.apps.basket.apps.BasketConfig",
    "oscar.apps.payment.apps.PaymentConfig",
    "oscar.apps.offer.apps.OfferConfig",
    "oscar.apps.order.apps.OrderConfig",
    "oscar.apps.customer.apps.CustomerConfig",
    "oscar.apps.search.apps.SearchConfig",
    "oscar.apps.voucher.apps.VoucherConfig",
    "oscar.apps.wishlists.apps.WishlistsConfig",
    "oscar.apps.dashboard.apps.DashboardConfig",
    "oscar.apps.dashboard.reports.apps.ReportsDashboardConfig",
    "oscar.apps.dashboard.users.apps.UsersDashboardConfig",
    "oscar.apps.dashboard.orders.apps.OrdersDashboardConfig",
    "oscar.apps.dashboard.catalogue.apps.CatalogueDashboardConfig",
    "oscar.apps.dashboard.offers.apps.OffersDashboardConfig",
    "oscar.apps.dashboard.partners.apps.PartnersDashboardConfig",
    "oscar.apps.dashboard.pages.apps.PagesDashboardConfig",
    "oscar.apps.dashboard.ranges.apps.RangesDashboardConfig",
    "oscar.apps.dashboard.reviews.apps.ReviewsDashboardConfig",
    "oscar.apps.dashboard.vouchers.apps.VouchersDashboardConfig",
    "oscar.apps.dashboard.communications.apps.CommunicationsDashboardConfig",
    "oscar.apps.dashboard.shipping.apps.ShippingDashboardConfig",
    # Oscar dependencies
    "haystack",
    "widget_tweaks",
    "treebeard",
    "sorl.thumbnail",
    "django_tables2",
    # REST Framework
    "rest_framework",
    "rest_framework.authtoken",
    # Encryption
    "encrypted_fields",
    # Apps
    "core",
    "suppliers",
    "currencies",
]

# ─── Middleware ───────────────────────────────────────────────────────────────

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "oscar.apps.basket.middleware.BasketMiddleware",
    "django.contrib.flatpages.middleware.FlatpageFallbackMiddleware",
    # "partner.middleware.CurrencyMiddleware",
]

# ─── Haystack ──────────────────────────────────────────────────────────────────

HAYSTACK_CONNECTIONS = {
    "default": {"ENGINE": "haystack.backends.simple_backend.SimpleEngine"},
}

# ─── DRF ───────────────────────────────────────────────────────────────────────

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

# ─── Auth ─────────────────────────────────────────────────────────────────────-

AUTHENTICATION_BACKENDS = (
    "oscar.apps.customer.auth_backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
)

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

# AUTH_PASSWORD_VALIDATORS = [
#     {
#         'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
#     },
#     {
#         'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
#     },
#     {
#         'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
#     },
#     {
#         'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
#     },
# ]

# WSGI_APPLICATION = 'digital_store.wsgi.application'

# ─── Database ─────────────────────────────────────────────────────────────────

# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": settings.db.engine,
        "NAME": settings.db.database,
        "USER": settings.db.user,
        "PASSWORD": settings.db.password,
        "HOST": settings.db.host,
        "PORT": settings.db.port,
        "CONN_MAX_AGE": settings.db.conn_max_age,
        "OPTIONS": settings.db.options,
    },
}

# ─── Django Core Settings ──────────────────────────────────────────────────────

SITE_ID = settings.django.site_id
DEBUG = settings.django.debug
SALT_KEY = settings.django.salt_key
SECRET_KEY = settings.django.secret_key
ALLOWED_HOSTS = settings.django.allowed_hosts

SECURE_SSL_REDIRECT = settings.django.secure_ssl_redirect
SESSION_COOKIE_SECURE = settings.django.session_cookie_secure
CSRF_COOKIE_SECURE = settings.django.csrf_cookie_secure
USE_X_FORWARDED_HOST = settings.django.use_x_forwarded_host
USE_X_FORWARDED_PORT = settings.django.use_x_forwarded_port

# ─── Oscar ─────────────────────────────────────────────────────────────────────

OSCAR_DEFAULT_CURRENCY = settings.oscar.default_currency
OSCAR_SHOP_NAME = settings.oscar.shop_name

# ─── Localization ──────────────────────────────────────────────────────────────

# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = settings.django.language_code
LANGUAGES = settings.django.languages
TIME_ZONE = settings.django.time_zone
USE_I18N = settings.django.use_i18n
USE_TZ = settings.django.use_tz

# ─── Modeltranslation ──────────────────────────────────────────────────────────

MODELTRANSLATION_DEFAULT_LANGUAGE = settings.modeltranslation.default_language
MODELTRANSLATION_LANGUAGES = tuple(settings.modeltranslation.languages)

# ─── Static / Media ───────────────────────────────────────────────────────────
# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = settings.django.static_url
STATIC_ROOT = BASE_DIR / settings.django.static_root
STATICFILES_DIRS = [BASE_DIR / settings.django.staticfiles_dir]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = settings.django.media_url
MEDIA_ROOT = BASE_DIR / settings.django.media_root

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

# ─── Oscar defaults ────────────────────────────────────────────────────────────

from oscar.defaults import *  # noqa
