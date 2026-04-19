import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "evaluation" / "commerce_questions.jsonl"
CATALOG_PATH = ROOT / "data" / "inventory" / "catalog.jsonl"
REQUIRED_KEYS = {
    "question_id",
    "category",
    "intent",
    "query",
    "expected_primary_product_ids",
    "acceptable_alternative_product_ids",
    "forbidden_product_ids",
    "must_abstain",
    "required_metadata_fields",
    "constraints",
    "evaluation_focus",
}


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
    return rows


def test_commerce_eval_dataset_has_seed_coverage() -> None:
    rows = _load_jsonl(DATASET_PATH)

    assert len(rows) >= 100
    assert len({row["question_id"] for row in rows}) == len(rows)

    categories = {str(row["category"]) for row in rows}
    assert {
        "audio",
        "computing",
        "wearables",
        "electronics",
        "home_appliances",
        "mobile",
        "office",
        "networking_storage",
        "cross_sell",
        "abstain",
    }.issubset(categories)

    abstain_count = sum(1 for row in rows if row["must_abstain"])
    assert abstain_count >= 10

    for row in rows:
        assert REQUIRED_KEYS.issubset(row)
        assert isinstance(row["query"], str) and row["query"].strip()
        assert isinstance(row["required_metadata_fields"], list)
        assert isinstance(row["constraints"], dict)
        assert isinstance(row["evaluation_focus"], list)


def test_commerce_eval_dataset_references_known_catalog_products() -> None:
    rows = _load_jsonl(DATASET_PATH)
    catalog_rows = _load_jsonl(CATALOG_PATH)
    known_product_ids = {str(row["product_id"]) for row in catalog_rows}

    for row in rows:
        for key in (
            "expected_primary_product_ids",
            "acceptable_alternative_product_ids",
            "forbidden_product_ids",
        ):
            for product_id in row[key]:
                assert product_id in known_product_ids, f"{row['question_id']} references missing product_id {product_id}"
