from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="bangla-tax-rag", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    config_path: str = Field(default="config/config.dev.yaml", alias="CONFIG_PATH")
    raw_data_dir: str = Field(default="data/raw", alias="RAW_DATA_DIR")
    processed_data_dir: str = Field(default="data/processed", alias="PROCESSED_DATA_DIR")
    sparse_index_dir: str = Field(default="indexes/sparse", alias="SPARSE_INDEX_DIR")
    dense_index_dir: str = Field(default="indexes/dense", alias="DENSE_INDEX_DIR")
    results_dir: str = Field(default="results", alias="RESULTS_DIR")
    parser_provider: str = Field(default="fallback", alias="PARSER_PROVIDER")
    llama_parse_result_type: str = Field(default="markdown", alias="LLAMAPARSE_RESULT_TYPE")
    llama_cloud_api_key: str | None = Field(default=None, alias="LLAMA_CLOUD_API_KEY")
    ui_backend_base_url: str = Field(default="http://127.0.0.1:8000", alias="UI_BACKEND_BASE_URL")
    retrieval_mode: str = Field(default="hybrid", alias="RETRIEVAL_MODE")
    top_k: int = Field(default=5, alias="TOP_K")
    final_evidence_k: int = Field(default=5, alias="FINAL_EVIDENCE_K")
    generator_provider: str = Field(default="openai_compatible", alias="GENERATOR_PROVIDER")
    generator_model_name: str = Field(default="deepseek-r1:7b", alias="GENERATOR_MODEL_NAME")
    generator_base_url: str | None = Field(default="http://127.0.0.1:11434/v1", alias="GENERATOR_BASE_URL")
    generator_api_key: str | None = Field(default=None, alias="GENERATOR_API_KEY")
    max_generation_tokens: int = Field(default=512, alias="MAX_GENERATION_TOKENS")
    temperature: float = Field(default=0.0, alias="TEMPERATURE")
    abstention_score_threshold: float = Field(default=0.75, alias="ABSTENTION_SCORE_THRESHOLD")
    verification_enabled: bool = Field(default=True, alias="VERIFICATION_ENABLED")
    embedding_provider: str = Field(default="transformers", alias="EMBEDDING_PROVIDER")
    embedding_model_name: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL_NAME")
    embedding_base_url: str | None = Field(default=None, alias="EMBEDDING_BASE_URL")
    embedding_api_key: str | None = Field(default=None, alias="EMBEDDING_API_KEY")
    embedding_dimensions: int | None = Field(default=None, alias="EMBEDDING_DIMENSIONS")
    vector_db: str = Field(default="pinecone", alias="VECTOR_DB")
    vector_metric: str = Field(default="cosine", alias="VECTOR_METRIC")
    vector_namespace: str | None = Field(default=None, alias="VECTOR_NAMESPACE")
    pinecone_api_key: str | None = Field(default=None, alias="PINECONE_API_KEY")
    pinecone_index_name: str | None = Field(default=None, alias="PINECONE_INDEX_NAME")
    pinecone_host: str | None = Field(default=None, alias="PINECONE_HOST")
    milvus_uri: str | None = Field(default=None, alias="MILVUS_URI")
    milvus_token: str | None = Field(default=None, alias="MILVUS_TOKEN")
    milvus_collection_name: str | None = Field(default=None, alias="MILVUS_COLLECTION_NAME")
    reranker_provider: str = Field(default="transformers", alias="RERANKER_PROVIDER")
    reranker_model_name: str = Field(default="BAAI/bge-reranker-v2-m3", alias="RERANKER_MODEL_NAME")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def load_yaml_config(self) -> dict:
        config_file = Path(self.config_path)
        if not config_file.exists():
            return {}
        with config_file.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def non_secret_config(self) -> dict:
        return {
            "app_name": self.app_name,
            "app_env": self.app_env,
            "raw_data_dir": self.raw_data_dir,
            "processed_data_dir": self.processed_data_dir,
            "sparse_index_dir": self.sparse_index_dir,
            "dense_index_dir": self.dense_index_dir,
            "results_dir": self.results_dir,
            "parser_provider": self.parser_provider,
            "llama_parse_result_type": self.llama_parse_result_type,
            "ui_backend_base_url": self.ui_backend_base_url,
            "retrieval_mode": self.retrieval_mode,
            "top_k": self.top_k,
            "final_evidence_k": self.final_evidence_k,
            "generator_provider": self.generator_provider,
            "generator_model_name": self.generator_model_name,
            "generator_base_url": self.generator_base_url,
            "max_generation_tokens": self.max_generation_tokens,
            "temperature": self.temperature,
            "abstention_score_threshold": self.abstention_score_threshold,
            "verification_enabled": self.verification_enabled,
            "embedding_provider": self.embedding_provider,
            "embedding_model_name": self.embedding_model_name,
            "embedding_base_url": self.embedding_base_url,
            "embedding_dimensions": self.embedding_dimensions,
            "vector_db": self.vector_db,
            "vector_metric": self.vector_metric,
            "vector_namespace": self.vector_namespace,
            "pinecone_index_name": self.pinecone_index_name,
            "pinecone_host": self.pinecone_host,
            "milvus_uri": self.milvus_uri,
            "milvus_collection_name": self.milvus_collection_name,
            "reranker_provider": self.reranker_provider,
            "reranker_model_name": self.reranker_model_name,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    yaml_config = settings.load_yaml_config()
    flat_updates: dict[str, object] = {}
    app_config = yaml_config.get("app", {})
    retrieval_config = yaml_config.get("retrieval", {})
    generation_config = yaml_config.get("generation", {})
    paths_config = yaml_config.get("paths", {})
    parser_config = yaml_config.get("parser", {})
    embeddings_config = yaml_config.get("embeddings", {})
    vector_store_config = yaml_config.get("vector_store", {})
    reranker_config = yaml_config.get("reranker", {})
    if "name" in app_config:
        flat_updates["app_name"] = app_config["name"]
    if "environment" in app_config:
        flat_updates["app_env"] = app_config["environment"]
    if "host" in app_config:
        flat_updates["app_host"] = app_config["host"]
    if "port" in app_config:
        flat_updates["app_port"] = app_config["port"]
    if "mode" in retrieval_config:
        flat_updates["retrieval_mode"] = retrieval_config["mode"]
    if "top_k" in retrieval_config:
        flat_updates["top_k"] = retrieval_config["top_k"]
    if "final_evidence_k" in retrieval_config:
        flat_updates["final_evidence_k"] = retrieval_config["final_evidence_k"]
    if "provider" in generation_config:
        flat_updates["generator_provider"] = generation_config["provider"]
    if "model_name" in generation_config:
        flat_updates["generator_model_name"] = generation_config["model_name"]
    if "base_url" in generation_config:
        flat_updates["generator_base_url"] = generation_config["base_url"]
    if "max_tokens" in generation_config:
        flat_updates["max_generation_tokens"] = generation_config["max_tokens"]
    if "temperature" in generation_config:
        flat_updates["temperature"] = generation_config["temperature"]
    if "abstention_score_threshold" in generation_config:
        flat_updates["abstention_score_threshold"] = generation_config["abstention_score_threshold"]
    if "verification_enabled" in generation_config:
        flat_updates["verification_enabled"] = generation_config["verification_enabled"]
    for key in ("raw_data_dir", "processed_data_dir", "sparse_index_dir", "dense_index_dir", "results_dir"):
        if key in paths_config:
            flat_updates[key] = paths_config[key]
    if "provider" in parser_config:
        flat_updates["parser_provider"] = parser_config["provider"]
    if "result_type" in parser_config:
        flat_updates["llama_parse_result_type"] = parser_config["result_type"]
    if "ui_backend_base_url" in paths_config:
        flat_updates["ui_backend_base_url"] = paths_config["ui_backend_base_url"]
    if "provider" in embeddings_config:
        flat_updates["embedding_provider"] = embeddings_config["provider"]
    if "model_name" in embeddings_config:
        flat_updates["embedding_model_name"] = embeddings_config["model_name"]
    if "base_url" in embeddings_config:
        flat_updates["embedding_base_url"] = embeddings_config["base_url"]
    if "dimensions" in embeddings_config:
        flat_updates["embedding_dimensions"] = embeddings_config["dimensions"]
    if "provider" in vector_store_config:
        flat_updates["vector_db"] = vector_store_config["provider"]
    if "metric" in vector_store_config:
        flat_updates["vector_metric"] = vector_store_config["metric"]
    if "namespace" in vector_store_config:
        flat_updates["vector_namespace"] = vector_store_config["namespace"]
    if "pinecone_index_name" in vector_store_config:
        flat_updates["pinecone_index_name"] = vector_store_config["pinecone_index_name"]
    if "pinecone_host" in vector_store_config:
        flat_updates["pinecone_host"] = vector_store_config["pinecone_host"]
    if "milvus_uri" in vector_store_config:
        flat_updates["milvus_uri"] = vector_store_config["milvus_uri"]
    if "milvus_collection_name" in vector_store_config:
        flat_updates["milvus_collection_name"] = vector_store_config["milvus_collection_name"]
    if "provider" in reranker_config:
        flat_updates["reranker_provider"] = reranker_config["provider"]
    if "model_name" in reranker_config:
        flat_updates["reranker_model_name"] = reranker_config["model_name"]
    return settings.model_copy(update=flat_updates)
