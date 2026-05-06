# TODO: Elasticsearch Integration for Inventory RAG

## Implementation Checklist

Use this as the execution tracker. Keep the detailed notes below as reference while implementing.

### Decision and Setup

- [x] Confirm Elasticsearch is worth adding for this project stage.
- [x] Choose Elasticsearch deployment mode: local Docker, self-managed server, or Elastic Cloud.
- [x] Confirm Elasticsearch server version.
- [x] Choose compatible Python client version.
- [x] Add `elasticsearch` dependency to `pyproject.toml`.
- [x] Add `elasticsearch` dependency to `requirements.txt`.
- [x] Install dependencies in the project environment.

Decision lock:

- Development deployment: local Docker Elasticsearch.
- Target server family: Elasticsearch 8.x.
- Suggested local image: `docker.elastic.co/elasticsearch/elasticsearch:8.19.3`.
- Python client range: `elasticsearch>=8,<9`.
- Installed Python client: `elasticsearch 8.19.3`.
- Production option later: Elastic Cloud or managed Elasticsearch after the adapter passes tests.

### Settings and Configuration

- [x] Add `ELASTICSEARCH_URL` setting.
- [x] Add `ELASTICSEARCH_API_KEY` setting.
- [x] Add `ELASTICSEARCH_USERNAME` setting.
- [x] Add `ELASTICSEARCH_PASSWORD` setting.
- [x] Add `ELASTICSEARCH_INDEX_NAME` setting.
- [x] Add safe Elasticsearch values to `non_secret_config()`.
- [x] Do not expose API key or password in non-secret config.
- [x] Add Elasticsearch fields to `VectorStoreConfig`.
- [x] Pass Elasticsearch settings in `vector_store_config_from_settings()`.
- [x] Add YAML override support under `vector_store`.
- [x] Update `config/config.dev.yaml` with local Elasticsearch defaults.

### Provider Wiring

- [x] Add `ELASTICSEARCH = "elasticsearch"` to `VectorStoreProvider`.
- [x] Add Elasticsearch branch to `build_vector_store()`.
- [x] Create `app/retrieval/elasticsearch_store.py`.
- [x] Export Elasticsearch store if needed from `app/retrieval/__init__.py`.

### Elasticsearch Adapter

- [x] Implement `ElasticsearchVectorStore.__init__`.
- [x] Implement `_client()`.
- [x] Implement `_index_name()`.
- [x] Implement `_document_id(record_id, namespace)`.
- [x] Implement `_ensure_index(dimensions)`.
- [x] Implement `_to_document(record, namespace)`.
- [x] Implement `_to_match(hit, namespace)`.
- [x] Implement `_build_filter_clauses(filters, namespace)`.
- [x] Implement `upsert()`.
- [x] Implement `query()`.
- [x] Implement `delete()`.
- [x] Implement `describe()`.
- [x] Use deterministic document IDs: `namespace::record_id`.
- [x] Store `record_id`, `namespace`, `text`, metadata, and vector.
- [x] Use bulk indexing for multi-record upserts.
- [x] Return `VectorSearchResult` with `VectorSearchMatch` objects.
- [x] Support `$eq`, `$in`, `$gte`, and `$lte` filters.

### Index Mapping

- [x] Define mapping for keyword fields: `namespace`, `record_id`, `product_id`, `sku`, `brand`, `category`, `status`.
- [x] Define mapping for text fields: `name`, `text`.
- [x] Define mapping for numeric fields: `stock`, `price`.
- [x] Define `dense_vector` mapping for `vector`.
- [x] Confirm embedding dimension before creating the index.
- [x] Ensure cosine similarity matches current vector scoring assumptions.
- [ ] Decide how to handle existing index with wrong dimensions.

### Inventory Sync

