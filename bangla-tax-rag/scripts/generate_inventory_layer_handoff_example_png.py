from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "docs" / "assets" / "inventory_layer_handoff_example.png"

W, H = 3600, 2250
BG = "#f6f8fc"
INK = "#172033"
MUTED = "#5e6b80"
LINE = "#95a4bd"
PANEL = "#ffffff"
PANEL_ALT = "#eef3fb"
SHADOW = "#d8dfeb"
CODE_BG = "#f7fafc"


def font(size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    if mono:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationMono-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


TITLE = font(72, bold=True)
SUBTITLE = font(29)
LAYER = font(32, bold=True)
BODY = font(22)
SMALL = font(19)
TINY = font(16)
CODE = font(18, mono=True)
CODE_BOLD = font(18, bold=True, mono=True)

COLORS = {
    "catalog": "#1a8c96",
    "understanding": "#6a67d8",
    "retrieval": "#d87a18",
    "decision": "#b05f99",
    "answer": "#707b8e",
    "verify": "#23304d",
}


def text_width(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=fnt)
    return bbox[2] - bbox[0]


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    fnt: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    paragraphs = text.split("\n")
    lines: list[str] = []
    for paragraph in paragraphs:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if text_width(draw, candidate, fnt) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    fnt: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_gap: int = 7,
) -> int:
    x, y = xy
    line_height = (getattr(fnt, "size", 20)) + line_gap
    for line in wrap_text(draw, text, fnt, max_width):
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_height
    return y


def rounded_panel(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    radius: int = 22,
    fill: str = PANEL,
    outline: str = "#cdd7e7",
    top_bar: str | None = None,
) -> None:
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle((x1 + 8, y1 + 10, x2 + 8, y2 + 10), radius=radius, fill=SHADOW)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=fill, outline=outline, width=2)
    if top_bar:
        draw.rounded_rectangle((x1, y1, x2, y1 + 16), radius=radius, fill=top_bar)


def draw_layer_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    label: str,
    title: str,
    subtitle: str,
    accent: str,
    files: str,
) -> None:
    x1, y1, x2, y2 = xy
    rounded_panel(draw, xy, top_bar=accent)
    draw.text((x1 + 26, y1 + 28), label, font=SMALL, fill=MUTED)
    draw.text((x1 + 26, y1 + 66), title, font=LAYER, fill=INK)
    draw_wrapped(draw, (x1 + 26, y1 + 115), subtitle, fnt=BODY, fill=INK, max_width=x2 - x1 - 52)
    tag_h = 38
    tag_y = y2 - tag_h - 18
    draw.rounded_rectangle((x1 + 22, tag_y, x2 - 22, tag_y + tag_h), radius=13, fill="#eef3f8")
    draw.text((x1 + 28, tag_y + 8), files, font=TINY, fill=MUTED)


def draw_payload_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    title: str,
    accent: str,
    lines: list[str],
    note: str | None = None,
) -> None:
    x1, y1, x2, y2 = xy
    rounded_panel(draw, xy, radius=18, fill=CODE_BG, outline="#d6deeb")
    draw.rounded_rectangle((x1 + 18, y1 + 18, x1 + 190, y1 + 52), radius=14, fill=accent)
    draw.text((x1 + 36, y1 + 27), title, font=TINY, fill="#ffffff")
    y = y1 + 72
    line_h = getattr(CODE, "size", 18) + 7
    for line in lines:
        font_to_use = CODE_BOLD if line.startswith("# ") else CODE
        text = line[2:] if line.startswith("# ") else line
        draw.text((x1 + 22, y), text, font=font_to_use, fill=INK)
        y += line_h
    if note:
        draw.line((x1 + 20, y2 - 52, x2 - 20, y2 - 52), fill="#d9e1ec", width=2)
        draw_wrapped(draw, (x1 + 22, y2 - 42), note, fnt=TINY, fill=MUTED, max_width=x2 - x1 - 44, line_gap=4)


def draw_speech(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], *, title: str, text: str, accent: str) -> None:
    x1, y1, x2, y2 = xy
    rounded_panel(draw, xy, radius=24, fill=PANEL_ALT, outline="#c7d4ea", top_bar=accent)
    draw.text((x1 + 24, y1 + 28), title, font=SMALL, fill=MUTED)
    draw_wrapped(draw, (x1 + 24, y1 + 68), text, fnt=BODY, fill=INK, max_width=x2 - x1 - 48, line_gap=8)


