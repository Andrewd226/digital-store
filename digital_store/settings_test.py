"""
digital_store/settings_test.py
"""
from pathlib import Path

import environ

from digital_store.settings import *  # noqa

# ─── Environment ──────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# ─── Database (Test) ──────────────────────────────────────────────────────────

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
