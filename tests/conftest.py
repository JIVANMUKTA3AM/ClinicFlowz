"""
tests/conftest.py
Sets dummy environment variables before any app module is imported.
This prevents the lazy Supabase singleton from attempting a real network
connection during test collection or setup.
"""

import os
import pytest


def pytest_configure(config):
    """
    Earliest pytest hook — runs before test collection and before any app
    import. Sets the minimum env vars required by pydantic_settings.Settings()
    so that config.py can be imported without raising a validation error.

    os.environ.setdefault is used so that real values in the shell environment
    (e.g. CI secrets) are NOT overwritten.
    """
    os.environ.setdefault("SUPABASE_URL",         "https://dummy.supabase.co")
    os.environ.setdefault("SUPABASE_SERVICE_KEY",  "sb_dummy_service_key_for_tests")
    os.environ.setdefault("ANTHROPIC_API_KEY",     "sk-ant-dummy-key-for-tests")


@pytest.fixture(autouse=True)
def reset_supabase_singleton():
    """
    Resets the lazy Supabase singleton before and after every test so that
    no test's side-effects (e.g. a test that somehow triggered a real client
    creation) leak into subsequent tests.
    """
    import app.core.database as db_module
    db_module._client = None
    yield
    db_module._client = None
