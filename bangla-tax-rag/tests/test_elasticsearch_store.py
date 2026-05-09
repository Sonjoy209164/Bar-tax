import pytest

from app.retrieval.elasticsearch_store import ElasticsearchVectorStore
from app.retrieval.vector_store_base import VectorRecord, VectorStoreConfig, VectorStoreProvider

# Tests that exercise validation logic AFTER the elasticsearch import probe
# need the dependency installed. When it isn't, _client() raises RuntimeError
# before the real validation runs, so we skip the affected test.
_HAS_ELASTICSEARCH = False
try:
    import elasticsearch  # noqa: F401
    _HAS_ELASTICSEARCH = True
except ImportError:
    pass


def test_elasticsearch_client_uses_api_key_auth(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeElasticsearch:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

    monkeypatch.setattr("app.retrieval.elasticsearch_store.Elasticsearch", FakeElasticsearch)
    store = ElasticsearchVectorStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.ELASTICSEARCH,
            elasticsearch_url="http://localhost:9200",
            elasticsearch_api_key="secret-api-key",
            elasticsearch_index_name="inventory-rag",
        )
    )

    store._client()

    assert captured["kwargs"] == {
        "hosts": ["http://localhost:9200"],
        "api_key": "secret-api-key",
    }


def test_elasticsearch_client_uses_basic_auth(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeElasticsearch:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

    monkeypatch.setattr("app.retrieval.elasticsearch_store.Elasticsearch", FakeElasticsearch)
    store = ElasticsearchVectorStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.ELASTICSEARCH,
            elasticsearch_url="http://localhost:9200",
            elasticsearch_username="elastic",
            elasticsearch_password="secret-password",
            elasticsearch_index_name="inventory-rag",
        )
    )

    store._client()

    assert captured["kwargs"] == {
        "hosts": ["http://localhost:9200"],
        "basic_auth": ("elastic", "secret-password"),
    }


@pytest.mark.skipif(not _HAS_ELASTICSEARCH, reason="elasticsearch package not installed")
def test_elasticsearch_client_requires_complete_basic_auth() -> None:
    store = ElasticsearchVectorStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.ELASTICSEARCH,
            elasticsearch_url="http://localhost:9200",
            elasticsearch_username="elastic",
            elasticsearch_index_name="inventory-rag",
        )
    )

    with pytest.raises(ValueError, match="Both Elasticsearch username and password are required"):
        store._client()


def test_elasticsearch_lexical_query_builds_bm25_payload() -> None:
    captured: dict[str, object] = {}

    class FakeIndices:
        def exists(self, *, index):
            captured["exists_index"] = index
            return True

    class FakeClient:
        def __init__(self) -> None:
            self.indices = FakeIndices()

        def search(self, *, index, query, size, source_excludes=None):
            captured["search_index"] = index
            captured["search_query"] = query
            captured["search_size"] = size
            captured["source_excludes"] = source_excludes
            return {
                "hits": {
                    "hits": [
                        {
                            "_id": "inventory::prod-headphones",
                            "_score": 9.0,
                            "_source": {
                                "record_id": "prod-headphones",
                                "namespace": "inventory",
                                "text": "Wireless headphones",
                                "metadata": {"sku": "AUD-HP-001"},
                                "sku": "AUD-HP-001",
                            },
                        }
                    ]
                }
            }

    class FakeElasticsearchStore(ElasticsearchVectorStore):
        def _client(self):
            return FakeClient()

    store = FakeElasticsearchStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.ELASTICSEARCH,
            elasticsearch_url="http://localhost:9200",
            elasticsearch_index_name="inventory-rag",
            namespace="inventory",
        )
    )

    result = store.lexical_query(
        "wireless headphones",
        top_k=5,
        filters={"category_key": ["audio"], "stock": {"$gte": 1}},
    )

    assert captured["search_index"] == "inventory-rag"
    assert captured["search_size"] == 5
    assert captured["source_excludes"] == ["vector"]
    assert captured["search_query"] == {
        "bool": {
            "filter": [
                {"term": {"namespace": "inventory"}},
                {"terms": {"category_key": ["audio"]}},
                {"range": {"stock": {"gte": 1}}},
            ],
            "should": [
                {"term": {"sku": {"value": "wireless headphones", "boost": 8.0}}},
                {"term": {"product_id": {"value": "wireless headphones", "boost": 7.0}}},
                {"match_phrase": {"name": {"query": "wireless headphones", "boost": 5.0}}},
                {
                    "multi_match": {
                        "query": "wireless headphones",
                        "fields": ["name^4", "sku^5", "brand^2", "category^2", "text"],
                        "type": "best_fields",
                        "fuzziness": "AUTO",
                    }
                },
            ],
            "minimum_should_match": 1,
        }
    }
    assert result.matches[0].record_id == "prod-headphones"
    assert result.matches[0].metadata["sku"] == "AUD-HP-001"


