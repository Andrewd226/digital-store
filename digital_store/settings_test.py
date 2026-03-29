"""
digital_store/settings_test.py
"""
import os
os.environ["ENV_FOR_DYNACONF"] = "tests.local"

from digital_store.settings import *  # noqa
