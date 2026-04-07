import json
from pathlib import Path

from app.core.logging import get_logger
from app.core.schemas import AnnotatedQuestion, AnnotationCandidate, ChunkRecord, DatasetValidationReport
from app.core.utils import detect_text_language, truncate_text
from app.retrieval.sparse import load_chunk_records_from_jsonl

logger = get_logger(__name__)

ALLOWED_QUESTION_TYPES = {
    "rate_lookup",
    "definition",
    "amendment",
    "procedure",
    "example_based",
    "calculation",
    "comparison",
    "authority_conflict",
}


def infer_question_type(chunk: ChunkRecord) -> str:
    heading_text = " ".join(chunk.heading_path).lower()
    normalized_text = chunk.normalized_text.lower()
    if chunk.chunk_type == "table" or "করহার" in heading_text or "rate" in normalized_text:
        return "rate_lookup"
    if "সংজ্ঞা" in heading_text or "definition" in heading_text:
        return "definition"
    if "সংশোধন" in heading_text or "amend" in normalized_text:
        return "amendment"
    if chunk.chunk_type == "example" or "উদাহরণ" in heading_text:
        return "example_based"
    if "প্রক্রিয়া" in heading_text or "পদ্ধতি" in heading_text or "procedure" in normalized_text:
        return "procedure"
    if "গণনা" in normalized_text or "calculate" in normalized_text:
        return "calculation"
    if "তুলনা" in normalized_text or "comparison" in normalized_text:
        return "comparison"
    if "authority" in normalized_text or "কর্তৃপক্ষ" in normalized_text:
        return "authority_conflict"
    return "definition"


def build_candidate_question_text(chunk: ChunkRecord, question_type: str) -> str:
    section_text = chunk.subsection_id or chunk.section_id or "এই অংশ"
    if question_type == "rate_lookup":
        return f"{chunk.tax_year or 'প্রাসঙ্গিক'} করবর্ষে ধারা {section_text} অনুযায়ী করহার কত?"
    if question_type == "definition":
        return f"ধারা {section_text} এ কী সংজ্ঞা দেওয়া হয়েছে?"
    if question_type == "amendment":
        return f"ধারা {section_text} এ কী সংশোধন আনা হয়েছে?"
    if question_type == "procedure":
        return f"ধারা {section_text} অনুযায়ী প্রক্রিয়াটি কী?"
    if question_type == "example_based":
        return f"{section_text} সম্পর্কিত উদাহরণে কী দেখানো হয়েছে?"
    if question_type == "calculation":
        return f"ধারা {section_text} অনুযায়ী গণনার নিয়ম কী?"
    if question_type == "comparison":
        return f"ধারা {section_text} এ কী তুলনা করা হয়েছে?"
    return f"ধারা {section_text} অনুযায়ী কর্তৃপক্ষগত অবস্থান কী?"


def build_annotation_candidates_from_chunks(chunk_records: list[ChunkRecord]) -> list[AnnotationCandidate]:
    candidates: list[AnnotationCandidate] = []
    for chunk in chunk_records:
        question_type = infer_question_type(chunk)
        candidate = AnnotationCandidate(
            question_id=f"cand-{chunk.chunk_id}",
            source_chunk_id=chunk.chunk_id,
            source_doc_id=chunk.doc_id,
            source_doc_title=chunk.doc_title,
            question_text=build_candidate_question_text(chunk, question_type),
            question_type=question_type,
            heading_path=chunk.heading_path,
            tax_year=chunk.tax_year,
            section_id=chunk.section_id,
            subsection_id=chunk.subsection_id,
            chunk_type=chunk.chunk_type,
            evidence_snippet=truncate_text(chunk.original_text, max_length=280),
            notes="Candidate generated from chunk metadata. Fill gold answer manually.",
        )
        candidates.append(candidate)
    return candidates


def write_annotation_candidates(candidates: list[AnnotationCandidate], output_path: str | Path) -> Path:
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(json.dumps(candidate.model_dump(), ensure_ascii=False) + "\n")
    logger.info("Annotation candidates written", extra={"output_path": str(output_file), "count": len(candidates)})
    return output_file


def validate_annotated_dataset(
    dataset_path: str | Path,
    chunk_jsonl_path: str | Path,
) -> DatasetValidationReport:
    known_chunks = {chunk.chunk_id for chunk in load_chunk_records_from_jsonl(chunk_jsonl_path)}
    total_rows = 0
    valid_rows = 0
    errors: list[str] = []
    warnings: list[str] = []
    with Path(dataset_path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped_line = line.strip()
            if not stripped_line:
                continue
            total_rows += 1
            try:
                row = AnnotatedQuestion.model_validate_json(stripped_line)
            except Exception as exc:
                errors.append(f"Line {line_number}: invalid schema: {exc}")
                continue
            row_errors: list[str] = []
            if row.question_type not in ALLOWED_QUESTION_TYPES:
                row_errors.append(f"invalid question_type '{row.question_type}'")
            if row.expected_tax_year and len(row.expected_tax_year.split("-")) != 2:
                row_errors.append("expected_tax_year must look like YYYY-YYYY")
            missing_chunk_ids = [chunk_id for chunk_id in row.expected_chunk_ids if chunk_id not in known_chunks]
            if missing_chunk_ids:
                row_errors.append(f"unknown chunk ids: {', '.join(missing_chunk_ids)}")
            if not row.answer_text and not row.should_abstain:
                row_errors.append("answer_text is required unless should_abstain is true")
            if not row.answer_language:
                warnings.append(f"Line {line_number}: answer_language missing, consider setting it explicitly.")
            if row_errors:
                errors.append(f"Line {line_number}: " + "; ".join(row_errors))
                continue
            valid_rows += 1
    return DatasetValidationReport(
        valid=len(errors) == 0,
        dataset_path=str(dataset_path),
        total_rows=total_rows,
        valid_rows=valid_rows,
        invalid_rows=total_rows - valid_rows,
        errors=errors,
        warnings=warnings,
    )