- [ ] Verify `/inventory/items/upsert` writes to Elasticsearch.
- [ ] Verify `/inventory/items/delete` deletes from Elasticsearch.
- [ ] Verify `/inventory/sync/rebuild` recreates Elasticsearch records from catalog.
- [ ] Verify `/inventory/sync/status` reports correct vector count.
- [ ] Verify disabled `include_in_rag=false` items are removed from Elasticsearch.

### Search Behavior

- [ ] Test exact SKU lookup.
- [ ] Test exact product-name lookup.
- [ ] Test category-filtered search.
- [ ] Test brand-filtered search.
- [ ] Test price-filtered search.
- [ ] Test stock-filtered search.
- [ ] Test semantic product recommendation query.
- [ ] Test "no matching product" query.
- [ ] Confirm current planner, gates, reranker, and verifier still run.

### Phase 2 Hybrid Search

- [ ] Add optional Elasticsearch lexical query method.
- [ ] Query BM25 across `sku`, `name`, `brand`, `category`, and `text`.
- [ ] Boost exact SKU and phrase name matches.
- [ ] Add typo tolerance with fuzzy matching where useful.
- [ ] Merge BM25 and vector candidate pools.
- [ ] Preserve dense and lexical scores in diagnostics.
- [ ] Keep existing product-type, category, exact lookup, and reranker gates.
- [ ] Evaluate Reciprocal Rank Fusion after the simple merge works.

### Tests

- [ ] Add `tests/test_elasticsearch_store.py`.
- [ ] Mock Elasticsearch client for adapter unit tests.
- [ ] Test missing URL failure.
- [ ] Test client auth setup.
- [ ] Test deterministic IDs.
- [ ] Test upsert payload shape.
- [ ] Test query result conversion.
- [ ] Test namespace filtering.
- [ ] Test metadata filter conversion.
- [ ] Test delete behavior.
- [ ] Test describe behavior.
- [ ] Add inventory service test with mocked Elasticsearch backend.
- [ ] Run `pytest tests/test_elasticsearch_store.py`.
- [ ] Run `pytest tests/test_vector_store.py`.
- [ ] Run `pytest tests/test_inventory_api.py`.

### Local Validation

- [ ] Start local Elasticsearch.
- [ ] Confirm `curl http://localhost:9200` works.
- [ ] Start FastAPI backend.
- [ ] Run `/inventory/sync/rebuild`.
- [ ] Run `/inventory/status`.
- [ ] Run `/inventory/sync/status`.
- [ ] Run sample exact lookup query.
- [ ] Run sample semantic query.
- [ ] Inspect Elasticsearch index document count.
- [ ] Inspect one indexed document.

### Evaluation

- [ ] Build or reuse inventory evaluation set.
- [ ] Compare local vector backend against Elasticsearch vector backend.
- [ ] Compare Python lexical plus vector against Elasticsearch BM25 plus vector.
- [ ] Measure top-1 exact product accuracy.
- [ ] Measure top-5 recall.
- [ ] Measure wrong-category retrieval rate.
- [ ] Measure abstention correctness.
- [ ] Measure p50 and p95 latency.
- [ ] Record whether Elasticsearch improves quality enough to justify operational cost.

### Completion Criteria

- [ ] `VECTOR_DB=elasticsearch` starts the API successfully.
- [ ] Inventory upsert indexes records into Elasticsearch.
- [ ] Inventory delete removes records from Elasticsearch.
- [ ] Sync rebuild restores Elasticsearch from catalog.
- [ ] Search returns expected products from Elasticsearch-backed retrieval.
- [ ] Local vector backend still works.
- [ ] Existing tests still pass.
- [ ] New Elasticsearch tests pass.
- [ ] Evaluation shows improvement or documents clear failure modes.

## Strategic Decision

Use Elasticsearch as a search and vector retrieval mirror for the inventory RAG system.

Do not make Elasticsearch the source of truth. The operational inventory database or existing catalog mirror remains authoritative. Elasticsearch should be a derived index used for:

