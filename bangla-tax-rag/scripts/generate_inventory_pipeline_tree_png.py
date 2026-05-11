from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "docs" / "assets" / "inventory_pipeline_tree.png"

W, H = 3000, 1900
BG = "#f7f9fc"
INK = "#172033"
MUTED = "#5d687b"
LINE = "#a7b5ca"
WHITE = "#ffffff"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


TITLE = font(68, bold=True)
SUBTITLE = font(28)
ROOT_FONT = font(36, bold=True)
NODE_TITLE = font(27, bold=True)
BODY = font(19)
SMALL = font(16)


@dataclass(frozen=True)
class Branch:
    title: str
    color: str
    children: tuple[tuple[str, str], ...]


BRANCHES = (
    Branch(
        "1. Data + Storage",
        "#1d8aa5",
        (
            ("Catalog DB", "JSONL product records with SKU, stock, price, variants"),
            ("POS Sync", "CSV/webhook import updates catalog and audit logs"),
            ("Orders + Signals", "Orders, feedback, and business signals for future decisions"),
        ),
    ),
    Branch(
        "2. API + UI",
        "#2f8f5b",
        (
            ("Chat UI", "frontend/chat.html renders conversation and catalog panel"),
            ("FastAPI", "routes_inventory.py exposes chat, catalog, sync, image, order APIs"),
            ("Security", "X-API-Key protects inventory endpoints"),
        ),
    ),
    Branch(
        "3. Understanding",
        "#6a75c9",
        (
            ("Language Normalizer", "Bangla/Banglish text cleanup and alias expansion"),
            ("Intent Classifier", "Detects search, variant, size, compare, style, policy, order"),
            ("Slot Extractor", "Finds category, color, size, budget, fabric, occasion, gender"),
        ),
    ),
    Branch(
        "4. Retrieval",
        "#d57b1f",
        (
            ("Structured Search", "Exact catalog filters for category, size, stock, design id"),
            ("Vector Search", "Embeddings over product search text via local/Elasticsearch/Pinecone/Milvus"),
            ("Lexical Search", "SKU, product id, brand, name, category, and fuzzy aliases"),
        ),
    ),
    Branch(
        "5. Decisions",
        "#b0639b",
        (
            ("Ranking", "Reranker and scorer prioritize relevance, stock, price fit"),
            ("Evidence Contract", "Only supported catalog facts can reach the answer"),
            ("Abstention Gate", "Ask clarification or refuse when evidence is weak"),
        ),
    ),
    Branch(
        "6. Answer + Loop",
        "#697386",
        (
            ("Answer Writer", "Deterministic templates or optional grounded LLM prompt"),
            ("Verifier", "Checks claims against retrieved product evidence"),
            ("Feedback Loop", "Trace, tests, feedback, and audit reports tune the system"),
        ),
    ),
)


