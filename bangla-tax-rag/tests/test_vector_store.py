from app.retrieval import (
    ElasticsearchVectorStore,
    LocalVectorStore,
    MilvusVectorStore,
    PineconeVectorStore,
    VectorRecord,
    VectorStoreConfig,
    VectorStoreProvider,
    build_vector_store,
)
from app.retrieval.elasticsearch_store import _elasticsearch_similarity
from app.retrieval import vector_store_base
from app.retrieval.milvus_store import _build_milvus_filter_expression


def test_build_vector_store_factory_selects_provider() -> None:
    local_store = build_vector_store(
        VectorStoreConfig(
            provider=VectorStoreProvider.LOCAL,
            local_store_path="/tmp/local-vectors.jsonl",
        )
    )
    assert isinstance(local_store, LocalVectorStore)

    pinecone_store = build_vector_store(
        VectorStoreConfig(
            provider=VectorStoreProvider.PINECONE,
            pinecone_api_key="key",
            pinecone_index_name="income-tax-index",
        )
    )
    assert isinstance(pinecone_store, PineconeVectorStore)

    milvus_store = build_vector_store(
        VectorStoreConfig(
            provider=VectorStoreProvider.MILVUS,
            milvus_uri="http://localhost:19530",
            milvus_collection_name="income_tax_chunks",
        )
    )
    assert isinstance(milvus_store, MilvusVectorStore)

    elasticsearch_store = build_vector_store(
        VectorStoreConfig(
            provider=VectorStoreProvider.ELASTICSEARCH,
            elasticsearch_url="http://localhost:9200",
            elasticsearch_index_name="income-tax-vectors",
        )
    )
    assert isinstance(elasticsearch_store, ElasticsearchVectorStore)


def test_local_store_persists_queries_and_filters(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = LocalVectorStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.LOCAL,
            namespace="tax",
            local_store_path=str(tmp_path / "vectors.jsonl"),
        )
    )

    store.upsert(
        [
            VectorRecord(
                record_id="chunk-1",
                vector=[1.0, 0.0],
                metadata={"section_number": "4", "page_start": 12, "chunk_type": "rule"},
                text="Income tax authorities",
            ),
            VectorRecord(
                record_id="chunk-2",
                vector=[0.0, 1.0],
                metadata={"section_number": "2", "page_start": 4, "chunk_type": "definition"},
                text="Commissioner definition",
            ),
        ]
    )
    reloaded = LocalVectorStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.LOCAL,
            namespace="tax",
            local_store_path=str(tmp_path / "vectors.jsonl"),
        )
    )

    result = reloaded.query(
        [1.0, 0.0],
        top_k=2,
        filters={"section_number": {"$eq": "4"}, "page_start": {"$gte": 10}},
    )

    assert [match.record_id for match in result.matches] == ["chunk-1"]
    assert result.matches[0].text == "Income tax authorities"


def test_pinecone_store_translates_upsert_query_and_delete_payloads(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeIndex:
        def upsert(self, *, vectors, namespace=None):
            captured["upsert_vectors"] = vectors
            captured["upsert_namespace"] = namespace

        def query(self, *, vector, top_k, namespace=None, filter=None, include_metadata=None):
            captured["query_vector"] = vector
            captured["query_top_k"] = top_k
            captured["query_namespace"] = namespace
            captured["query_filter"] = filter
            captured["query_include_metadata"] = include_metadata
            return {
                "matches": [
                    {
                        "id": "chunk-1",
                        "score": 0.91,
                        "metadata": {"section_number": "4", "_text": "Income tax authorities"},
                    }
                ]
            }

        def delete(self, *, ids, namespace=None):
            captured["delete_ids"] = ids
            captured["delete_namespace"] = namespace

        def describe_index_stats(self):
            return {"total_vector_count": 11, "namespaces": {"tax": {"vector_count": 7}}}

    class FakePineconeStore(PineconeVectorStore):
        def _index(self):
            return FakeIndex()

    store = FakePineconeStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.PINECONE,
            pinecone_api_key="key",
            pinecone_index_name="income-tax-index",
            namespace="tax",
        )
    )

    store.upsert(
        [
            VectorRecord(
                record_id="chunk-1",
                vector=[0.1, 0.2],
                metadata={"section_number": "4"},
                text="Income tax authorities",
            )
        ]
    )
    result = store.query([0.2, 0.4], top_k=3, filters={"section_number": {"$eq": "4"}})
    store.delete(["chunk-1"])
    stats = store.describe()

    assert captured["upsert_namespace"] == "tax"
    assert captured["upsert_vectors"] == [
        {
            "id": "chunk-1",
            "values": [0.1, 0.2],
            "metadata": {"section_number": "4", "_text": "Income tax authorities"},
        }
    ]
    assert captured["query_filter"] == {"section_number": {"$eq": "4"}}
    assert result.matches[0].record_id == "chunk-1"
    assert result.matches[0].text == "Income tax authorities"
    assert captured["delete_ids"] == ["chunk-1"]
    assert stats.total_vector_count == 7


