import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.settings import get_settings


@pytest.fixture(autouse=True)
def clear_api_key_for_tests(monkeypatch: pytest.MonkeyPatch):
    # Keep the suite open by default even when a real local .env enables API auth.
    monkeypatch.setenv("API_ACCESS_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
