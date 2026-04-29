import argparse
from copy import deepcopy
import csv
import json
import re
import shlex
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.utils import extract_query_section_references, normalize_text, normalize_whitespace

BANGLA_PATTERN = re.compile(r"[\u0980-\u09FF]")
LATIN_PATTERN = re.compile(r"[A-Za-z]")
LATIN_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z'.-]*")
NUMBER_PATTERN = re.compile(r"\d")
PERCENT_PATTERN = re.compile(r"(?:%|শতাংশ|percent)", re.IGNORECASE)
MONEY_PATTERN = re.compile(r"(?:টাকা|taka|lakh|crore|কোটি|লক্ষ)", re.IGNORECASE)
TABLE_SIGNAL_PATTERN = re.compile(
    r"(?:করহার|মোট আয়|এইচ\s*এস|H\.?\s*S\.?\s*Code|ক্রমিক|বিবরণ|বর্ণনা|slab|rate|amount)",
    re.IGNORECASE,
)
HS_CODE_PATTERN = re.compile(r"\b\d{2}\.\d{2}(?:\.\d{2,4}){0,2}\b")
RATE_TABLE_HEADER_PATTERN = re.compile(r"(?:মোট\s+আয়|total\s+income).{0,80}(?:হার|rate)|(?:হার|rate).{0,80}(?:মোট\s+আয়|total\s+income)", re.IGNORECASE | re.DOTALL)
FORM_SIGNAL_PATTERN = re.compile(
    r"(?:\bname\s+of\b|\bnational\s+id\b|\bdate\s+of\s+birth\b|\bemail\b|\bsignature\b|\bTIN\b|"
    r"\bassessment\s+year\b|\breturn\s+form\b|নাম\s*[:：]|জাতীয়\s+পরিচয়|স্বাক্ষর\s*[:：]|ঠিকানা\s*[:：]|ফরম\s*[:：-]|রিটার্ন\s+ফরম)",
    re.IGNORECASE,
)
FORM_BLANK_PATTERN = re.compile(r"(?:\.{4,}|_{4,}|[|]\s*[|]\s*[|])")
TABLE_ROW_SIGNAL_PATTERN = re.compile(
    r"(?:%|শতাংশ|টাকা|taka|Tk\.?|লক্ষ|কোটি|H\.?\s*S\.?\s*Code|\b\d{2}\.\d{2}\b)",
    re.IGNORECASE,
)
SPACED_BANGLA_LETTER_PATTERN = re.compile(r"(?<!\S)(?:[\u0980-\u09FF]\s+){2,}[\u0980-\u09FF](?!\S)")
FOOTER_PATTERN = re.compile(
    r"^(?:\d+\s*\|\s*)?(?:আ\s*য়\s*ক\s*র|আয়কর)\s+(?:পরিপত্র|পতরপত্র|পররপত্র).{0,40}\d{4}\s*-\s*\d{4}\s*$"
)
PAGE_ONLY_PATTERN = re.compile(r"^(?:পৃষ্ঠা\s*)?\d{1,4}$", re.IGNORECASE)
SECTION_LIKE_PATTERN = re.compile(r"^(?:ধারা\s*)?\d+[A-Za-z]?(?:\.\d+)*$")
SECTION_PREFIX_PATTERN = re.compile(r"^(?:ধারা|section)\s*", re.IGNORECASE)
SRO_PATTERN = re.compile(r"(?:এস\.?\s*আর\.?\s*ও|S\.?\s*R\.?\s*O\.?)", re.IGNORECASE)
DATE_LIKE_PATTERN = re.compile(r"^\d{1,4}[./-]\d{1,4}(?:[./-]\d{1,4})?$")
MEMO_LIKE_PATTERN = re.compile(r"^\d{1,4}(?:\.\d{1,4}){3,}")
BANGLA_OCR_ARTIFACT_PATTERN = re.compile(
    r"(?:\s\u09CD|\u09CD\s|ক্লষে|প্ররদ|অনুমযো|যোগ্দয|নহবে|মাধআ্য|আয়কর\s+মঅ|"
    r"সংশৌধ|অবরকা|পহয়ে|প্রতিস্থাকপর|অধ্যন|দধােরা|সংযৌজন|করযোগহবে|"
    r"রিটাদারখিল|পররপত্র|পথরথশষ্ট|রেন-মাস|বের\)|অতরকর|সংকত্রান|"
    r"পরিচাক্ল|নিয়রূপ|অনুমযোোগ)"
)
STRICT_TABLE_CONFIDENCE = 0.75
GOLD_SECTION_CONFIDENCE = 0.55
GOLD_EXTRACTION_CONFIDENCE = 0.75
CANONICAL_CHUNK_FIELDS = [
    "chunk_id",
    "doc_id",
    "doc_title",
    "doc_type",
    "authority_level",
    "tax_year",
    "effective_start",
    "effective_end",
    "page_no",
    "section_id",
    "subsection_id",
    "appendix_id",
    "sro_id",
    "chunk_type",
    "heading_path",
    "original_text",
    "normalized_text",
    "cross_refs",
]
LEGAL_ENGLISH_TOKENS = {
    "act",
    "acts",
    "advance",
    "amount",
    "assessment",
    "authority",
    "bank",
    "board",
    "business",
    "challan",
    "chapter",
    "clause",
    "code",
    "commissioner",
    "company",
    "contract",
    "deduction",
    "form",
    "government",
    "income",
    "law",
    "legal",
    "loan",
    "nbr",
    "of",
    "ordinance",
    "part",
    "payment",
    "person",
    "rate",
    "royalties",
    "return",
    "rule",
    "schedule",
    "sch",
    "serial",
    "sub",
    "subsection",
    "section",
    "sro",
    "tax",
    "taxes",
    "technical",
    "third",
    "tin",
    "tk",
    "vat",
    "withholding",
}
SHORT_NOISE_TOKENS = {
    "haifa",
    "ft",
    "as",
    "ga]",
    "ga",
    "wl",
    "wit",
    "wa",
    "ala",
    "|",
}


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Clean and structure Pilot14 parsed chunks into canonical research artifacts. "
            "Raw OCR/non-OCR parses are preserved; outputs are written to data/processed/btax14/structured by default."
        )
    )
    parser.add_argument("--manifest", default="data/metadata/corpus_manifest_btax14.csv")
    parser.add_argument("--source-dir", default="data/processed/btax14/ocr_per_doc")
    parser.add_argument("--fallback-dir", default="data/processed/btax14/per_doc")
    parser.add_argument("--output-dir", default="data/processed/btax14/structured")
    parser.add_argument("--publish-dir", default="data/processed/btax14")
    parser.add_argument("--ocr-pdf-dir", default="data/processed/btax14/ocr_pdfs")
    parser.add_argument("--raw-pdf-dir", default="data/raw/btax14/pdfs")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--results-dir", default="results/pilot14")
    parser.add_argument("--source-label", default="ocr")
    parser.add_argument("--min-clean-chars", type=int, default=20)
    parser.add_argument("--keep-noise", action="store_true", help="Keep noise chunks in canonical chunks.jsonl.")
    return parser