def test_milvus_store_translates_filter_and_result_payloads() -> None:
    captured: dict[str, object] = {}

    class FakeMilvusClient:
        def upsert(self, *, collection_name, data):
            captured["upsert_collection"] = collection_name
            captured["upsert_data"] = data

        def search(self, *, collection_name, data, limit, filter=None, output_fields=None):
            captured["search_collection"] = collection_name
            captured["search_data"] = data
            captured["search_limit"] = limit
            captured["search_filter"] = filter
            captured["search_output_fields"] = output_fields
            return [
                [
                    {
                        "id": "chunk-2",
                        "distance": 0.88,
                        "entity": {
                            "text": "Commissioner definition",
                            "namespace": "tax",
                            "section_number": "2",
                        },
                    }
                ]
            ]

        def delete(self, *, collection_name, ids):
            captured["delete_collection"] = collection_name
            captured["delete_ids"] = ids

        def describe_collection(self, *, collection_name):
            captured["describe_collection"] = collection_name
            return {"num_entities": 19}

    class FakeMilvusStore(MilvusVectorStore):
        def _client(self):
            return FakeMilvusClient()

    store = FakeMilvusStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.MILVUS,
            milvus_uri="http://localhost:19530",
            milvus_collection_name="income_tax_chunks",
            namespace="tax",
        )
    )

    store.upsert(
        [
            VectorRecord(
                record_id="chunk-2",
                vector=[0.5, 0.6],
                metadata={"section_number": "2"},
                text="Commissioner definition",
            )
        ]
    )
    result = store.query([0.5, 0.7], top_k=4, filters={"section_number": {"$eq": "2"}})
    store.delete(["chunk-2"])
    stats = store.describe()

    assert captured["upsert_collection"] == "income_tax_chunks"
    assert captured["upsert_data"] == [
        {
            "id": "chunk-2",
            "vector": [0.5, 0.6],
            "text": "Commissioner definition",
            "namespace": "tax",
            "section_number": "2",
        }
    ]
    assert captured["search_filter"] == 'section_number == "2" and namespace == "tax"'
    assert result.matches[0].record_id == "chunk-2"
    assert result.matches[0].metadata["section_number"] == "2"
    assert captured["delete_ids"] == ["chunk-2"]
    assert stats.total_vector_count == 19