def draw_arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    color: str = LINE,
    width: int = 8,
) -> None:
    draw.line((start, end), fill=color, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head_len = 28
    head_angle = math.pi / 7
    points = [
        end,
        (
            int(end[0] - head_len * math.cos(angle - head_angle)),
            int(end[1] - head_len * math.sin(angle - head_angle)),
        ),
        (
            int(end[0] - head_len * math.cos(angle + head_angle)),
            int(end[1] - head_len * math.sin(angle + head_angle)),
        ),
    ]
    draw.polygon(points, fill=color)


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)

    draw.text((82, 58), "Inventory RAG Layer Handoff Example", font=TITLE, fill=INK)
    draw.text(
        (88, 152),
        "One example question traced across the runtime layers, showing what each layer passes to the next.",
        font=SUBTITLE,
        fill=MUTED,
    )

    question_box = (90, 300, 710, 520)
    draw_speech(
        draw,
        question_box,
        title="Runtime Example",
        text='Customer asks: "eid er jonno 5000 er moddhe elegant saree ache?"',
        accent=COLORS["understanding"],
    )

    catalog_box = (1320, 265, 1985, 530)
    draw_layer_box(
        draw,
        catalog_box,
        label="Layer 1",
        title="Catalog + Index",
        subtitle="Validated product facts are stored once, then indexed as searchable text + metadata + vectors.",
        accent=COLORS["catalog"],
        files="catalog.jsonl | storage.py | embedder.py | elasticsearch_store.py",
    )

    layer_y = 660
    box_w = 610
    box_h = 220
    gap = 70
    xs = [90, 770, 1450, 2130, 2810]
    layers = [
        ("Layer 2", "Understanding", "Normalizes Bangla/Banglish/English text and extracts intent, slots, and confidence.", COLORS["understanding"], "fashion_retail.py | llm_intent_classifier.py"),
        ("Layer 3", "Retrieval", "Combines structured filters, vector search, and lexical search to return product candidates.", COLORS["retrieval"], "inventory_service.py | elasticsearch_store.py"),
        ("Layer 4", "Decisions + Evidence", "Ranks candidates, chooses product roles, and defines which facts are allowed.", COLORS["decision"], "reranker.py | evidence_contract.py | planner.py"),
        ("Layer 5A", "Answer Writing", "Turns the approved plan into a human-friendly reply without changing product decisions.", COLORS["answer"], "inventory_service.py | natural_answer.py"),
        ("Layer 5B", "Verification", "Checks the draft against evidence, exclusions, stock, price, and abstention rules.", COLORS["verify"], "verifier.py | answer_critic.py"),
    ]
    boxes: list[tuple[int, int, int, int]] = []
    for i, (label, title, subtitle, accent, files) in enumerate(layers):
        box = (xs[i], layer_y, xs[i] + box_w, layer_y + box_h)
        boxes.append(box)
        draw_layer_box(
            draw,
            box,
            label=label,
            title=title,
            subtitle=subtitle,
            accent=accent,
            files=files,
        )

    # Connect question to understanding.
    draw_arrow(draw, (710, 410), (xs[0] - 22, layer_y + 110), color=COLORS["understanding"], width=7)

    # Catalog to retrieval vertical feed.
    retrieval_box = boxes[1]
    draw_arrow(
        draw,
        ((catalog_box[0] + catalog_box[2]) // 2, catalog_box[3] + 10),
        ((retrieval_box[0] + retrieval_box[2]) // 2, retrieval_box[1] - 18),
        color=COLORS["catalog"],
        width=7,
    )

    # Horizontal arrows.
    for idx in range(len(boxes) - 1):
        draw_arrow(
            draw,
            (boxes[idx][2] + 12, boxes[idx][1] + 110),
            (boxes[idx + 1][0] - 18, boxes[idx + 1][1] + 110),
            color=LINE,
            width=8,
        )

    # Payload boxes.
    payload1 = (110, 970, 720, 1425)
    draw_payload_box(
        draw,
        payload1,
        title="Output to Retrieval",
        accent=COLORS["understanding"],
        lines=[
            "# structured query package",
            '{',
            '  "intent": "fashion_search",',
            '  "language": "banglish",',
            '  "category": "saree",',
            '  "occasion": "eid",',
            '  "budget_max": 5000,',
            '  "style": "elegant",',
            '  "wants_in_stock": true,',
            '  "confidence": 0.88',
            '}',
        ],
        note="This is the cleaned runtime query. Retrieval uses it as filters and recall hints.",
    )

    payload_catalog = (820, 970, 1410, 1425)
    draw_payload_box(
        draw,
        payload_catalog,
        title="Indexed Catalog Record",
        accent=COLORS["catalog"],
        lines=[
            "# vector record",
            '{',
            '  "record_id": "saree-muslin-pastel-eid",',
            '  "text": "Pastel Eid Saree soft muslin...",',
            '  "metadata": {',
            '    "category": "Saree",',
            '    "price": 4800,',
            '    "stock": 4,',
            '    "occasion": "eid"',
            '  },',
            '  "vector": [0.12, -0.04, ...]',
            '}',
        ],
        note="Catalog is indexed ahead of time, then reused by Retrieval at query time.",
    )

    payload2 = (1510, 970, 2120, 1425)
    draw_payload_box(
        draw,
        payload2,
        title="Output to Decisions",
        accent=COLORS["retrieval"],
        lines=[
            "# ranked candidate hits",
            '[',
            '  {"product_id": "saree-muslin-pastel-eid",',
            '   "score": 0.91, "price": 4800, "stock": 4},',
            '  {"product_id": "saree-cotton-elegant-blue",',
            '   "score": 0.84, "price": 4500, "stock": 2},',
            '  {"product_id": "saree-soft-silk-party",',
            '   "score": 0.62, "price": 5200, "stock": 1}',
            ']',
        ],
        note="Retrieval passes candidates only. It does not choose the final recommendation.",
    )

    payload3 = (2200, 970, 2810, 1425)
    draw_payload_box(
        draw,
        payload3,
        title="Output to Answer Writer",
        accent=COLORS["decision"],
        lines=[
            "# answer_plan + evidence_contract",
            '{',
            '  "primary_product_id": "saree-muslin-pastel-eid",',
            '  "alternative_product_ids": ["saree-cotton-elegant-blue"],',
            '  "excluded_product_ids": ["saree-soft-silk-party"],',
            '  "allowed_claims": ["price", "stock", "occasion"],',
            '  "risk_notes": ["Third hit exceeds budget."],',
            '  "next_best_question": "Which color do you prefer?"',
            '}',
        ],
        note="This is the control boundary. The writer may express the plan, but may not change it.",
    )

    payload4 = (2890, 970, 3500, 1425)
    draw_payload_box(
        draw,
        payload4,
        title="Output to Final Response",
        accent=COLORS["verify"],
        lines=[
            "# verified reply package",
            '{',
            '  "passed": true,',
            '  "issues": [],',
            '  "answer": "Ami 2ta option suggest korte pari. ',
            'Pastel Eid Saree BDT 4,800 and stock 4."',
            '}',
        ],
        note="Verification ensures the final text did not invent stock, price, or product facts.",
    )

    # Bottom summary.
    summary_box = (90, 1570, 3500, 2060)
    rounded_panel(draw, summary_box, radius=26, fill=PANEL, outline="#ccd6e7", top_bar=COLORS["verify"])
    draw.text((118, 1606), "End-to-End Runtime Meaning", font=LAYER, fill=INK)
    summary = (
        "Question -> Understanding extracts a structured query package. "
        "Retrieval combines that package with indexed catalog records to find candidates. "
        "Decisions + Evidence turn candidates into an answer_plan and an evidence_contract. "
        "Answer Writing produces customer-friendly text from the approved plan. "
        "Verification checks that the draft stayed grounded before it becomes the final answer."
    )
    draw_wrapped(draw, (120, 1670), summary, fnt=BODY, fill=INK, max_width=3320, line_gap=8)

    pill_y = 1795
    pills = [
        ("Understanding passes normalized slots, not raw text only.", COLORS["understanding"]),
        ("Retrieval passes candidates, not decisions.", COLORS["retrieval"]),
        ("Decisions pass allowed facts, tradeoffs, and exclusions.", COLORS["decision"]),
        ("Verification can force abstain or fallback.", COLORS["verify"]),
    ]
    px = 120
    for text, color in pills:
        width = text_width(draw, text, SMALL) + 46
        draw.rounded_rectangle((px, pill_y, px + width, pill_y + 48), radius=24, fill=color)
        draw.text((px + 22, pill_y + 12), text, font=SMALL, fill="#ffffff")
        px += width + 20

    footer = (
        "Example layer map for engineering presentation. Runtime files: fashion_retail.py, "
        "llm_intent_classifier.py, inventory_service.py, reranker.py, evidence_contract.py, "
        "planner.py, natural_answer.py, verifier.py, answer_critic.py."
    )
    draw.text((90, 2140), footer, font=TINY, fill=MUTED)

    image.save(OUTPUT_PATH)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