def read_manifest(path: Path) -> dict[str, dict[str, str]]:
    return {row["doc_id"]: row for row in csv.DictReader(path.open(encoding="utf-8"))}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_heading_path(values: list[Any]) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        text = clean_text(str(value))
        if not text or is_noise_line(text):
            continue
        if text not in cleaned:
            cleaned.append(text)
    return cleaned


def collapse_spaced_bangla_letters(line: str) -> str:
    def join_match(match: re.Match[str]) -> str:
        return match.group(0).replace(" ", "")

    return SPACED_BANGLA_LETTER_PATTERN.sub(join_match, line)


def strip_low_signal_latin_noise(line: str) -> str:
    quality = text_quality(line)
    if quality["bangla_ratio"] < 0.25:
        return line

    def clean_token(match: re.Match[str]) -> str:
        token = match.group(0)
        normalized_token = re.sub(r"[^A-Za-z]", "", token).lower()
        if not normalized_token:
            return token
        if normalized_token in LEGAL_ENGLISH_TOKENS:
            return token
        if len(normalized_token) <= 4:
            return ""
        if re.fullmatch(r"[ceosx]{5,}", normalized_token):
            return ""
        return token

    stripped = LATIN_TOKEN_PATTERN.sub(clean_token, line)
    return normalize_whitespace(stripped)


def clean_text(text: str) -> str:
    lines = []
    for raw_line in text.replace("\u00a0", " ").splitlines():
        line = normalize_whitespace(raw_line.strip())
        if not line:
            continue
        line = collapse_spaced_bangla_letters(line)
        line = strip_low_signal_latin_noise(line)
        if not line:
            continue
        if is_noise_line(line):
            continue
        lines.append(line)
    return normalize_whitespace("\n".join(lines))


def is_noise_line(line: str) -> bool:
    normalized = normalize_text(line).strip()
    lowered = normalized.lower()
    if not normalized:
        return True
    if lowered in SHORT_NOISE_TOKENS:
        return True
    if FOOTER_PATTERN.match(normalized):
        return True
    if PAGE_ONLY_PATTERN.match(normalized):
        return True
    if len(normalized) <= 2 and not NUMBER_PATTERN.search(normalized):
        return True
    if len(normalized) <= 6 and not BANGLA_PATTERN.search(normalized) and not NUMBER_PATTERN.search(normalized):
        return True
    return False


def looks_form_like(text: str, heading_path: list[str]) -> bool:
    combined = f"{' '.join(heading_path)}\n{text}"
    if not combined.strip():
        return False
    signal_count = len(FORM_SIGNAL_PATTERN.findall(combined))
    blank_count = len(FORM_BLANK_PATTERN.findall(combined))
    colon_label_count = len(re.findall(r"(?:^|\n)\s*(?:\d+[.)]?\s*)?[\w\u0980-\u09FF /()-]{2,35}\s*:", combined))
    return signal_count >= 2 or (signal_count >= 1 and blank_count >= 2) or (signal_count >= 1 and colon_label_count >= 5)


def looks_table_like(text: str, chunk_type: str, heading_path: list[str]) -> bool:
    combined = f"{' '.join(heading_path)}\n{text}"
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    if len(lines) < 2:
        if not lines:
            return False
        single_row_table = "|" in lines[0] and row_signal_score(lines[0]) >= 3
        return (chunk_type == "table" or single_row_table) and not looks_form_like(text, heading_path)
    numeric_lines = sum(1 for line in lines if len(NUMBER_PATTERN.findall(line)) >= 2)
    pipe_rows = sum(1 for line in lines if "|" in line)
    spaced_column_rows = sum(1 for line in lines if re.search(r"\S\s{3,}\S", line))
    hs_code_rows = sum(1 for line in lines if HS_CODE_PATTERN.search(line))
    amount_or_percent_rows = sum(1 for line in lines if MONEY_PATTERN.search(line) or PERCENT_PATTERN.search(line))
    has_table_signal = bool(TABLE_SIGNAL_PATTERN.search(combined))
    has_rate_table_header = bool(RATE_TABLE_HEADER_PATTERN.search(combined))
    form_like = looks_form_like(text, heading_path)

    strong_grid_layout = pipe_rows >= 2 or spaced_column_rows >= 3 or hs_code_rows >= 2
    strong_rate_table = has_rate_table_header and amount_or_percent_rows >= 2 and len(lines) >= 4
    compact_rate_list = (
        amount_or_percent_rows >= 2
        and numeric_lines >= 2
        and len(lines) >= 4
        and bool(re.match(r"^\d+[.)]?$", lines[0]) or (heading_path and re.match(r"^\d+[.)]?$", heading_path[-1])))
    )
    source_table_with_structure = (
        chunk_type == "table"
        and has_table_signal
        and numeric_lines >= 3
        and len(lines) >= 4
    )
    if form_like and not strong_rate_table and hs_code_rows < 2:
        return False
    return strong_grid_layout or strong_rate_table or compact_rate_list or source_table_with_structure


def table_confidence(text: str, chunk_type: str, heading_path: list[str]) -> float:
    combined = f"{' '.join(heading_path)}\n{text}"
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    if not looks_table_like(text, chunk_type, heading_path):
        return 0.0
    pipe_rows = sum(1 for line in lines if "|" in line)
    numeric_lines = sum(1 for line in lines if len(NUMBER_PATTERN.findall(line)) >= 2)
    hs_code_rows = sum(1 for line in lines if HS_CODE_PATTERN.search(line))
    amount_or_percent_rows = sum(1 for line in lines if MONEY_PATTERN.search(line) or PERCENT_PATTERN.search(line))
    if RATE_TABLE_HEADER_PATTERN.search(combined) and amount_or_percent_rows >= 2:
        return 0.9
    if hs_code_rows >= 2:
        return 0.85
    if amount_or_percent_rows >= 2 and numeric_lines >= 2:
        return 0.8
    if pipe_rows >= 3 and TABLE_SIGNAL_PATTERN.search(combined):
        return 0.78
    if chunk_type == "table" and amount_or_percent_rows >= 2:
        return 0.68
    return 0.58


def infer_clean_chunk_type(
    row: dict[str, Any],
    *,
    is_strict_table: bool,
    is_form_candidate: bool,
    clean_section_id: str | None,
) -> str:
    source_type = row.get("chunk_type") or "text"
    if source_type in {"example", "appendix"}:
        return source_type
    if is_strict_table:
        return "table"
    if is_form_candidate:
        return "form"
    if source_type == "table":
        return "section" if clean_section_id else "text"
    return source_type


