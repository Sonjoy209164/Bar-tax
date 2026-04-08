import re
from pathlib import Path
import json

from app.core.schemas import QuerySignals

BANGLA_DIGIT_MAP = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
SECTION_KEYWORDS = ("ধারা", "উপ-ধারা", "উপধারা", "পরিশিষ্ট", "অনুচ্ছেদ")
QUERY_TYPE_PATTERNS = {
    "rate_lookup": re.compile(r"(হার|rate|slab|threshold|করহার)", re.IGNORECASE),
    "amendment": re.compile(r"(amend|সংশোধন|পরিবর্তন|change)", re.IGNORECASE),
    "example": re.compile(r"(উদাহরণ|example|illustration)", re.IGNORECASE),
    "definition": re.compile(r"(definition|সংজ্ঞা|মানে কী|কি বলা হয়েছে|কী বলা হয়েছে|what is|what does)", re.IGNORECASE),
    "procedure": re.compile(r"(প্রক্রিয়া|পদ্ধতি|how to|process|steps)", re.IGNORECASE),
    "calculation": re.compile(r"(calculate|calculation|গণনা|compute)", re.IGNORECASE),
    "comparison": re.compile(r"(compare|comparison|তুলনা|versus|পার্থক্য)", re.IGNORECASE),
}
DOCUMENT_HEADER_PATTERN = re.compile(r"আয়কর\s+পররপত্র\s+20\d{2}\s*-\s*20\d{2}\s*\|\s*\d+", re.IGNORECASE)
TABLE_HEADER_LINES = {
    "ক্রমিক নং",
    "মির োনোি",
    "মিরোনাম",
    "এইচ এস ককোড",
    "এইচ এস কোড",
    "বণডনা",
    "বর্ণনা",
    "(1)",
    "(2)",
    "(3)",
    "(4)",
}


def is_year_like_marker(marker: str) -> bool:
    normalized_marker = normalize_bangla_digits(marker).strip()
    if re.fullmatch(r"20\d{2}", normalized_marker):
        return True
    if re.fullmatch(r"20\d{2}\s*[-–]\s*20\d{2}", normalized_marker):
        return True
    return False


def clean_section_marker(marker: str) -> str:
    normalized_marker = normalize_text(marker)
    cleaned_marker = re.sub(
        r"^(?:ধারা|উপ-ধারা|উপধারা|পরিশিষ্ট|অনুচ্ছেদ|section|article)\s*",
        "",
        normalized_marker,
        flags=re.IGNORECASE,
    )
    return cleaned_marker.strip(" .):;-")


def ensure_directory(path_value: str) -> Path:
    path = Path(path_value)
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_bangla_digits(text: str) -> str:
    return text.translate(BANGLA_DIGIT_MAP)


def normalize_whitespace(text: str) -> str:
    collapsed_text = re.sub(r"[ \t]+", " ", text)
    collapsed_text = re.sub(r"\n{3,}", "\n\n", collapsed_text)
    return collapsed_text.strip()


def normalize_text(text: str) -> str:
    return normalize_whitespace(normalize_bangla_digits(text))


def extract_tax_years(text: str) -> list[str]:
    normalized_text = normalize_text(text)
    matches = re.findall(r"\b(20\d{2}\s*[-–]\s*20\d{2})\b", normalized_text)
    return list(dict.fromkeys(match.replace(" ", "") for match in matches))


def extract_section_ids(text: str) -> list[str]:
    normalized_text = normalize_text(text)
    patterns = [
        r"\b\d+(?:\.\d+)+\b",
        r"\b\d+\b",
        r"(?:ধারা|উপ-ধারা|উপধারা|পরিশিষ্ট|অনুচ্ছেদ)\s*\d+(?:\.\d+)*",
        r"(?:ধারা|উপ-ধারা|উপধারা|পরিশিষ্ট|অনুচ্ছেদ)\s*[A-Za-z0-9.-]+",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, normalized_text, flags=re.IGNORECASE))
    cleaned_matches = [match.strip(" .)") for match in matches if match.strip()]
    return list(dict.fromkeys(cleaned_matches))


