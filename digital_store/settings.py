"""
digital_store/settings.py

Django settings for digital_store project using Django 5.2.
"""
from pathlib import Path
from dynaconf import Dynaconf

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

_settings = Dynaconf(
    settings_file=BASE_DIR / "settings.yaml",
    env_switcher="ENV_FOR_DYNACONF",
    environments=True,
    merge_enabled=True,
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

# ─── Templates ────────────────────────────────────────────────────────────────

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "oscar.apps.search.context_processors.search_form",
                "oscar.apps.checkout.context_processors.checkout",
                "oscar.apps.communication.notifications.context_processors.notifications",
                "oscar.core.context_processors.metadata",
            ],
        },
    },
]

ROOT_URLCONF = "digital_store.urls"
# WSGI_APPLICATION = 'digital_store.wsgi.application'

# ─── Database ─────────────────────────────────────────────────────────────────

# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": _settings.db.engine,
        "NAME": _settings.db.database,
        "USER": _settings.db.user,
        "PASSWORD": _settings.db.password,
        "HOST": _settings.db.host,
        "PORT": _settings.db.port,
        "CONN_MAX_AGE": _settings.db.conn_max_age,
        "OPTIONS": _settings.db.options,
    },
}

# ─── Django Core Settings ──────────────────────────────────────────────────────

SITE_ID = _settings.django.site_id
DEBUG = _settings.django.debug
SALT_KEY = _settings.django.salt_key
SECRET_KEY = _settings.django.secret_key
ALLOWED_HOSTS = _settings.django.allowed_hosts

SECURE_SSL_REDIRECT = _settings.django.secure_ssl_redirect
SESSION_COOKIE_SECURE = _settings.django.session_cookie_secure
CSRF_COOKIE_SECURE = _settings.django.csrf_cookie_secure
USE_X_FORWARDED_HOST = _settings.django.use_x_forwarded_host
USE_X_FORWARDED_PORT = _settings.django.use_x_forwarded_port

# ─── Oscar ─────────────────────────────────────────────────────────────────────

OSCAR_DEFAULT_CURRENCY = _settings.oscar.default_currency
OSCAR_SHOP_NAME = _settings.oscar.shop_name

# ─── Localization ──────────────────────────────────────────────────────────────

# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = _settings.django.language_code
LANGUAGES = _settings.django.languages
TIME_ZONE = _settings.django.time_zone
USE_I18N = _settings.django.use_i18n
USE_TZ = _settings.django.use_tz

# ─── Modeltranslation ──────────────────────────────────────────────────────────

MODELTRANSLATION_DEFAULT_LANGUAGE = _settings.modeltranslation.default_language
MODELTRANSLATION_LANGUAGES = tuple(_settings.modeltranslation.languages)

# ─── Static / Media ───────────────────────────────────────────────────────────
# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = _settings.django.static_url
STATIC_ROOT = BASE_DIR / _settings.django.static_root
STATICFILES_DIRS = [BASE_DIR / _settings.django.staticfiles_dir]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = _settings.django.media_url
MEDIA_ROOT = BASE_DIR / _settings.django.media_root

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

# ─── Oscar defaults ────────────────────────────────────────────────────────────

from oscar.defaults import *  # noqa
