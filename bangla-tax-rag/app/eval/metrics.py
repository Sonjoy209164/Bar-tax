import json
from pathlib import Path


def evaluate_predictions(predictions: list[str], references: list[str]) -> dict[str, object]:
    paired_count = min(len(predictions), len(references))
    score = 1.0 if paired_count > 0 else 0.0
    return {
        "metric_name": "placeholder_exact_match",
        "score": score,
        "details": {
            "prediction_count": len(predictions),
            "reference_count": len(references),
            "paired_count": paired_count,
        },
    }


def evaluate_dataset_file(dataset_path: str | Path) -> dict[str, object]:
    dataset_records = []
    with Path(dataset_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped_line = line.strip()
            if not stripped_line:
                continue
            dataset_records.append(json.loads(stripped_line))
    predictions = [record.get("prediction", "") for record in dataset_records]
    references = [record.get("reference", "") for record in dataset_records]
    metrics = evaluate_predictions(predictions, references)
    metrics["details"]["dataset_size"] = len(dataset_records)
    return metrics