def extract_query_section_references(text: str) -> list[str]:
    normalized_text = normalize_text(text)
    matches: list[str] = []
    contextual_patterns = [
        r"(?:ধারা|উপ-ধারা|উপধারা|অনুচ্ছেদ|section|article)\s*([0-9]+(?:\.[0-9]+)*)",
    ]
    for pattern in contextual_patterns:
        matches.extend(re.findall(pattern, normalized_text, flags=re.IGNORECASE))
    matches.extend(re.findall(r"\b([0-9]+\.[0-9]+(?:\.[0-9]+)*)\b", normalized_text))
    cleaned_matches = [clean_section_marker(match) for match in matches if clean_section_marker(match)]
    return [match for match in dict.fromkeys(cleaned_matches) if not is_year_like_marker(match)]


def select_primary_section_markers(
    text: str,
    *,
    heading_path: list[str] | None = None,
    page_section_markers: list[str] | None = None,
) -> tuple[str | None, str | None]:
    text_markers: list[str] = []
    fallback_markers: list[str] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:8]:
        text_markers.extend(extract_query_section_references(line))
        heading_marker = detect_heading_marker(line)
        if heading_marker:
            text_markers.append(clean_section_marker(heading_marker))
    for heading in reversed(heading_path or []):
        fallback_markers.extend(extract_query_section_references(heading))
        heading_marker = detect_heading_marker(heading)
        if heading_marker:
            fallback_markers.append(clean_section_marker(heading_marker))
    for marker in page_section_markers or []:
        cleaned_marker = clean_section_marker(marker)
        if cleaned_marker:
            fallback_markers.append(cleaned_marker)
    candidate_markers = text_markers if text_markers else fallback_markers
    filtered_markers: list[str] = []
    for marker in candidate_markers:
        if not marker or is_year_like_marker(marker):
            continue
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", marker):
            continue
        if marker not in filtered_markers:
            filtered_markers.append(marker)
    dotted_markers = [marker for marker in filtered_markers if "." in marker]
    dotted_markers.sort(key=lambda marker: (marker.count("."), len(marker)), reverse=True)
    subsection_id = dotted_markers[0] if dotted_markers else None
    if subsection_id:
        return subsection_id.split(".", maxsplit=1)[0], subsection_id
    section_id = next((marker for marker in filtered_markers if marker.isdigit()), None)
    return section_id, None


def extract_sro_ids(text: str) -> list[str]:
    normalized_text = normalize_text(text)
    patterns = [
        r"(?<![A-Za-z])(?:এস\.?\s*আর\.?\s*ও\.?|S\.?\s*R\.?\s*O\.?)(?![A-Za-z])\s*(?:নং|No\.?|NO\.?)?\s*[-:()]?\s*[A-Za-z0-9/-]+",
        r"(?<![A-Za-z])(?:এস\.?\s*আর\.?\s*ও\.?|S\.?\s*R\.?\s*O\.?)(?![A-Za-z])\s*[-:()]?\s*[A-Za-z0-9/-]+",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, normalized_text, flags=re.IGNORECASE))
    unique_matches: list[str] = []
    for match in dict.fromkeys(match.strip() for match in matches):
        if any(match != other and match in other for other in matches):
            continue
        unique_matches.append(match)
    return unique_matches


def extract_cross_references(text: str) -> list[str]:
    normalized_text = normalize_text(text)
    patterns = [
        r"(?:ধারা|উপ-ধারা|উপধারা|পরিশিষ্ট|তফসিল)\s*\d+(?:\.\d+)*",
        r"\b\d+(?:\.\d+)+\b",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, normalized_text, flags=re.IGNORECASE))
    return list(dict.fromkeys(match.strip() for match in matches))


def detect_heading_marker(text: str) -> str | None:
    normalized_text = normalize_text(text)
    if not normalized_text:
        return None
    numeric_match = re.match(r"^(\d+(?:\.\d+)*)[\).\s:-]+", normalized_text)
    if numeric_match:
        return numeric_match.group(1)
    for keyword in SECTION_KEYWORDS:
        keyword_match = re.match(
            rf"^({re.escape(keyword)}\s*[A-Za-z0-9.-]+)",
            normalized_text,
            flags=re.IGNORECASE,
        )
        if keyword_match:
            return keyword_match.group(1)
    return None


def extract_appendix_ids(text: str) -> list[str]:
    normalized_text = normalize_text(text)
    patterns = [
        r"(?:পরিশিষ্ট|appendix|annex)\s*[A-Za-z0-9.-]+",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, normalized_text, flags=re.IGNORECASE))
    return list(dict.fromkeys(match.strip() for match in matches))