def text_quality(text: str) -> dict[str, Any]:
    total = max(len(text), 1)
    bangla_count = len(BANGLA_PATTERN.findall(text))
    latin_count = len(LATIN_PATTERN.findall(text))
    digit_count = len(NUMBER_PATTERN.findall(text))
    return {
        "char_count": len(text),
        "bangla_ratio": bangla_count / total,
        "latin_ratio": latin_count / total,
        "digit_count": digit_count,
        "line_count": len([line for line in text.splitlines() if line.strip()]),
    }


def classify_section_reference(value: Any) -> dict[str, Any]:
    raw = "" if value is None else str(value).strip()
    cleaned = normalize_text(raw)
    cleaned = SECTION_PREFIX_PATTERN.sub("", cleaned).strip(" :;।()[]")
    if not cleaned:
        return {"raw": raw, "canonical": None, "kind": "missing", "confidence": 0.0}
    if SRO_PATTERN.search(cleaned):
        return {"raw": raw, "canonical": None, "kind": "sro_reference", "confidence": 0.25}
    if HS_CODE_PATTERN.search(cleaned):
        return {"raw": raw, "canonical": None, "kind": "hs_code", "confidence": 0.2}
    if DATE_LIKE_PATTERN.match(cleaned):
        return {"raw": raw, "canonical": None, "kind": "date_like", "confidence": 0.1}
    if MEMO_LIKE_PATTERN.match(cleaned):
        return {"raw": raw, "canonical": None, "kind": "memo_like", "confidence": 0.1}
    match = re.fullmatch(r"(\d{1,3}[A-Za-z]?)(?:\.\d{1,3})*", cleaned)
    if match:
        first_number_match = re.match(r"\d+", cleaned)
        first_number = int(first_number_match.group(0)) if first_number_match else 0
        if 1 <= first_number <= 400:
            return {"raw": raw, "canonical": cleaned, "kind": "legal_or_outline_section", "confidence": 0.78}
        return {"raw": raw, "canonical": None, "kind": "numeric_nonsection", "confidence": 0.2}
    if re.fullmatch(r"\d{4,}", cleaned):
        return {"raw": raw, "canonical": None, "kind": "year_or_form_code", "confidence": 0.12}
    return {"raw": raw, "canonical": None, "kind": "unknown", "confidence": 0.2}


def first_line_has_section_heading(text: str, *, allow_numbered_heading: bool = False) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    first_line = normalize_text(lines[0])
    if re.match(r"^(?:ধারা|section)\s*\d{1,3}[A-Za-z]?(?:\.\d+)*\b", first_line, flags=re.IGNORECASE):
        return True
    if allow_numbered_heading and re.match(r"^\d{1,3}[A-Za-z]?(?:\.\d+)*\s*[.)।:-]\s+\S+", first_line):
        return True
    return False


def select_section_metadata(
    raw_section_id: Any,
    section_candidates: list[str],
    *,
    text: str = "",
    source_chunk_type: str = "",
    source_doc_type: str = "",
) -> dict[str, Any]:
    raw_info = classify_section_reference(raw_section_id)
    candidate_infos = [raw_info]
    candidate_infos.extend(classify_section_reference(candidate) for candidate in section_candidates)
    valid_contextual_infos = [info for info in candidate_infos[1:] if info["canonical"]]
    heading_supports_raw = first_line_has_section_heading(
        text,
        allow_numbered_heading=source_doc_type == "act",
    ) and source_chunk_type in {"section", "text", "appendix", ""}

    if raw_info["canonical"] and not valid_contextual_infos and not heading_supports_raw:
        raw_info = {
            **raw_info,
            "canonical": None,
            "kind": f"uncontextualized_{raw_info['kind']}",
            "confidence": min(raw_info["confidence"], 0.45),
        }
        candidate_infos[0] = raw_info

    if valid_contextual_infos:
        best = max(valid_contextual_infos, key=lambda item: item["confidence"])
    else:
        best = raw_info
    return {
        "raw_section_id": raw_section_id,
        "canonical": best["canonical"] if best["confidence"] >= 0.55 else None,
        "kind": best["kind"],
        "confidence": best["confidence"],
        "candidate_infos": candidate_infos,
    }


def clean_cross_refs(raw_refs: list[Any], section_candidates: list[str]) -> list[str]:
    refs: list[str] = []
    for value in [*raw_refs, *section_candidates]:
        info = classify_section_reference(value)
        if info["canonical"]:
            refs.append(info["canonical"])
    return list(dict.fromkeys(refs))


def detect_ocr_risk(text: str, quality: dict[str, Any], *, is_form_candidate: bool) -> list[str]:
    risks: list[str] = []
    if "\ufffd" in text:
        risks.append("replacement_character")
    if re.search(r"\bNee\b", text) and re.search(r"(?:অনি|উস|ইন)", text):
        risks.append("known_noisy_ocr_phrase")
    if quality["bangla_ratio"] >= 0.15 and quality["latin_ratio"] >= 0.18 and not is_form_candidate:
        risks.append("mixed_latin_inside_bangla")
    tokens = [token for token in re.split(r"\s+", text) if token]
    if tokens:
        isolated_bangla = sum(1 for token in tokens if re.fullmatch(r"[\u0980-\u09FF]", token.strip(".,;:()[]{}|")))
        if isolated_bangla / len(tokens) >= 0.18 and isolated_bangla >= 8:
            risks.append("fragmented_bangla_spacing")
    if re.search(r"(?:ecece|sccee|eeee|০০০০০০০০০)", text, re.IGNORECASE):
        risks.append("form_or_ocr_fill_noise")
    if BANGLA_OCR_ARTIFACT_PATTERN.search(text):
        risks.append("bangla_ocr_artifact")
    return list(dict.fromkeys(risks))


def extraction_confidence(quality: dict[str, Any], ocr_risk_labels: list[str]) -> float:
    score = 1.0
    if quality["char_count"] < 80:
        score -= 0.08
    score -= min(0.5, len(ocr_risk_labels) * 0.12)
    if quality["bangla_ratio"] < 0.05 and quality["latin_ratio"] < 0.05:
        score -= 0.25
    return round(max(0.05, min(1.0, score)), 3)


def canonical_from_enriched(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in CANONICAL_CHUNK_FIELDS}


