import json
import re
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

RATE_EXPLICIT_SIGNALS = (
    "করহার",
    "আয়কর হার",
    "আয়কর হার",
    "tax rate",
    "rate",
    "শতাংশ",
    "স্ল্যাব",
    "slab",
)
DEFINITION_SIGNALS = ("সংজ্ঞা", "অর্থ", "ব্যাখ্যা", "definition", "means", "defined")
AMENDMENT_SIGNALS = ("সংশোধন", "প্রতিস্থাপন", "সংযোজন", "বিলোপ", "পরিবর্তন", "amend", "substitut")
PROCEDURE_SIGNALS = (
    "পদ্ধতি",
    "প্রক্রিয়া",
    "প্রক্রিয়া",
    "দাখিল",
    "রিটার্ন",
    "আবেদন",
    "পরিশোধ",
    "জমা",
    "শর্ত",
    "করতে হবে",
    "procedure",
    "process",
    "submit",
    "payment",
)
CALCULATION_SIGNALS = ("গণনা", "পরিগণনা", "হিসাব", "calculate", "calculation")
COMPARISON_SIGNALS = ("তুলনা", "অপেক্ষা", "comparison", "compare")
AUTHORITY_SIGNALS = ("কর্তৃপক্ষ", "বোর্ড", "কমিশনার", "authority", "commissioner")
EXAMPLE_SIGNALS = ("উদাহরণ", "example")

GENERIC_CONTEXT_LABELS = {
    "",
    "বিষয়",
    "বিষয়",
    "পরিপত্র",
    "সূচিপত্র",
    "table of contents",
    "appendix",
    "annexure",
}
BOILERPLATE_LINE_PREFIXES = (
    "গণপ্রজাতন্ত্রী বাংলাদেশ সরকার",
    "জাতীয় রাজস্ব বোর্ড",
    "জাতীয় রাজস্ব বোর্ড",
    "রাজস্ব ভবন",
    "সেগুনবাগিচা",
    "সেগ্তনবাগিচা",
    "নথি নং",
    "তারিখ",
    "পরিপত্র-",
    "পরিপত্র ",
    "www.",
)


def _contains_any(text: str, signals: tuple[str, ...]) -> bool:
    return any(signal in text for signal in signals)


def _looks_like_rate_lookup(chunk: ChunkRecord, heading_text: str, normalized_text: str) -> bool:
    if chunk.chunk_type == "table":
        return True
    if _contains_any(heading_text, RATE_EXPLICIT_SIGNALS):
        return True
    if "করহার" in normalized_text or "আয়কর হার" in normalized_text or "আয়কর হার" in normalized_text:
        return True
    if ("%" in normalized_text or "শতাংশ" in normalized_text) and _contains_any(
        normalized_text,
        ("কর", "আয়", "আয়", "সারচার্জ", "মোট আয়", "মোট আয়"),
    ):
        return True
    return False


def _clean_context_label(text: str | None) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip(" -:;।|ঃ")
    if cleaned.lower() in GENERIC_CONTEXT_LABELS:
        return ""
    if re.fullmatch(r"[০-৯0-9]+[।.)]?", cleaned):
        return ""
    if re.fullmatch(r"[০-৯0-9/., -]+", cleaned):
        return ""
    if re.fullmatch(r"[\d%/., -]+", cleaned):
        return ""
    if re.fullmatch(r"[A-Za-z]{1,4}", cleaned):
        return ""
    return truncate_text(cleaned, max_length=90)


def _line_is_boilerplate(line: str) -> bool:
    cleaned = line.strip()
    if not cleaned:
        return True
    return any(cleaned.startswith(prefix) for prefix in BOILERPLATE_LINE_PREFIXES)


def _marker_is_usable(marker: str | None) -> bool:
    if not marker:
        return False
    cleaned = marker.strip()
    if not cleaned:
        return False
    if len(cleaned) > 24:
        return False
    if cleaned.count(".") >= 3:
        return False
    if len(re.sub(r"[^০-৯0-9A-Za-zক-হ]", "", cleaned)) < 1:
        return False
    return True


def build_context_label(chunk: ChunkRecord) -> str:
    for heading in reversed(chunk.heading_path):
        label = _clean_context_label(heading)
        if label:
            return label

    for line in chunk.original_text.splitlines():
        if _line_is_boilerplate(line):
            continue
        line_label = _clean_context_label(line)
        if line_label:
            return line_label

    if _marker_is_usable(chunk.subsection_id):
        return f"উপধারা/অনুচ্ছেদ {chunk.subsection_id}"
    if _marker_is_usable(chunk.section_id):
        return f"ধারা {chunk.section_id}"
    if chunk.chunk_type == "table":
        return "এই সারণি"
    if chunk.chunk_type == "example":
        return "এই উদাহরণ"
    if chunk.chunk_type == "appendix":
        return "এই পরিশিষ্ট"
    return "এই অংশ"


def infer_question_type(chunk: ChunkRecord) -> str:
    heading_text = " ".join(chunk.heading_path).lower()
    normalized_text = chunk.normalized_text.lower()
    combined_text = f"{heading_text}\n{normalized_text}"

    if _looks_like_rate_lookup(chunk, heading_text, normalized_text):
        return "rate_lookup"
    if chunk.chunk_type == "example" or _contains_any(combined_text, EXAMPLE_SIGNALS):
        return "example_based"
    if _contains_any(combined_text, AMENDMENT_SIGNALS):
        return "amendment"
    if _contains_any(combined_text, DEFINITION_SIGNALS):
        return "definition"
    if _contains_any(combined_text, CALCULATION_SIGNALS):
        return "calculation"
    if _contains_any(combined_text, COMPARISON_SIGNALS):
        return "comparison"
    if _contains_any(combined_text, AUTHORITY_SIGNALS):
        return "authority_conflict"
    if _contains_any(combined_text, PROCEDURE_SIGNALS):
        return "procedure"
    return "procedure"


def build_candidate_question_text(chunk: ChunkRecord, question_type: str) -> str:
    context_label = build_context_label(chunk)
    tax_year_prefix = f"{chunk.tax_year} করবর্ষে " if chunk.tax_year else ""
    if question_type == "rate_lookup":
        return f"{tax_year_prefix}{context_label} অনুযায়ী প্রযোজ্য করহার বা হার কী?"
    if question_type == "definition":
        return f"{context_label} অংশে কোন শব্দ বা ধারণার সংজ্ঞা কীভাবে দেওয়া হয়েছে?"
    if question_type == "amendment":
        return f"{context_label} অংশে কী পরিবর্তন বা সংশোধন আনা হয়েছে?"
    if question_type == "procedure":
        return f"{context_label} অনুযায়ী কী নিয়ম বা প্রক্রিয়া অনুসরণ করতে হবে?"
    if question_type == "example_based":
        return f"{context_label} উদাহরণে কী দেখানো হয়েছে?"
    if question_type == "calculation":
        return f"{context_label} অনুযায়ী গণনার নিয়ম কী?"
    if question_type == "comparison":
        return f"{context_label} অংশে কী তুলনা করা হয়েছে?"
    return f"{context_label} অনুযায়ী কোন কর্তৃপক্ষ বা আইনি অবস্থান প্রযোজ্য?"


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
            notes="Machine-generated annotation seed. Verify question, answer, tax year, and evidence manually.",
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
