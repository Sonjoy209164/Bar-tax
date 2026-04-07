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
    "definition": re.compile(r"(definition|সংজ্ঞা|মানে কী|what is)", re.IGNORECASE),
    "procedure": re.compile(r"(প্রক্রিয়া|পদ্ধতি|how to|process|steps)", re.IGNORECASE),
    "calculation": re.compile(r"(calculate|calculation|গণনা|compute)", re.IGNORECASE),
    "comparison": re.compile(r"(compare|comparison|তুলনা|versus|পার্থক্য)", re.IGNORECASE),
}


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


def extract_sro_ids(text: str) -> list[str]:
    normalized_text = normalize_text(text)
    patterns = [
        r"(?:এস\.?\s*আর\.?\s*ও\.?|S\.?\s*R\.?\s*O\.?)\s*(?:নং|No\.?|NO\.?)?\s*[-:()]?\s*[A-Za-z0-9/-]+",
        r"(?:এস\.?\s*আর\.?\s*ও\.?|S\.?\s*R\.?\s*O\.?)\s*[-:()]?\s*[A-Za-z0-9/-]+",
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
    section_ids = extract_section_ids(query)
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
