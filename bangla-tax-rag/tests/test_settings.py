from pathlib import Path

from app.core.settings import get_settings
from app.retrieval.vector_store_base import vector_store_config_from_settings


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


def test_settings_support_rotated_api_keys(monkeypatch) -> None:
    monkeypatch.setenv("API_ACCESS_KEY", "primary-key")
    monkeypatch.setenv("API_ACCESS_KEYS", "legacy-key, next-key, primary-key\nfuture-key")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.accepted_api_keys() == (
        "primary-key",
        "legacy-key",
        "next-key",
        "future-key",
    )
    get_settings.cache_clear()


def test_elasticsearch_settings_are_loaded_without_exposing_secrets(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "settings.yaml"
    config_path.write_text(
        """
vector_store:
  provider: local
  elasticsearch_url: http://localhost:9200
  elasticsearch_api_key: yaml-secret-key
  elasticsearch_username: elastic
  elasticsearch_password: yaml-secret-password
  elasticsearch_index_name: inventory-test
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    get_settings.cache_clear()

    settings = get_settings()
    vector_config = vector_store_config_from_settings()
    public_config = settings.non_secret_config()

    assert settings.elasticsearch_url == "http://localhost:9200"
    assert settings.elasticsearch_api_key == "yaml-secret-key"
    assert settings.elasticsearch_username == "elastic"
    assert settings.elasticsearch_password == "yaml-secret-password"
    assert settings.elasticsearch_index_name == "inventory-test"
    assert vector_config.elasticsearch_url == "http://localhost:9200"
    assert vector_config.elasticsearch_api_key == "yaml-secret-key"
    assert vector_config.elasticsearch_username == "elastic"
    assert vector_config.elasticsearch_password == "yaml-secret-password"
    assert vector_config.elasticsearch_index_name == "inventory-test"
    assert public_config["elasticsearch_url"] == "http://localhost:9200"
    assert public_config["elasticsearch_index_name"] == "inventory-test"
    assert "elasticsearch_api_key" not in public_config
    assert "elasticsearch_password" not in public_config
    assert "elasticsearch_username" not in public_config
    get_settings.cache_clear()