- exact SKU and product-name lookup
- BM25 keyword retrieval
- dense vector retrieval
- structured filtering by category, brand, stock, status, and price
- future hybrid retrieval using BM25 plus vector search

## Expected Improvement

Elasticsearch should improve retrieval quality and production readiness, especially for real inventory queries where exact identifiers and structured filters matter.

Primary gains:

- better exact lookup for SKU, product name, brand, and category
- faster filtering for stock, price, status, category, and brand
- improved typo-tolerant and partial text search
- scalable indexing beyond the local JSONL vector store
- better observability and debugging of search behavior
- future support for hybrid BM25 plus vector retrieval

Non-goals:

- it will not automatically fix hallucinated answers
- it will not replace the planner, reranker, verifier, or business rules
- it will not repair poor product metadata
- it will not make weak recommendations strong by itself

## External Requirements

External product data is not required.

External infrastructure is required:

- local Elasticsearch via Docker, or
- self-managed Elasticsearch, or
- Elastic Cloud

Python dependency required:

```txt
elasticsearch
```

Official references:

- Python client: https://www.elastic.co/docs/reference/elasticsearch/clients/python
- Python client connection: https://www.elastic.co/docs/reference/elasticsearch/clients/python/connecting
- Dense vector mapping: https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/dense-vector/

## Current Repo Integration Points

Relevant files:

- `app/retrieval/vector_store_base.py`
- `app/retrieval/local_store.py`
- `app/retrieval/pinecone_store.py`
- `app/retrieval/milvus_store.py`
- `app/core/settings.py`
- `app/services/inventory_service.py`
- `config/config.dev.yaml`
- `pyproject.toml`
- `requirements.txt`
- `tests/test_vector_store.py`
- `tests/test_inventory_api.py`

Current vector providers:

- `local`
- `pinecone`
- `milvus`

Target provider to add:

- `elasticsearch`

## Phase 1: Add Elasticsearch as a VectorStore Backend

Goal: make Elasticsearch satisfy the existing `VectorStore` contract without changing inventory search behavior too much.

### 1. Add dependency

Update:

- `pyproject.toml`
- `requirements.txt`

Add:

```txt
elasticsearch
```

Recommended: pin a compatible major version once the Elasticsearch server version is chosen.

Example:

```txt
elasticsearch>=8,<9
```

Use this if running Elasticsearch 8.x.

### 2. Add settings

Update `app/core/settings.py`.

Add fields:

```python
elasticsearch_url: str | None = Field(default=None, alias="ELASTICSEARCH_URL")
elasticsearch_api_key: str | None = Field(default=None, alias="ELASTICSEARCH_API_KEY")
elasticsearch_username: str | None = Field(default=None, alias="ELASTICSEARCH_USERNAME")
elasticsearch_password: str | None = Field(default=None, alias="ELASTICSEARCH_PASSWORD")
elasticsearch_index_name: str | None = Field(default="inventory-rag", alias="ELASTICSEARCH_INDEX_NAME")
```

Add non-secret config values to `non_secret_config()`:

- `elasticsearch_url`
- `elasticsearch_index_name`

Do not expose:

- `elasticsearch_api_key`
- `elasticsearch_password`

Add YAML override support under `vector_store`:

```yaml
vector_store:
  elasticsearch_url: http://localhost:9200
  elasticsearch_index_name: inventory-rag
```

### 3. Extend VectorStoreConfig

Update `app/retrieval/vector_store_base.py`.

Add enum value:

```python
class VectorStoreProvider(StrEnum):
    LOCAL = "local"
    PINECONE = "pinecone"
    MILVUS = "milvus"
    ELASTICSEARCH = "elasticsearch"
```

Add config fields:

```python
elasticsearch_url: str | None = None
elasticsearch_api_key: str | None = None
elasticsearch_username: str | None = None
elasticsearch_password: str | None = None
elasticsearch_index_name: str | None = None
```

