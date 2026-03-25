from digital_store.settings import *  # noqa

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("TEST_DB_NAME"),
        "USER": env("TEST_DB_USER"),
        "PASSWORD": env("TEST_DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT"),
    }
}