def text_width(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=fnt)
    return bbox[2] - bbox[0]


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if text_width(draw, candidate, fnt) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def centered_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, fnt: ImageFont.ImageFont, fill: str) -> None:
    x1, y1, x2, y2 = box
    lines = wrap(draw, text, fnt, x2 - x1 - 36)
    line_h = fnt.size + 6
    total_h = len(lines) * line_h
    y = y1 + ((y2 - y1 - total_h) // 2)
    for line in lines:
        x = x1 + ((x2 - x1 - text_width(draw, line, fnt)) // 2)
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_h


def draw_node(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    title: str,
    body: str | None = None,
    color: str,
    title_font: ImageFont.ImageFont = NODE_TITLE,
    body_font: ImageFont.ImageFont = BODY,
    fill: str = WHITE,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle((x1 + 6, y1 + 8, x2 + 6, y2 + 8), radius=20, fill="#d7dee9")
    draw.rounded_rectangle((x1, y1, x2, y2), radius=20, fill=fill, outline="#c6d2e2", width=2)
    draw.rounded_rectangle((x1, y1, x2, y1 + 13), radius=10, fill=color)
    if body is None:
        centered_text(draw, (x1 + 8, y1 + 12, x2 - 8, y2 - 8), title, title_font, INK)
        return
    draw.text((x1 + 24, y1 + 30), title, font=title_font, fill=INK)
    y = y1 + 72
    for line in wrap(draw, body, body_font, x2 - x1 - 48):
        draw.text((x1 + 24, y), line, font=body_font, fill=MUTED)
        y += body_font.size + 8


def connector(draw: ImageDraw.ImageDraw, a: tuple[int, int], b: tuple[int, int], *, color: str = LINE, width: int = 4) -> None:
    ax, ay = a
    bx, by = b
    mid_y = ay + (by - ay) // 2
    draw.line((ax, ay, ax, mid_y, bx, mid_y, bx, by), fill=color, width=width, joint="curve")
    angle = math.pi / 2
    head = 16
    points = [
        (bx, by),
        (int(bx - head * math.cos(angle - math.pi / 7)), int(by - head * math.sin(angle - math.pi / 7))),
        (int(bx - head * math.cos(angle + math.pi / 7)), int(by - head * math.sin(angle + math.pi / 7))),
    ]
    draw.polygon(points, fill=color)


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)

    draw.text((80, 52), "Inventory Chatbot Pipeline: Tree View", font=TITLE, fill=INK)
    draw.text(
        (83, 135),
        "A responsibility tree for explaining what each layer owns, what technology it uses, and how decisions flow.",
        font=SUBTITLE,
        fill=MUTED,
    )

    root_box = (1025, 215, 1975, 360)
    draw_node(
        draw,
        root_box,
        title="Catalog-Grounded Boutique Inventory Assistant",
        color="#172033",
        title_font=ROOT_FONT,
        fill="#ffffff",
    )

    branch_y = 520
    child_y = 780
    branch_w = 430
    branch_h = 125
    child_w = 390
    child_h = 128
    left = 80
    gap = 61

    root_anchor = ((root_box[0] + root_box[2]) // 2, root_box[3])
    hub = (root_anchor[0], 445)
    draw.line((root_anchor, hub), fill=LINE, width=5)
    draw.line((left + branch_w // 2, hub[1], W - left - branch_w // 2, hub[1]), fill=LINE, width=5)

    for index, branch in enumerate(BRANCHES):
        x = left + index * (branch_w + gap)
        b_box = (x, branch_y, x + branch_w, branch_y + branch_h)
        branch_anchor = (x + branch_w // 2, branch_y)
        draw.line((branch_anchor[0], hub[1], branch_anchor[0], branch_anchor[1]), fill=LINE, width=5)
        draw_node(draw, b_box, title=branch.title, color=branch.color, title_font=NODE_TITLE, fill="#ffffff")

        parent_bottom = (x + branch_w // 2, branch_y + branch_h)
        child_gap = 22
        total_child_h = len(branch.children) * child_h + (len(branch.children) - 1) * child_gap
        start_y = child_y
        spine_x = x + branch_w // 2
        draw.line((spine_x, parent_bottom[1], spine_x, start_y + total_child_h - child_h // 2), fill="#d5dee9", width=4)

        for child_index, (child_title, child_body) in enumerate(branch.children):
            cy = start_y + child_index * (child_h + child_gap)
            cx = x + 20
            c_box = (cx, cy, cx + child_w, cy + child_h)
            draw.line((spine_x, cy + child_h // 2, cx, cy + child_h // 2), fill="#d5dee9", width=4)
            draw_node(draw, c_box, title=child_title, body=child_body, color=branch.color)

    # Decision flow strip.
    flow_y = 1315
    draw.rounded_rectangle((80, flow_y, W - 80, flow_y + 205), radius=24, fill="#eef3f8", outline="#cad6e6", width=2)
    draw.text((110, flow_y + 28), "Runtime Decision Flow", font=NODE_TITLE, fill=INK)
    flow_nodes = [
        ("Question", "#2f8f5b"),
        ("Normalize + Slots", "#6a75c9"),
        ("Route", "#6a75c9"),
        ("Retrieve", "#d57b1f"),
        ("Rank + Evidence", "#b0639b"),
        ("Write + Verify", "#697386"),
        ("Answer", "#172033"),
    ]
    fx = 110
    fy = flow_y + 95
    fw = 340
    for i, (label, color) in enumerate(flow_nodes):
        box = (fx, fy, fx + fw, fy + 66)
        draw.rounded_rectangle(box, radius=20, fill=WHITE, outline="#c8d3e1", width=2)
        draw.rounded_rectangle((box[0], box[1], box[2], box[1] + 9), radius=8, fill=color)
        centered_text(draw, box, label, NODE_TITLE, INK)
        if i < len(flow_nodes) - 1:
            x1 = fx + fw
            x2 = fx + fw + 58
            ymid = fy + 33
            draw.line((x1 + 8, ymid, x2 - 10, ymid), fill=LINE, width=5)
            draw.polygon([(x2, ymid), (x2 - 18, ymid - 12), (x2 - 18, ymid + 12)], fill=LINE)
        fx += fw + 68

    notes_y = 1585
    notes = [
        ("Best for exact facts", "Structured path answers stock, price, size, color, design, and SKU questions."),
        ("Best for fuzzy wording", "RAG path helps when customers ask vague Bangla/Banglish or semantic questions."),
        ("Best safety control", "Evidence contract and verifier stop unsupported claims from reaching the customer."),
    ]
    note_w = 900
    for i, (title, body) in enumerate(notes):
        x = 80 + i * (note_w + 70)
        draw_node(draw, (x, notes_y, x + note_w, notes_y + 150), title=title, body=body, color="#172033")

    draw.text(
        (80, H - 48),
        "Technology stack: FastAPI, Pydantic, JSONL/SQLite, local or Elasticsearch vector store, transformers/multilingual/OpenAI embeddings, optional Ollama/OpenAI-compatible LLM, custom retail ranking and verification.",
        font=SMALL,
        fill=MUTED,
    )

    image.save(OUTPUT_PATH, format="PNG", optimize=True)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
