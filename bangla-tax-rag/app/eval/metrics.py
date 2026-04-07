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