def test_elasticsearch_store_translates_upsert_query_delete_and_describe_payloads(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeIndices:
        def exists(self, *, index):
            captured.setdefault("exists_indices", []).append(index)
            return bool(captured.get("index_exists", False))

        def create(self, *, index, mappings):
            captured["created_index"] = index
            captured["created_mappings"] = mappings
            captured["index_exists"] = True

    class FakeElasticsearchClient:
        def __init__(self) -> None:
            self.indices = FakeIndices()

        def search(self, *, index, knn, size, source_excludes=None):
            captured["search_index"] = index
            captured["search_knn"] = knn
            captured["search_size"] = size
            captured["search_source_excludes"] = source_excludes
            return {
                "hits": {
                    "hits": [
                        {
                            "_id": "tax::chunk-1",
                            "_score": 0.91,
                            "_source": {
                                "record_id": "chunk-1",
                                "namespace": "tax",
                                "text": "Income tax authorities",
                                "metadata": {"section_number": "4"},
                                "product_id": "prod-1",
                                "stock": 12,
                            },
                        }
                    ]
                }
            }

        def delete(self, *, index, id, refresh=None):
            captured["delete_index"] = index
            captured["delete_id"] = id
            captured["delete_refresh"] = refresh

        def count(self, *, index, query):
            captured["count_index"] = index
            captured["count_query"] = query
            return {"count": 7}

    class FakeHelpers:
        @staticmethod
        def bulk(client, actions):
            captured["bulk_client"] = client
            captured["bulk_actions"] = list(actions)

    class FakeElasticsearchStore(ElasticsearchVectorStore):
        def __init__(self, config):
            super().__init__(config)
            self.fake_client = FakeElasticsearchClient()

        def _client(self):
            return self.fake_client

    monkeypatch.setattr("app.retrieval.elasticsearch_store.helpers", FakeHelpers)
    store = FakeElasticsearchStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.ELASTICSEARCH,
            elasticsearch_url="http://localhost:9200",
            elasticsearch_index_name="income-tax-vectors",
            namespace="tax",
        )
    )

    store.upsert(
        [
            VectorRecord(
                record_id="chunk-1",
                vector=[0.1, 0.2],
                metadata={
                    "section_number": "4",
                    "product_id": "prod-1",
                    "stock": 12,
                    "nested": {"ignored": True},
                },
                text="Income tax authorities",
            )
        ]
    )
    result = store.query(
        [0.2, 0.4],
        top_k=3,
        filters={
            "section_number": {"$eq": "4"},
            "page_start": {"$gte": 10, "$lte": 20},
            "chunk_type": {"$in": ["rule", "table"]},
            "product_id": ["prod-1", "prod-2"],
        },
    )
    store.delete(["chunk-1"])
    stats = store.describe()

    mappings = captured["created_mappings"]
    assert captured["created_index"] == "income-tax-vectors"
    assert mappings["properties"]["vector"] == {
        "type": "dense_vector",
        "dims": 2,
        "index": True,
        "similarity": "cosine",
    }
    assert captured["bulk_actions"] == [
        {
            "_op_type": "index",
            "_index": "income-tax-vectors",
            "_id": "tax::chunk-1",
            "_source": {
                "record_id": "chunk-1",
                "namespace": "tax",
                "text": "Income tax authorities",
                "metadata": {
                    "section_number": "4",
                    "product_id": "prod-1",
                    "stock": 12,
                    "nested": {"ignored": True},
                },
                "vector": [0.1, 0.2],
                "section_number": "4",
                "product_id": "prod-1",
                "stock": 12,
            },
        }
    ]
    assert captured["search_index"] == "income-tax-vectors"
    assert captured["search_knn"] == {
        "field": "vector",
        "query_vector": [0.2, 0.4],
        "k": 3,
        "num_candidates": 50,
        "filter": [
            {"term": {"namespace": "tax"}},
            {"term": {"section_number": "4"}},
            {"range": {"page_start": {"gte": 10, "lte": 20}}},
            {"terms": {"chunk_type": ["rule", "table"]}},
            {"terms": {"product_id": ["prod-1", "prod-2"]}},
        ],
    }
    assert captured["search_source_excludes"] == ["vector"]
    assert result.matches[0].record_id == "chunk-1"
    assert result.matches[0].score == 0.91
    assert result.matches[0].text == "Income tax authorities"
    assert result.matches[0].metadata["section_number"] == "4"
    assert result.matches[0].metadata["product_id"] == "prod-1"
    assert captured["delete_id"] == "tax::chunk-1"
    assert captured["delete_refresh"] is True
    assert captured["count_query"] == {"bool": {"filter": [{"term": {"namespace": "tax"}}]}}
    assert stats.total_vector_count == 7


def test_elasticsearch_store_deletes_by_query_without_namespace() -> None:
    captured: dict[str, object] = {}

    class FakeElasticsearchClient:
        def delete_by_query(self, *, index, query, conflicts=None, refresh=None):
            captured["delete_by_query_index"] = index
            captured["delete_by_query_query"] = query
            captured["delete_by_query_conflicts"] = conflicts
            captured["delete_by_query_refresh"] = refresh

    class FakeElasticsearchStore(ElasticsearchVectorStore):
        def _client(self):
            return FakeElasticsearchClient()

    store = FakeElasticsearchStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.ELASTICSEARCH,
            elasticsearch_url="http://localhost:9200",
            elasticsearch_index_name="income-tax-vectors",
        )
    )

    store.delete(["chunk-1", "chunk-2"])

    assert captured == {
        "delete_by_query_index": "income-tax-vectors",
        "delete_by_query_query": {"terms": {"record_id": ["chunk-1", "chunk-2"]}},
        "delete_by_query_conflicts": "proceed",
        "delete_by_query_refresh": True,
    }


def test_elasticsearch_store_requires_url() -> None:
    store = ElasticsearchVectorStore(
        VectorStoreConfig(
            provider=VectorStoreProvider.ELASTICSEARCH,
            elasticsearch_index_name="income-tax-vectors",
        )
    )

    try:
        store._client()
    except ValueError as exc:
        assert str(exc) == "Elasticsearch URL is required"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Expected missing Elasticsearch URL to fail")


def test_build_milvus_filter_expression_supports_common_operators() -> None:
    expression = _build_milvus_filter_expression(
        {
            "section_number": {"$eq": "4"},
            "page_start": {"$gte": 20},
            "chunk_type": {"$in": ["rule", "table"]},
        },
        namespace="tax",
    )

    assert expression == (
        'section_number == "4" and '
        "page_start >= 20 and "
        'chunk_type in ["rule", "table"] and '
        'namespace == "tax"'
    )


def test_elasticsearch_similarity_normalizes_supported_metrics() -> None:
    assert _elasticsearch_similarity("cosine") == "cosine"
    assert _elasticsearch_similarity("euclidean") == "l2_norm"
