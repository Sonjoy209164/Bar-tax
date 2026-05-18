import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.settings import get_settings
from app.core.security import reset_security_state


@pytest.fixture(autouse=True)
def clear_api_key_for_tests(monkeypatch: pytest.MonkeyPatch):
    # Keep the suite open by default even when a real local .env enables API auth.
    monkeypatch.setenv("API_ACCESS_KEY", "")
    get_settings.cache_clear()
    yield
    reset_security_state()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_ollama_probe_cache_globally():
    """
    is_ollama_available() caches its probe for 30s in production. In tests,
    that means whichever test runs first poisons the cache for every later
    test. Reset around every test so each test's mocks behave consistently.
    """
    try:
        from app.inventory.llm_slot_extractor import reset_ollama_probe_cache
        reset_ollama_probe_cache()
    except Exception:
        pass
    yield
    try:
        from app.inventory.llm_slot_extractor import reset_ollama_probe_cache
        reset_ollama_probe_cache()
    except Exception:
        pass