Update `vector_store_config_from_settings()` to pass those settings into `VectorStoreConfig`.

### 4. Wire provider factory

Update `build_vector_store()` in `app/retrieval/vector_store_base.py`:

```python
if resolved_config.provider is VectorStoreProvider.ELASTICSEARCH:
    from app.retrieval.elasticsearch_store import ElasticsearchVectorStore

    return ElasticsearchVectorStore(resolved_config)
```

### 5. Create Elasticsearch adapter

Create:

```txt
app/retrieval/elasticsearch_store.py
```

Implement:

```python
class ElasticsearchVectorStore(VectorStore):
    def upsert(self, records: list[VectorRecord], *, namespace: str | None = None) -> None:
        ...

    def query(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filters: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> VectorSearchResult:
        ...

    def delete(self, record_ids: list[str], *, namespace: str | None = None) -> None:
        ...

    def describe(self, *, namespace: str | None = None) -> VectorStoreStats:
        ...
```

Required private helpers:

- `_client()`
- `_index_name()`
- `_ensure_index(dimensions: int)`
- `_to_document(record: VectorRecord, namespace: str | None)`
- `_to_match(hit: dict, namespace: str | None)`
- `_build_filter_clauses(filters: dict[str, Any] | None, namespace: str | None)`

### 6. Initial index mapping

Use one document per vector record.

Suggested mapping:

```json
{
  "mappings": {
    "properties": {
      "namespace": { "type": "keyword" },
      "record_id": { "type": "keyword" },
      "product_id": { "type": "keyword" },
      "sku": { "type": "keyword" },
      "name": { "type": "text" },
      "brand": { "type": "keyword" },
      "brand_key": { "type": "keyword" },
      "category": { "type": "keyword" },
      "category_key": { "type": "keyword" },
      "status": { "type": "keyword" },
      "status_key": { "type": "keyword" },
      "stock": { "type": "integer" },
      "price": { "type": "float" },
      "currency": { "type": "keyword" },
      "include_in_rag": { "type": "boolean" },
      "text": { "type": "text" },
      "vector": {
        "type": "dense_vector",
        "dims": 1024,
        "index": true,
        "similarity": "cosine"
      }
    }
  }
}
```

Important: `dims` must match the embedding model output. For `BAAI/bge-m3`, confirm the runtime embedding dimension before locking this mapping.

### 7. Upsert behavior

Implementation rules:

- use `_id = namespace + "::" + record_id`
- store `record_id` separately as a keyword field
- store `record.text` in `text`
- flatten safe metadata fields into top-level document fields
- keep the original metadata object if useful
- use Elasticsearch bulk helper for multiple records

Pseudo-shape:

```python
from elasticsearch import Elasticsearch, helpers

actions = [
    {
        "_op_type": "index",
        "_index": self._index_name(),
        "_id": self._document_id(record.record_id, effective_namespace),
        "_source": self._to_document(record, effective_namespace),
    }
    for record in records
]
helpers.bulk(self._client(), actions)
```

### 8. Query behavior

Phase 1 query should map to dense vector retrieval plus filters.

Use kNN or script score depending on the installed Elasticsearch version and client support.

Preferred query shape:

```python
response = client.search(
    index=index_name,
    knn={
        "field": "vector",
        "query_vector": query_vector,
        "k": top_k,
        "num_candidates": max(top_k * 10, 50),
        "filter": filter_clauses,
    },
    size=top_k,
)
```

Return:

- `VectorSearchResult`
- provider = `VectorStoreProvider.ELASTICSEARCH`
- matches = list of `VectorSearchMatch`
- score = Elasticsearch `_score`
- metadata = source metadata excluding `vector`
- text = source `text`
- namespace = source `namespace`

### 9. Delete behavior

Delete by deterministic `_id`:

```python
client.delete(index=index_name, id=document_id, ignore_status=[404])
```