def test_elasticsearch_record_ids_uses_scan_with_namespace(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeIndices:
        def exists(self, *, index):
            return True

    class FakeClient:
        def __init__(self) -> None:
            self.indices = FakeIndices()

    class FakeHelpers:
        @staticmethod
        def scan(client, *, index, query, size):
            captured["scan_client"] = client
            captured["scan_index"] = index
            captured["scan_query"] = query
            captured["scan_size"] = size
            return [
                {"_source": {"record_id": "prod-headphones"}},
                {"_source": {"record_id": "prod-watch"}},
            ]

    class FakeElasticsearchStore(ElasticsearchVectorStore):
        def __init__(self, config):
            super().__init__(config)
            self.fake_client = FakeClient()

        def _client(self):
            return self.fake_client

    monkeypatch.setattr("app.retrieval.elasticsearch_store.helpers", FakeHelpers)
    store = FakeElasticsearchStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.ELASTICSEARCH,
            elasticsearch_url="http://localhost:9200",
            elasticsearch_index_name="inventory-rag",
            namespace="inventory",
        )
    )

    assert store.record_ids() == ["prod-headphones", "prod-watch"]
    assert captured["scan_index"] == "inventory-rag"
    assert captured["scan_query"] == {
        "query": {"bool": {"filter": [{"term": {"namespace": "inventory"}}]}},
        "_source": ["record_id"],
    }
    assert captured["scan_size"] == 1000


def test_elasticsearch_describe_reads_object_api_response_body() -> None:
    class CountResponse:
        body = {"count": 60}

    class FakeIndices:
        def exists(self, *, index):
            return True

    class FakeClient:
        def __init__(self) -> None:
            self.indices = FakeIndices()

        def count(self, *, index, query):
            return CountResponse()

    class FakeElasticsearchStore(ElasticsearchVectorStore):
        def _client(self):
            return FakeClient()

    store = FakeElasticsearchStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.ELASTICSEARCH,
            elasticsearch_url="http://localhost:9200",
            elasticsearch_index_name="inventory-rag",
            namespace="inventory",
        )
    )

    assert store.describe().total_vector_count == 60


def test_elasticsearch_existing_index_dimension_mismatch_fails(monkeypatch) -> None:
    class FakeIndices:
        def exists(self, *, index):
            return True

        def get_mapping(self, *, index):
            return {
                index: {
                    "mappings": {
                        "properties": {
                            "vector": {
                                "type": "dense_vector",
                                "dims": 384,
                            }
                        }
                    }
                }
            }

    class FakeClient:
        def __init__(self) -> None:
            self.indices = FakeIndices()

    class FakeHelpers:
        @staticmethod
        def bulk(client, actions, refresh=None):
            raise AssertionError("bulk should not run when dimensions mismatch")

    class FakeElasticsearchStore(ElasticsearchVectorStore):
        def _client(self):
            return FakeClient()

    monkeypatch.setattr("app.retrieval.elasticsearch_store.helpers", FakeHelpers)
    store = FakeElasticsearchStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.ELASTICSEARCH,
            elasticsearch_url="http://localhost:9200",
            elasticsearch_index_name="inventory-rag",
        )
    )

    with pytest.raises(ValueError, match="has vector dimensions 384"):
        store.upsert(
            [
                VectorRecord(
                    record_id="prod-headphones",
                    vector=[0.1, 0.2],
                    metadata={"sku": "AUD-HP-001"},
                )
            ]
        )
