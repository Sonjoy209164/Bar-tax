from app.retrieval import (
    MilvusVectorStore,
    PineconeVectorStore,
    VectorRecord,
    VectorStoreConfig,
    VectorStoreProvider,
    build_vector_store,
)
from app.retrieval import vector_store_base
from app.retrieval.milvus_store import _build_milvus_filter_expression


def test_build_vector_store_factory_selects_provider() -> None:
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
