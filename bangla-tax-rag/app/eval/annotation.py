from pathlib import Path

from app.core.logging import get_logger
from app.core.schemas import AnnotatedQuestion

logger = get_logger(__name__)


def merge_annotation_files(input_paths: list[str | Path]) -> list[AnnotatedQuestion]:
    merged_by_question_id: dict[str, AnnotatedQuestion] = {}
    for input_path in input_paths:
        with Path(input_path).open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped_line = line.strip()
                if not stripped_line:
                    continue
                annotated_question = AnnotatedQuestion.model_validate_json(stripped_line)
                merged_by_question_id[annotated_question.question_id] = annotated_question
    merged_rows = list(merged_by_question_id.values())
    logger.info("Merged annotation files", extra={"input_count": len(input_paths), "row_count": len(merged_rows)})
    return merged_rows


def write_merged_annotations(rows: list[AnnotatedQuestion], output_path: str | Path) -> Path:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(row.model_dump_json(ensure_ascii=False) + "\n")
    return output_file