If namespace is missing, delete all matching `record_id` values across namespaces with `delete_by_query`.

### 10. Describe behavior

Return:

- provider
- index name
- document count
- namespace
- metadata with cluster/index status if cheap to fetch

Use `client.count()` with namespace filter for namespace-specific count.

## Phase 2: Use Elasticsearch BM25 for Inventory Lexical Search

Goal: stop scanning the whole catalog in Python for lexical candidates once the catalog grows.

Current behavior:

- dense candidates come from `vector_store.query()`
- lexical candidates are computed in Python by `_lexical_candidate_scores()`

Target behavior:

- dense candidates from Elasticsearch vector query
- lexical candidates from Elasticsearch BM25 query
- merge both pools before the existing product-type, category, exact lookup, and reranker gates

Do not remove the existing gates. They are the quality control layer.

### Proposed adapter extension

Add optional method on Elasticsearch store:

```python
def lexical_query(
    self,
    query_text: str,
    *,
    top_k: int,
    filters: dict[str, Any] | None = None,
    namespace: str | None = None,
) -> VectorSearchResult:
    ...
```

Avoid adding this method to the base abstract class until needed by more than one backend.

### BM25 query fields

Search across:

- `sku`
- `name`
- `brand`
- `category`
- `text`

Suggested query:

```json
{
  "bool": {
    "filter": [],
    "should": [
      { "term": { "sku": { "value": "exact sku", "boost": 8 } } },
      { "match_phrase": { "name": { "query": "query text", "boost": 5 } } },
      { "multi_match": {
        "query": "query text",
        "fields": ["name^4", "sku^5", "brand^2", "category^2", "text"],
        "type": "best_fields",
        "fuzziness": "AUTO"
      }}
    ],
    "minimum_should_match": 1
  }
}
```

### Fusion strategy

Start simple:

- get top N dense candidates
- get top N BM25 candidates
- union by product ID
- preserve both score types in trace diagnostics
- allow existing `EcommerceReranker` to make final ranking decision

Later:

- add Reciprocal Rank Fusion
- tune field boosts using evaluation set

## Phase 3: Inventory Service Integration

Goal: let `InventoryService` exploit Elasticsearch when available without breaking local tests.

Potential changes in `app/services/inventory_service.py`:

- keep `_dense_candidate_scores()` unchanged for base compatibility
- add `_external_lexical_candidate_scores()` for Elasticsearch only
- fall back to current `_lexical_candidate_scores()` when provider is not Elasticsearch
- preserve existing diagnostics keys
- add new diagnostics keys only if useful:
  - `elastic_lexical_raw_matches`
  - `elastic_dense_raw_matches`
  - `elastic_hybrid_pool_candidates`

Guardrail:

- do not bypass `_item_matches_filters()`
- do not bypass product-type gate
- do not bypass category gate
- do not bypass exact lookup gate
- do not bypass reranker

## Phase 4: Configuration

Update `config/config.dev.yaml`:

```yaml
vector_store:
  provider: elasticsearch
  metric: cosine
  namespace:
  inventory_namespace: inventory
  local_store_path: data/agentic_store/local_vectors.jsonl
  elasticsearch_url: http://localhost:9200
  elasticsearch_index_name: inventory-rag
```

Environment variable alternative:

```bash
export VECTOR_DB=elasticsearch
export ELASTICSEARCH_URL=http://localhost:9200
export ELASTICSEARCH_INDEX_NAME=inventory-rag
```

For secured clusters:

```bash
export ELASTICSEARCH_API_KEY=...
```

or:

```bash
export ELASTICSEARCH_USERNAME=elastic
export ELASTICSEARCH_PASSWORD=...
```

## Phase 5: Local Elasticsearch for Development

Suggested Docker command for local development:

