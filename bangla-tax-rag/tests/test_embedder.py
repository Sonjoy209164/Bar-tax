import numpy as np

from app.retrieval import embedder
from app.retrieval.embedder import (
    DEFAULT_OPENAI_BASE_URL,
    DeterministicTextEmbedder,
    EmbedderConfig,
    EmbeddingProvider,
    OpenAITextEmbedder,
    TransformersTextEmbedder,
    build_embedder,
)


def test_deterministic_embedder_returns_stable_normalized_vectors() -> None:
    config = EmbedderConfig(
        provider=EmbeddingProvider.DETERMINISTIC,
        model_name="deterministic-test",
        dimensions=16,
    )
    embedder_instance = DeterministicTextEmbedder(config)

    batch_one = embedder_instance.embed_texts(["Commissioner definition", "Tax Day"])
    batch_two = embedder_instance.embed_texts(["Commissioner definition", "Tax Day"])

    assert batch_one.dimensions == 16
    assert batch_one.vectors == batch_two.vectors
    assert len(batch_one.vectors) == 2
    assert np.isclose(np.linalg.norm(np.asarray(batch_one.vectors[0], dtype=np.float32)), 1.0, atol=1e-5)


def test_transformers_embedder_uses_encoder_and_respects_dimension_override(monkeypatch) -> None:
    def fake_encode(texts, *, model_name):
        assert model_name == "demo-model"
        return np.asarray(
            [
                [3.0, 4.0, 0.0],
                [0.0, 6.0, 8.0],
            ],
            dtype=np.float32,
        )

    monkeypatch.setattr(embedder, "_encode_texts_with_transformers", fake_encode)

    config = EmbedderConfig(
        provider=EmbeddingProvider.TRANSFORMERS,
        model_name="demo-model",
        dimensions=2,
    )
    batch = TransformersTextEmbedder(config).embed_texts(["A", "B"])

    assert batch.dimensions == 2
    assert len(batch.vectors) == 2
    assert np.allclose(batch.vectors[0], [0.6, 0.8], atol=1e-5)


def test_openai_embedder_posts_expected_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "model": "text-embedding-3-large",
                "data": [
                    {"embedding": [3.0, 4.0]},
                    {"embedding": [5.0, 12.0]},
                ],
            }

    class FakeClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, *, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(embedder.httpx, "Client", FakeClient)

    config = EmbedderConfig(
        provider=EmbeddingProvider.OPENAI,
        model_name="text-embedding-3-large",
        api_key="test-key",
        dimensions=2,
    )
    batch = OpenAITextEmbedder(config).embed_texts(["alpha", "beta"])

    assert captured["url"] == f"{DEFAULT_OPENAI_BASE_URL}/embeddings"
    assert captured["json"] == {
        "input": ["alpha", "beta"],
        "model": "text-embedding-3-large",
        "dimensions": 2,
    }
    assert batch.dimensions == 2
    assert np.allclose(batch.vectors[0], [0.6, 0.8], atol=1e-5)


def test_build_embedder_factory_supports_all_configured_providers() -> None:
    deterministic = build_embedder(
        EmbedderConfig(provider=EmbeddingProvider.DETERMINISTIC, model_name="deterministic", dimensions=8)
    )
    assert isinstance(deterministic, DeterministicTextEmbedder)

    transformers = build_embedder(
        EmbedderConfig(provider=EmbeddingProvider.TRANSFORMERS, model_name="demo-model")
    )
    assert isinstance(transformers, TransformersTextEmbedder)

    openai = build_embedder(
        EmbedderConfig(provider=EmbeddingProvider.OPENAI, model_name="text-embedding-3-large", api_key="x")
    )
    assert isinstance(openai, OpenAITextEmbedder)