def is_meaningful_short(row: dict[str, Any]) -> bool:
    text = row.get("original_text", "").strip()
    if not text:
        return False
    normalized = normalize_text(text)
    if row.get("appendix_id") or row.get("sro_id"):
        return True
    if row.get("structure", {}).get("is_form_candidate"):
        return True
    if row.get("structure", {}).get("is_table_candidate") and TABLE_ROW_SIGNAL_PATTERN.search(text):
        return True
    if row.get("section_id") and row.get("structure", {}).get("section_confidence", 0.0) >= 0.55:
        return True
    if SECTION_LIKE_PATTERN.match(normalized):
        return True
    if any(marker in normalized for marker in ("পরিশিষ্ট", "তফসিল", "প্রজ্ঞাপন", "ফরম")):
        return True
    if SRO_PATTERN.search(text) or HS_CODE_PATTERN.search(text):
        return True
    if (MONEY_PATTERN.search(text) or PERCENT_PATTERN.search(text)) and NUMBER_PATTERN.search(text):
        return True
    return False


def infer_noise_reason(cleaned_text: str, row: dict[str, Any], *, min_clean_chars: int) -> str | None:
    if not cleaned_text.strip():
        return "empty_after_cleanup"
    if len(cleaned_text.strip()) < min_clean_chars:
        if not SECTION_LIKE_PATTERN.search(cleaned_text) and not MONEY_PATTERN.search(cleaned_text):
            return "too_short_after_cleanup"
    return None


def chunk_record_fields(row: dict[str, Any], *, clean_original_text: str, clean_normalized_text: str, heading_path: list[str], chunk_type: str) -> dict[str, Any]:
    return {
        "chunk_id": row["chunk_id"],
        "doc_id": row["doc_id"],
        "doc_title": row["doc_title"],
        "doc_type": row["doc_type"],
        "authority_level": row["authority_level"],
        "tax_year": row.get("tax_year"),
        "effective_start": row.get("effective_start"),
        "effective_end": row.get("effective_end"),
        "page_no": row["page_no"],
        "section_id": row.get("section_id"),
        "subsection_id": row.get("subsection_id"),
        "appendix_id": row.get("appendix_id"),
        "sro_id": row.get("sro_id"),
        "chunk_type": chunk_type,
        "heading_path": heading_path,
        "original_text": clean_original_text,
        "normalized_text": clean_normalized_text,
        "cross_refs": row.get("cross_refs", []),
    }


def should_merge_short(row: dict[str, Any], *, min_clean_chars: int) -> bool:
    if is_meaningful_short(row):
        return False
    text = row.get("original_text", "").strip()
    if not text:
        return False
    if len(text) >= max(80, min_clean_chars):
        return False
    if row.get("chunk_type") in {"table", "appendix", "example", "form"}:
        return False
    return True


