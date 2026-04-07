# bangla-tax-rag

A clean, research-ready Python 3.11 scaffold for experimenting with Bangla tax document ingestion, retrieval, generation, and evaluation workflows.

## Structure

```text
bangla-tax-rag/
├── app/
├── config/
├── data/
├── docs/
├── indexes/
├── results/
├── scripts/
└── tests/
```

## Quickstart

1. Create and activate a Python 3.11 virtual environment.
2. Copy `.env.example` to `.env`.
3. Install dependencies:

```bash
make install
```

4. Run the API:

```bash
make run-api
```

5. Run the Streamlit UI:

```bash
make run-ui
```

6. Run tests:

```bash
make test
```

## API Endpoints

- `GET /health`
- `POST /ingest`
- `POST /query`
- `POST /evaluate`

## Notes

- The code is intentionally minimal and scaffold-focused.
- Retrieval, generation, and evaluation modules contain starter placeholders only.
- Configuration defaults live in `config/config.dev.yaml`.
