"""
digital_store/settings_test.py
"""
import os
os.environ["ENV_FOR_DYNACONF"] = "tests.local"

# from digital_store.settings import *  # noqa


from pathlib import Path
from dynaconf import Dynaconf

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


_settings = Dynaconf(
    settings_file=BASE_DIR / "settings.yaml",
    environments=True,
    env_switcher="ENV_FOR_DYNACONF",
)