def merge_text_records(short_records: list[dict[str, Any]], target: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(target)
    merged_from = []
    for record in short_records:
        merged_from.extend(record.get("structure", {}).get("merged_from_chunk_ids", [record["chunk_id"]]))
    existing = merged.get("structure", {}).get("merged_from_chunk_ids", [merged["chunk_id"]])
    merged_from.extend(existing)
    merged_from = list(dict.fromkeys(merged_from))

    text_parts = [record.get("original_text", "").strip() for record in short_records]
    text_parts.append(target.get("original_text", "").strip())
    merged_text = "\n".join(part for part in text_parts if part)
    merged["original_text"] = merged_text
    merged["normalized_text"] = normalize_text(merged_text)
    merged["quality"] = text_quality(merged_text)

    heading_path: list[str] = []
    for record in [*short_records, target]:
        heading_path.extend(record.get("heading_path", []))
    merged["heading_path"] = list(dict.fromkeys(item for item in heading_path if item))

    section_candidates = extract_query_section_references(merged_text)
    section_metadata = select_section_metadata(merged.get("section_id"), section_candidates, text=merged_text)
    merged["section_id"] = section_metadata["canonical"]
    merged["cross_refs"] = clean_cross_refs(merged.get("cross_refs", []), section_candidates)

    structure = deepcopy(merged.get("structure", {}))
    structure.update(
        {
            "merged_from_chunk_ids": merged_from,
            "merge_source_count": len(merged_from),
            "section_candidates": section_candidates,
            "raw_section_id": section_metadata["raw_section_id"],
            "section_kind": section_metadata["kind"],
            "section_confidence": section_metadata["confidence"],
            "section_candidate_infos": section_metadata["candidate_infos"],
            "noise_reason": None,
        }
    )
    merged["structure"] = structure
    merged["metadata_confidence"] = round(max(float(merged.get("metadata_confidence", 0.0)), section_metadata["confidence"]), 3)
    merged["extraction_confidence"] = extraction_confidence(
        merged["quality"],
        detect_ocr_risk(
            merged_text,
            merged["quality"],
            is_form_candidate=bool(structure.get("is_form_candidate")),
        ),
    )
    return merged


def merge_short_records(records: list[dict[str, Any]], *, min_clean_chars: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_doc[record["doc_id"]].append(record)

    merged_records: list[dict[str, Any]] = []
    rejected_short_records: list[dict[str, Any]] = []
    stats = {"merged_short_chunk_count": 0, "unmerged_short_chunk_count": 0}

    for doc_id, doc_records in sorted(by_doc.items()):
        doc_records = sorted(doc_records, key=lambda row: (row["page_no"], row["chunk_id"]))
        pending_short: list[dict[str, Any]] = []
        doc_output_start = len(merged_records)
        for record in doc_records:
            if should_merge_short(record, min_clean_chars=min_clean_chars):
                pending_short.append(record)
                continue
            if pending_short:
                near_enough = record["page_no"] - pending_short[0]["page_no"] <= 1
                if near_enough:
                    record = merge_text_records(pending_short, record)
                    stats["merged_short_chunk_count"] += len(pending_short)
                else:
                    for short_record in pending_short:
                        rejected = deepcopy(short_record)
                        rejected.setdefault("structure", {})["noise_reason"] = "unmerged_short_fragment"
                        rejected_short_records.append(rejected)
                        stats["unmerged_short_chunk_count"] += 1
                pending_short = []
            merged_records.append(record)

        if pending_short:
            previous_index = len(merged_records) - 1
            if previous_index >= doc_output_start:
                previous = merged_records[previous_index]
                near_enough = pending_short[0]["page_no"] - previous["page_no"] <= 1
                if near_enough:
                    merged_records[previous_index] = merge_text_records(pending_short, previous)
                    stats["merged_short_chunk_count"] += len(pending_short)
                else:
                    for short_record in pending_short:
                        rejected = deepcopy(short_record)
                        rejected.setdefault("structure", {})["noise_reason"] = "unmerged_short_fragment"
                        rejected_short_records.append(rejected)
                        stats["unmerged_short_chunk_count"] += 1
            else:
                for short_record in pending_short:
                    rejected = deepcopy(short_record)
                    rejected.setdefault("structure", {})["noise_reason"] = "unmerged_short_fragment"
                    rejected_short_records.append(rejected)
                    stats["unmerged_short_chunk_count"] += 1

    return merged_records, rejected_short_records, stats


def read_pdf_page_text(pdf_path: Path, page_no: int) -> str:
    if not pdf_path.exists():
        return ""
    try:
        import fitz

        with fitz.open(pdf_path) as document:
            if page_no < 1 or page_no > document.page_count:
                return ""
            return document[page_no - 1].get_text("text")
    except Exception:
        return ""


def find_page_pdf(doc_id: str, manifest_row: dict[str, str], ocr_pdf_dir: Path, raw_pdf_dir: Path) -> Path:
    ocr_path = ocr_pdf_dir / f"{doc_id}.ocr.pdf"
    if ocr_path.exists():
        return ocr_path
    return raw_pdf_dir / manifest_row.get("file_name", "")


def build_pages(
    *,
    manifest: dict[str, dict[str, str]],
    chunks: list[dict[str, Any]],
    ocr_pdf_dir: Path,
    raw_pdf_dir: Path,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        grouped[(chunk["doc_id"], chunk["page_no"])].append(chunk)
    pages: list[dict[str, Any]] = []
    for doc_id, manifest_row in sorted(manifest.items()):
        page_total = int(manifest_row.get("page_count") or 0)
        doc_pdf_path = find_page_pdf(doc_id, manifest_row, ocr_pdf_dir, raw_pdf_dir)
        available_pages = sorted(page_no for item_doc_id, page_no in grouped if item_doc_id == doc_id)
        if page_total <= 0 and available_pages:
            page_total = max(available_pages)
        for page_no in range(1, page_total + 1):
            page_chunks = sorted(grouped.get((doc_id, page_no), []), key=lambda chunk: chunk["chunk_id"])
            text = "\n\n".join(chunk["original_text"] for chunk in page_chunks if chunk["original_text"])
            page_status = "structured_text"
            if not page_chunks:
                text = clean_text(read_pdf_page_text(doc_pdf_path, page_no))
                page_status = "pdf_text_only" if text else "blank_or_unreadable"
            sections = sorted({chunk.get("section_id") for chunk in page_chunks if chunk.get("section_id")})
            pages.append(
                {
                    "page_id": f"{doc_id}:page:{page_no}",
                    "doc_id": doc_id,
                    "page_no": page_no,
                    "chunk_ids": [chunk["chunk_id"] for chunk in page_chunks],
                    "section_ids": sections,
                    "text": text,
                    "normalized_text": normalize_text(text),
                    "quality": text_quality(text),
                    "has_structured_chunks": bool(page_chunks),
                    "page_status": page_status,
                    "source_pdf": str(doc_pdf_path),
                }
            )
    return pages


def build_table_records(chunks: list[dict[str, Any]], enriched_by_chunk_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for chunk in chunks:
        enriched = enriched_by_chunk_id[chunk["chunk_id"]]
        if not enriched["structure"].get("is_strict_table"):
            continue
        tables.append(
            {
                "table_id": f"{chunk['chunk_id']}:table",
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "page_no": chunk["page_no"],
                "section_id": chunk.get("section_id"),
                "tax_year": chunk.get("tax_year"),
                "heading_path": chunk.get("heading_path", []),
                "text": chunk["original_text"],
                "normalized_text": chunk["normalized_text"],
                "quality": enriched["quality"],
                "table_confidence": enriched["structure"].get("table_confidence", 0.0),
                "structure_kind": enriched["structure"].get("structure_kind", "table"),
            }
        )
    return tables


def split_row_cells(line: str) -> list[str]:
    if "|" in line:
        cells = [normalize_whitespace(cell.strip()) for cell in line.split("|")]
    else:
        cells = [normalize_whitespace(cell.strip()) for cell in re.split(r"\s{2,}", line)]
    return [cell for cell in cells if cell]


def row_signal_score(line: str) -> int:
    score = 0
    if "|" in line:
        score += 1
    if HS_CODE_PATTERN.search(line):
        score += 2
    if TABLE_ROW_SIGNAL_PATTERN.search(line):
        score += 2
    if len(NUMBER_PATTERN.findall(line)) >= 2:
        score += 1
    if re.match(r"^\s*(?:\d+|[০-৯]+)[.)।-]?\s+", line):
        score += 1
    return score


def build_table_rows(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table in tables:
        table_rows = []
        for line in table["text"].splitlines():
            line = clean_text(line)
            if not line or len(line) < 4:
                continue
            signal_score = row_signal_score(line)
            if signal_score < 3:
                continue
            cells = split_row_cells(line)
            table_rows.append((line, cells, signal_score))

        for index, (line, cells, signal_score) in enumerate(table_rows, 1):
            row_confidence = min(float(table.get("table_confidence", 0.0)), 0.95)
            if signal_score >= 4:
                row_confidence = min(0.95, row_confidence + 0.05)
            rows.append(
                {
                    "row_id": f"{table['table_id']}:r{index:03d}",
                    "table_id": table["table_id"],
                    "chunk_id": table["chunk_id"],
                    "doc_id": table["doc_id"],
                    "page_no": table["page_no"],
                    "section_id": table.get("section_id"),
                    "tax_year": table.get("tax_year"),
                    "row_index": index,
                    "cells": cells,
                    "row_text": line,
                    "normalized_text": normalize_text(line),
                    "quality": text_quality(line),
                    "row_signal_score": signal_score,
                    "row_confidence": round(row_confidence, 3),
                }
            )
    return rows


def build_form_records(chunks: list[dict[str, Any]], enriched_by_chunk_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    forms: list[dict[str, Any]] = []
    for chunk in chunks:
        enriched = enriched_by_chunk_id[chunk["chunk_id"]]
        if not enriched["structure"].get("is_form_candidate"):
            continue
        forms.append(
            {
                "form_id": f"{chunk['chunk_id']}:form",
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "page_no": chunk["page_no"],
                "section_id": chunk.get("section_id"),
                "tax_year": chunk.get("tax_year"),
                "heading_path": chunk.get("heading_path", []),
                "text": chunk["original_text"],
                "normalized_text": chunk["normalized_text"],
                "quality": enriched["quality"],
                "structure_kind": "form",
            }
        )
    return forms


def gold_readiness_reasons(chunk: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    structure = chunk.get("structure", {})
    quality = chunk.get("quality", {})
    if structure.get("ocr_risk_labels"):
        reasons.append("ocr_risk")
    if chunk.get("extraction_confidence", 0.0) < GOLD_EXTRACTION_CONFIDENCE:
        reasons.append("low_extraction_confidence")
    if structure.get("is_table_candidate") and not structure.get("is_strict_table"):
        reasons.append("weak_table_boundary")
    if chunk.get("chunk_type") == "form":
        reasons.append("form_requires_manual_review")
    if chunk.get("section_id") and structure.get("section_confidence", 0.0) < GOLD_SECTION_CONFIDENCE:
        reasons.append("low_section_confidence")
    if len(chunk.get("original_text", "").strip()) < 80 and chunk.get("chunk_type") != "table" and not chunk.get("section_id"):
        reasons.append("short_unanchored_text")
    if len(chunk.get("original_text", "").strip()) < 80 and not is_meaningful_short(chunk):
        reasons.append("short_weak_fragment")
    return reasons


def build_gold_review_sets(enriched_chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ready: list[dict[str, Any]] = []
    review_queue: list[dict[str, Any]] = []
    for chunk in enriched_chunks:
        reasons = gold_readiness_reasons(chunk)
        annotated = deepcopy(chunk)
        annotated["gold_readiness"] = {
            "is_gold_ready_candidate": not reasons,
            "exclusion_reasons": reasons,
            "requires_pdf_verification": True,
        }
        if reasons:
            review_queue.append(annotated)
        else:
            ready.append(annotated)
    return ready, review_queue


def add_node(nodes: dict[str, dict[str, Any]], node_id: str, **payload: Any) -> None:
    if node_id in nodes:
        nodes[node_id].update({key: value for key, value in payload.items() if value not in (None, "", [])})
        return
    nodes[node_id] = {"node_id": node_id, **payload}


def add_link(links: list[dict[str, Any]], seen: set[tuple[str, str, str]], source: str, target: str, relation: str, **metadata: Any) -> None:
    key = (source, target, relation)
    if key in seen:
        return
    seen.add(key)
    links.append({"source_node_id": source, "target_node_id": target, "relation": relation, "metadata": metadata})


def build_graph(
    *,
    manifest: dict[str, dict[str, str]],
    chunks: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    table_rows: list[dict[str, Any]],
    forms: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: dict[str, dict[str, Any]] = {}
    links: list[dict[str, Any]] = []
    seen_links: set[tuple[str, str, str]] = set()

    for doc_id, row in sorted(manifest.items()):
        doc_node_id = f"{doc_id}:doc"
        add_node(
            nodes,
            doc_node_id,
            node_type="document",
            doc_id=doc_id,
            title=row.get("title"),
            title_bn=row.get("title_bn"),
            authority_type=row.get("authority_type"),
            tax_year=row.get("tax_year"),
            source_url=row.get("source_url"),
        )

    for page in pages:
        doc_node_id = f"{page['doc_id']}:doc"
        page_node_id = page["page_id"]
        add_node(
            nodes,
            page_node_id,
            node_type="page",
            doc_id=page["doc_id"],
            page_no=page["page_no"],
            section_ids=page["section_ids"],
            quality=page["quality"],
        )
        add_link(links, seen_links, doc_node_id, page_node_id, "contains_page")

    for chunk in chunks:
        doc_id = chunk["doc_id"]
        doc_node_id = f"{doc_id}:doc"
        page_node_id = f"{doc_id}:page:{chunk['page_no']}"
        chunk_node_id = f"{chunk['chunk_id']}:chunk"
        add_node(
            nodes,
            chunk_node_id,
            node_type="chunk",
            chunk_id=chunk["chunk_id"],
            doc_id=doc_id,
            page_no=chunk["page_no"],
            section_id=chunk.get("section_id"),
            subsection_id=chunk.get("subsection_id"),
            chunk_type=chunk.get("chunk_type"),
            tax_year=chunk.get("tax_year"),
        )
        add_link(links, seen_links, page_node_id, chunk_node_id, "contains_chunk")
        add_link(links, seen_links, doc_node_id, chunk_node_id, "contains_chunk")

        section_id = chunk.get("section_id")
        if section_id:
            section_node_id = f"{doc_id}:section:{section_id}"
            add_node(nodes, section_node_id, node_type="section", doc_id=doc_id, section_id=section_id)
            add_link(links, seen_links, doc_node_id, section_node_id, "contains_section")
            add_link(links, seen_links, section_node_id, chunk_node_id, "section_contains_chunk")

        for cross_ref in chunk.get("cross_refs", []):
            add_link(links, seen_links, chunk_node_id, f"{doc_id}:ref:{cross_ref}", "mentions_reference", reference=cross_ref)

    for table in tables:
        table_node_id = f"{table['table_id']}:node"
        chunk_node_id = f"{table['chunk_id']}:chunk"
        add_node(
            nodes,
            table_node_id,
            node_type="table",
            table_id=table["table_id"],
            chunk_id=table["chunk_id"],
            doc_id=table["doc_id"],
            page_no=table["page_no"],
            section_id=table.get("section_id"),
        )
        add_link(links, seen_links, chunk_node_id, table_node_id, "has_table_candidate")

    for table_row in table_rows:
        row_node_id = f"{table_row['row_id']}:node"
        table_node_id = f"{table_row['table_id']}:node"
        add_node(
            nodes,
            row_node_id,
            node_type="table_row",
            row_id=table_row["row_id"],
            table_id=table_row["table_id"],
            chunk_id=table_row["chunk_id"],
            doc_id=table_row["doc_id"],
            page_no=table_row["page_no"],
            section_id=table_row.get("section_id"),
            row_index=table_row["row_index"],
        )
        add_link(links, seen_links, table_node_id, row_node_id, "has_table_row")

    for form in forms:
        form_node_id = f"{form['form_id']}:node"
        chunk_node_id = f"{form['chunk_id']}:chunk"
        add_node(
            nodes,
            form_node_id,
            node_type="form",
            form_id=form["form_id"],
            chunk_id=form["chunk_id"],
            doc_id=form["doc_id"],
            page_no=form["page_no"],
            section_id=form.get("section_id"),
        )
        add_link(links, seen_links, chunk_node_id, form_node_id, "has_form_candidate")

    graph_events: list[dict[str, Any]] = []
    graph_events.extend({"record_type": "node", **node} for node in nodes.values())
    graph_events.extend({"record_type": "link", **link} for link in links)
    return list(nodes.values()), links, graph_events


def write_command_provenance(results_dir: Path, args: argparse.Namespace) -> None:
    command = ["python", "scripts/structure_pilot14_corpus.py", *sys.argv[1:]]
    shell_path = results_dir / "pilot14_structure_command.sh"
    json_path = results_dir / "pilot14_structure_command.json"
    shell_path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n\n"
        'cd "/home/sonjoy/Bar tax/bangla-tax-rag"\n\n'
        + " ".join(shlex.quote(part) for part in command)
        + "\n",
        encoding="utf-8",
    )
    write_json(
        json_path,
        {
            "command": command,
            "created_at": datetime.now(UTC).isoformat(),
            "args": vars(args),
        },
    )


def write_artifacts(
    artifact_dir: Path,
    *,
    canonical_chunks: list[dict[str, Any]],
    enriched_chunks: list[dict[str, Any]],
    rejected_chunks: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    table_rows: list[dict[str, Any]],
    forms: list[dict[str, Any]],
    gold_ready_chunks: list[dict[str, Any]],
    gold_review_queue: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    links: list[dict[str, Any]],
    graph_events: list[dict[str, Any]],
    report: dict[str, Any],
) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(artifact_dir / "chunks.jsonl", canonical_chunks)
    write_jsonl(artifact_dir / "chunks_enriched.jsonl", enriched_chunks)
    write_jsonl(artifact_dir / "chunks_rejected.jsonl", rejected_chunks)
    write_jsonl(artifact_dir / "pages.jsonl", pages)
    write_jsonl(artifact_dir / "tables.jsonl", tables)
    write_jsonl(artifact_dir / "table_rows.jsonl", table_rows)
    write_jsonl(artifact_dir / "forms.jsonl", forms)
    write_jsonl(artifact_dir / "gold_ready_chunks.jsonl", gold_ready_chunks)
    write_jsonl(artifact_dir / "gold_review_queue.jsonl", gold_review_queue)
    write_jsonl(artifact_dir / "legal_graph_nodes.jsonl", nodes)
    write_jsonl(artifact_dir / "legal_graph_links.jsonl", links)
    write_jsonl(artifact_dir / "legal_graph.jsonl", graph_events)
    write_json(artifact_dir / "extraction_report.json", report)


def refresh_source_report(
    source_report: dict[str, Any],
    enriched_chunks: list[dict[str, Any]],
    rejected_chunks: list[dict[str, Any]],
) -> None:
    for item in source_report.values():
        item.update(
            {
                "kept_chunks": 0,
                "rejected_chunks": 0,
                "table_candidates": 0,
                "strict_tables": 0,
                "form_candidates": 0,
                "ocr_risk_chunks": 0,
                "merged_short_chunks": 0,
                "low_confidence_section_chunks": 0,
            }
        )
    for chunk in enriched_chunks:
        item = source_report[chunk["doc_id"]]
        item["kept_chunks"] += 1
        structure = chunk.get("structure", {})
        if structure.get("is_table_candidate"):
            item["table_candidates"] += 1
        if structure.get("is_strict_table"):
            item["strict_tables"] += 1
        if structure.get("is_form_candidate"):
            item["form_candidates"] += 1
        if structure.get("ocr_risk_labels"):
            item["ocr_risk_chunks"] += 1
        if len(structure.get("merged_from_chunk_ids", [])) > 1:
            item["merged_short_chunks"] += len(structure["merged_from_chunk_ids"]) - 1
        if 0 < structure.get("section_confidence", 0.0) < 0.55:
            item["low_confidence_section_chunks"] += 1
    for chunk in rejected_chunks:
        doc_id = chunk.get("doc_id")
        if doc_id in source_report:
            source_report[doc_id]["rejected_chunks"] += 1


def main() -> None:
    args = build_argument_parser().parse_args()
    manifest_path = Path(args.manifest)
    source_dir = Path(args.source_dir)
    fallback_dir = Path(args.fallback_dir)
    output_dir = Path(args.output_dir)
    publish_dir = Path(args.publish_dir)
    ocr_pdf_dir = Path(args.ocr_pdf_dir)
    raw_pdf_dir = Path(args.raw_pdf_dir)
    results_dir = Path(args.results_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not args.no_publish:
        publish_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    manifest = read_manifest(manifest_path)
    write_command_provenance(results_dir, args)

    enriched_chunks: list[dict[str, Any]] = []
    rejected_chunks: list[dict[str, Any]] = []
    source_report: dict[str, Any] = {}

    for doc_id, manifest_row in sorted(manifest.items()):
        source_path = source_dir / f"{doc_id}.jsonl"
        source_used = args.source_label
        if not source_path.exists():
            source_path = fallback_dir / f"{doc_id}.jsonl"
            source_used = "fallback_non_ocr"
        rows = read_jsonl(source_path)
        source_report[doc_id] = {
            "source_path": str(source_path),
            "source_used": source_used,
            "input_chunks": len(rows),
            "kept_chunks": 0,
            "rejected_chunks": 0,
            "table_candidates": 0,
        }

        for row in rows:
            cleaned_original = clean_text(row.get("original_text") or "")
            cleaned_normalized = normalize_text(cleaned_original)
            heading_path = clean_heading_path(row.get("heading_path", []))
            section_candidates = extract_query_section_references(cleaned_original)
            section_metadata = select_section_metadata(
                row.get("section_id"),
                section_candidates,
                text=cleaned_original,
                source_chunk_type=row.get("chunk_type") or "",
                source_doc_type=row.get("doc_type") or "",
            )
            clean_section_id = section_metadata["canonical"]
            is_form_candidate = looks_form_like(cleaned_original, heading_path)
            is_table_candidate = looks_table_like(cleaned_original, row.get("chunk_type") or "text", heading_path)
            table_conf = table_confidence(cleaned_original, row.get("chunk_type") or "text", heading_path)
            is_strict_table = is_table_candidate and table_conf >= STRICT_TABLE_CONFIDENCE
            chunk_type = infer_clean_chunk_type(
                row,
                is_strict_table=is_strict_table,
                is_form_candidate=is_form_candidate,
                clean_section_id=clean_section_id,
            )
            noise_reason = infer_noise_reason(cleaned_original, row, min_clean_chars=args.min_clean_chars)
            quality = text_quality(cleaned_original)
            ocr_risk_labels = detect_ocr_risk(cleaned_original, quality, is_form_candidate=is_form_candidate)
            structure_confidence = table_conf if is_table_candidate else 0.72 if is_form_candidate else 0.65
            if chunk_type == "section" and clean_section_id:
                structure_confidence = max(structure_confidence, section_metadata["confidence"])

            clean_record = chunk_record_fields(
                row,
                clean_original_text=cleaned_original,
                clean_normalized_text=cleaned_normalized,
                heading_path=heading_path,
                chunk_type=chunk_type,
            )
            clean_record["section_id"] = clean_section_id
            clean_record["cross_refs"] = clean_cross_refs(row.get("cross_refs", []), section_candidates)

            enriched = {
                **clean_record,
                "source": {
                    "parse_source": source_used,
                    "source_jsonl": str(source_path),
                    "source_url": manifest_row.get("source_url"),
                    "pdf_file_name": manifest_row.get("file_name"),
                },
                "quality": quality,
                "extraction_confidence": extraction_confidence(quality, ocr_risk_labels),
                "structure_confidence": round(structure_confidence, 3),
                "metadata_confidence": round(section_metadata["confidence"], 3),
                "structure": {
                    "is_table_candidate": is_table_candidate,
                    "is_strict_table": is_strict_table,
                    "is_form_candidate": is_form_candidate,
                    "structure_kind": "table" if is_strict_table else "table_candidate" if is_table_candidate else "form" if is_form_candidate else chunk_type,
                    "table_confidence": table_conf,
                    "section_candidates": section_candidates,
                    "raw_section_id": section_metadata["raw_section_id"],
                    "section_kind": section_metadata["kind"],
                    "section_confidence": section_metadata["confidence"],
                    "section_candidate_infos": section_metadata["candidate_infos"],
                    "ocr_risk_labels": ocr_risk_labels,
                    "noise_reason": noise_reason,
                },
            }

            if noise_reason == "too_short_after_cleanup" and is_meaningful_short(enriched):
                enriched["structure"]["noise_reason"] = None
                noise_reason = None

            if noise_reason == "empty_after_cleanup" and not args.keep_noise:
                rejected_chunks.append(enriched)
                continue

            enriched_chunks.append(enriched)

    merge_stats = {"merged_short_chunk_count": 0, "unmerged_short_chunk_count": 0}
    if not args.keep_noise:
        enriched_chunks, rejected_short_chunks, merge_stats = merge_short_records(
            enriched_chunks,
            min_clean_chars=args.min_clean_chars,
        )
        rejected_chunks.extend(rejected_short_chunks)

    canonical_chunks = [canonical_from_enriched(chunk) for chunk in enriched_chunks]
    enriched_by_chunk_id = {chunk["chunk_id"]: chunk for chunk in enriched_chunks}
    pages = build_pages(
        manifest=manifest,
        chunks=canonical_chunks,
        ocr_pdf_dir=ocr_pdf_dir,
        raw_pdf_dir=raw_pdf_dir,
    )
    tables = build_table_records(canonical_chunks, enriched_by_chunk_id)
    table_rows = build_table_rows(tables)
    forms = build_form_records(canonical_chunks, enriched_by_chunk_id)
    gold_ready_chunks, gold_review_queue = build_gold_review_sets(enriched_chunks)
    nodes, links, graph_events = build_graph(
        manifest=manifest,
        chunks=canonical_chunks,
        pages=pages,
        tables=tables,
        table_rows=table_rows,
        forms=forms,
    )
    refresh_source_report(source_report, enriched_chunks, rejected_chunks)

    section_confidence_counts = Counter(
        "missing"
        if chunk.get("structure", {}).get("section_confidence", 0.0) <= 0
        else "high"
        if chunk.get("structure", {}).get("section_confidence", 0.0) >= 0.75
        else "usable"
        if chunk.get("structure", {}).get("section_confidence", 0.0) >= 0.55
        else "low"
        for chunk in enriched_chunks
    )
    ocr_risk_counts = Counter(
        label
        for chunk in enriched_chunks
        for label in chunk.get("structure", {}).get("ocr_risk_labels", [])
    )
    page_status_counts = Counter(page.get("page_status", "unknown") for page in pages)
    broad_table_candidate_count = sum(1 for chunk in enriched_chunks if chunk.get("structure", {}).get("is_table_candidate"))

    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "manifest": str(manifest_path),
        "source_dir": str(source_dir),
        "fallback_dir": str(fallback_dir),
        "ocr_pdf_dir": str(ocr_pdf_dir),
        "raw_pdf_dir": str(raw_pdf_dir),
        "output_dir": str(output_dir),
        "publish_dir": None if args.no_publish else str(publish_dir),
        "document_count": len(manifest),
        "kept_chunk_count": len(canonical_chunks),
        "rejected_chunk_count": len(rejected_chunks),
        "page_count": len(pages),
        "table_candidate_count": broad_table_candidate_count,
        "strict_table_count": len(tables),
        "table_row_count": len(table_rows),
        "form_candidate_count": len(forms),
        "gold_ready_chunk_count": len(gold_ready_chunks),
        "gold_review_queue_count": len(gold_review_queue),
        "graph_node_count": len(nodes),
        "graph_link_count": len(links),
        **merge_stats,
        "source_report": source_report,
        "chunk_type_counts": Counter(chunk["chunk_type"] for chunk in canonical_chunks),
        "structure_kind_counts": Counter(chunk.get("structure", {}).get("structure_kind", "unknown") for chunk in enriched_chunks),
        "section_confidence_counts": section_confidence_counts,
        "ocr_risk_chunk_count": sum(1 for chunk in enriched_chunks if chunk.get("structure", {}).get("ocr_risk_labels")),
        "ocr_risk_counts": ocr_risk_counts,
        "page_status_counts": page_status_counts,
    }
    write_artifacts(
        output_dir,
        canonical_chunks=canonical_chunks,
        enriched_chunks=enriched_chunks,
        rejected_chunks=rejected_chunks,
        pages=pages,
        tables=tables,
        table_rows=table_rows,
        forms=forms,
        gold_ready_chunks=gold_ready_chunks,
        gold_review_queue=gold_review_queue,
        nodes=nodes,
        links=links,
        graph_events=graph_events,
        report=report,
    )
    if not args.no_publish:
        write_artifacts(
            publish_dir,
            canonical_chunks=canonical_chunks,
            enriched_chunks=enriched_chunks,
            rejected_chunks=rejected_chunks,
            pages=pages,
            tables=tables,
            table_rows=table_rows,
            forms=forms,
            gold_ready_chunks=gold_ready_chunks,
            gold_review_queue=gold_review_queue,
            nodes=nodes,
            links=links,
            graph_events=graph_events,
            report=report,
        )
    write_json(results_dir / "pilot14_structure_summary.json", report)

    markdown_lines = [
        "# Pilot14 Structure Summary",
        "",
        f"- Documents: {report['document_count']}",
        f"- Kept chunks: {report['kept_chunk_count']}",
        f"- Rejected chunks: {report['rejected_chunk_count']}",
        f"- Pages: {report['page_count']}",
        f"- Table candidates: {report['table_candidate_count']}",
        f"- Strict tables: {report['strict_table_count']}",
        f"- Table rows: {report['table_row_count']}",
        f"- Form candidates: {report['form_candidate_count']}",
        f"- Gold-ready chunk candidates: {report['gold_ready_chunk_count']}",
        f"- Gold review queue: {report['gold_review_queue_count']}",
        f"- Merged short fragments: {report['merged_short_chunk_count']}",
        f"- OCR-risk chunks: {report['ocr_risk_chunk_count']}",
        f"- Graph nodes: {report['graph_node_count']}",
        f"- Graph links: {report['graph_link_count']}",
        "",
        "## Per Document",
        "",
        "| doc_id | source | input | kept | rejected | table candidates | strict tables | form candidates | OCR-risk | merged short |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for doc_id, item in sorted(source_report.items()):
        markdown_lines.append(
            f"| {doc_id} | {item['source_used']} | {item['input_chunks']} | {item['kept_chunks']} | {item['rejected_chunks']} | {item['table_candidates']} | {item['strict_tables']} | {item['form_candidates']} | {item['ocr_risk_chunks']} | {item['merged_short_chunks']} |"
        )
    (results_dir / "pilot14_structure_summary.md").write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2, default=dict))


if __name__ == "__main__":
    main()