```bash
docker run --name inventory-elasticsearch \
  -p 9200:9200 \
  -e discovery.type=single-node \
  -e xpack.security.enabled=false \
  docker.elastic.co/elasticsearch/elasticsearch:8.19.3
```

Check health:

```bash
curl http://localhost:9200
```

Note: version should match the Python client compatibility target.

## Phase 6: Sync and Validation

Start backend:

```bash
cd "/home/sonjoy/Bar tax/bangla-tax-rag"
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 4893
```

Rebuild inventory search index:

```bash
curl -X POST http://127.0.0.1:4893/inventory/sync/rebuild
```

Check status:

```bash
curl http://127.0.0.1:4893/inventory/status
curl http://127.0.0.1:4893/inventory/sync/status
```

Test exact lookup:

```bash
curl -X POST http://127.0.0.1:4893/inventory/search \
  -H "Content-Type: application/json" \
  -d '{"query_text":"OFF-WBD-008","top_k":5}'
```

Test semantic lookup:

```bash
curl -X POST http://127.0.0.1:4893/inventory/search \
  -H "Content-Type: application/json" \
  -d '{"query_text":"wireless headphones under 300 in stock","top_k":5}'
```

Test category filter:

```bash
curl -X POST http://127.0.0.1:4893/inventory/search \
  -H "Content-Type: application/json" \
  -d '{"query_text":"premium travel audio","top_k":5,"filters":{"category":"Audio"}}'
```

## Phase 7: Tests

Add unit tests for the adapter with mocked Elasticsearch client.

Suggested test file:

```txt
tests/test_elasticsearch_store.py
```

Test cases:

- builds client with URL and API key
- fails clearly when URL is missing
- upsert creates deterministic IDs
- upsert stores namespace and metadata
- query converts Elasticsearch hits into `VectorSearchMatch`
- query applies namespace filter
- query converts `$eq`, `$in`, `$gte`, `$lte` filters
- delete removes by deterministic ID
- describe returns count and index name

Inventory integration tests:

- service boots with `VECTOR_DB=elasticsearch` when adapter is mocked
- `/inventory/items/upsert` calls vector upsert
- `/inventory/search` still returns valid `InventorySearchResponse`
- `/inventory/sync/rebuild` deletes stale vectors and upserts enabled items

Run:

```bash
pytest tests/test_elasticsearch_store.py tests/test_vector_store.py tests/test_inventory_api.py
```

## Phase 8: Evaluation

Do not judge success by "it runs."

Judge success by retrieval quality.

Create or reuse inventory eval queries:

- exact SKU lookup
- exact product name lookup
- typo query
- category constrained query
- price constrained query
- stock constrained query
- "no matching product" query
- wrong-category trap query
- semantic recommendation query

Metrics:

- top-1 exact product accuracy
- top-5 recall
- wrong-category retrieval rate
- abstention correctness
- latency p50 and p95
- answer factuality after planner and verifier

Compare:

- local vector only
- current Python lexical plus local vector
- Elasticsearch vector only
- Elasticsearch BM25 plus vector hybrid

## Completion Criteria

The Elasticsearch integration is complete when:

- `VECTOR_DB=elasticsearch` starts the API successfully
- `/inventory/items/upsert` indexes inventory records into Elasticsearch
- `/inventory/search` returns expected products from Elasticsearch-backed retrieval
- `/inventory/sync/rebuild` restores a clean index from the catalog
- local provider tests still pass
- Elasticsearch adapter tests pass
- inventory API tests pass
- eval results show improvement or identify clear failure modes

## Strategic Guardrails

If the catalog is small, Elasticsearch may add operational cost without meaningful quality gains.

Do the integration if at least one condition is true:

- catalog is expected to exceed a few thousand products
- exact SKU/name lookup matters
- filtering and faceting need to be fast
- typo tolerance matters
- production observability matters
- hybrid BM25 plus vector retrieval is part of the research story

If none of those are true, improve metadata quality, reranking, and evaluation first.
