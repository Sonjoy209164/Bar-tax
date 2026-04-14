from pathlib import Path

from app.core.settings import get_settings


def test_environment_values_override_yaml_config(monkeypatch) -> None:
    monkeypatch.setenv("CONFIG_PATH", "config/config.dev.yaml")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "deterministic")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "deterministic-demo")
    monkeypatch.setenv("RERANKER_PROVIDER", "none")
    monkeypatch.setenv("AGENTIC_STORE_DIR", "/tmp/test-agentic-store")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.embedding_provider == "deterministic"
    assert settings.embedding_model_name == "deterministic-demo"
    assert settings.reranker_provider == "none"
    assert settings.agentic_store_dir == "/tmp/test-agentic-store"
    get_settings.cache_clear()


def test_yaml_config_applies_when_field_is_not_explicitly_set(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        """
app:
  name: yaml-demo
retrieval:
  top_k: 9
vector_store:
  provider: local
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("TOP_K", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.app_name == "yaml-demo"
    assert settings.top_k == 9
    assert settings.vector_db == "local"
    get_settings.cache_clear()