def tokenize_for_bm25(text: str) -> list[str]:
    normalized_text = normalize_text(text).lower()
    return re.findall(r"[\w\u0980-\u09ff./-]+", normalized_text)


def detect_query_type(text: str) -> str:
    for query_type, pattern in QUERY_TYPE_PATTERNS.items():
        if pattern.search(text):
            return query_type
    return "general"


def preprocess_query(query: str) -> QuerySignals:
    normalized_query = normalize_text(query)
    tax_years = extract_tax_years(query)
    section_ids = extract_query_section_references(query)
    appendix_ids = extract_appendix_ids(query)
    sro_ids = extract_sro_ids(query)
    section_id: str | None = None
    subsection_id: str | None = None
    for candidate in section_ids:
        if "." in candidate and candidate[0].isdigit():
            subsection_id = candidate
            break
    if subsection_id:
        section_id = subsection_id.split(".", maxsplit=1)[0]
    else:
        for candidate in section_ids:
            if candidate and candidate[0].isdigit():
                section_id = candidate
                break
    return QuerySignals(
        original_query=query,
        normalized_query=normalized_query,
        tax_year=tax_years[0] if tax_years else None,
        section_reference=section_ids[0] if section_ids else None,
        section_id=section_id,
        subsection_id=subsection_id,
        appendix_reference=appendix_ids[0] if appendix_ids else None,
        appendix_id=appendix_ids[0] if appendix_ids else None,
        sro_reference=sro_ids[0] if sro_ids else None,
        sro_id=sro_ids[0] if sro_ids else None,
        query_type=detect_query_type(normalized_query),
        query_intent=detect_query_type(normalized_query),
    )


def split_sentences(text: str) -> list[str]:
    stripped_text = text.strip()
    if not stripped_text:
        return []
    sentence_candidates = re.split(r"(?<=[.!?।])\s+|\n+", stripped_text)
    return [candidate.strip() for candidate in sentence_candidates if candidate.strip()]


def truncate_text(text: str, max_length: int = 240) -> str:
    normalized = normalize_whitespace(text)
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


def detect_text_language(text: str) -> str:
    return "bangla" if re.search(r"[\u0980-\u09FF]", text) else "english"


def clamp_score(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _looks_like_code_or_serial_line(text: str) -> bool:
    normalized_line = normalize_text(text)
    if not normalized_line:
        return False
    return bool(
        re.fullmatch(r"\d+\.", normalized_line)
        or re.fullmatch(r"\d+(?:\.\d+){1,3}", normalized_line)
        or re.fullmatch(r"\(\d+\)", normalized_line)
    )


def _clean_generation_lines(text: str) -> list[str]:
    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = normalize_whitespace(normalize_bangla_digits(raw_line))
        if not line:
            continue
        if DOCUMENT_HEADER_PATTERN.search(line):
            continue
        if line in TABLE_HEADER_LINES:
            continue
        cleaned_lines.append(line)
    return cleaned_lines


def clean_bangla_ocr_text(text: str) -> str:
    cleaned_lines = _clean_generation_lines(text)
    if not cleaned_lines:
        return ""

    merged_lines: list[str] = []
    for line in cleaned_lines:
        if not merged_lines:
            merged_lines.append(line)
            continue
        previous_line = merged_lines[-1]
        if _looks_like_code_or_serial_line(line):
            merged_lines.append(line)
            continue
        if _looks_like_code_or_serial_line(previous_line):
            merged_lines.append(line)
            continue
        if previous_line.endswith(("।", ".", "?", "!", ":", ";", "%")):
            merged_lines.append(line)
            continue
        if re.match(r"^[A-Za-z0-9]", line):
            merged_lines.append(line)
            continue
        merged_lines[-1] = f"{previous_line} {line}".strip()

    cleaned_text = "\n".join(merged_lines)
    cleaned_text = re.sub(r"\s+([,.;:!?।])", r"\1", cleaned_text)
    cleaned_text = re.sub(r"([A-Za-z])\s*\n\s*([A-Za-z])", r"\1 \2", cleaned_text)
    cleaned_text = re.sub(r"(?<=\d)\s+(?=%)", "", cleaned_text)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)
    return cleaned_text.strip()


def ensure_file_exists(path_value: str) -> Path:
    path = Path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path


def write_jsonl(records: list[dict], output_path: str) -> Path:
    path = Path(output_path)
    ensure_directory(str(path.parent))
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path
