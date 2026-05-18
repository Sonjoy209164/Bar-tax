from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "docs" / "assets" / "full_current_inventory_pipeline.png"


W, H = 3000, 2100
BG = "#f7f9fc"
INK = "#172033"
MUTED = "#596579"
LINE = "#8ea0b8"
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


FONT_TITLE = font(70, bold=True)
FONT_SUBTITLE = font(30)
FONT_LANE = font(28, bold=True)
FONT_BOX_TITLE = font(30, bold=True)
FONT_BODY = font(19)
FONT_SMALL = font(17)
FONT_TINY = font(15)


def text_width(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=fnt)
    return bbox[2] - bbox[0]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if text_width(draw, candidate, fnt) <= max_width:
            current = candidate
            continue
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
    line_height = fnt.size + line_gap if hasattr(fnt, "size") else 24
    for line in wrap_text(draw, text, fnt, max_width):
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_height
    return y


def draw_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    title: str,
    bullets: list[str],
    accent: str,
    code: str | None = None,
) -> None:
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle((x1 + 6, y1 + 8, x2 + 6, y2 + 8), radius=20, fill="#d7dde8")
    draw.rounded_rectangle((x1, y1, x2, y2), radius=20, fill=WHITE, outline="#c9d3e1", width=2)
    draw.rounded_rectangle((x1, y1, x2, y1 + 12), radius=10, fill=accent)
    draw.text((x1 + 24, y1 + 26), title, font=FONT_BOX_TITLE, fill=INK)
    y = y1 + 68
    max_width = x2 - x1 - 54
    for bullet in bullets:
        draw.ellipse((x1 + 26, y + 8, x1 + 34, y + 16), fill=accent)
        y = draw_wrapped(draw, (x1 + 46, y), bullet, fnt=FONT_BODY, fill=INK, max_width=max_width, line_gap=7)
        y += 8
    if code:
        tag_h = 34
        tag_y = y2 - tag_h - 18
        draw.rounded_rectangle((x1 + 22, tag_y, x2 - 22, tag_y + tag_h), radius=12, fill="#eef3f8")
        draw.text((x1 + 36, tag_y + 8), code, font=FONT_TINY, fill=MUTED)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], *, color: str = LINE, width: int = 5) -> None:
    draw.line((start, end), fill=color, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head_len = 22
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


def pill(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, *, fill: str, outline: str | None = None) -> int:
    x, y = xy
    pad_x = 20
    pad_y = 9
    tw = text_width(draw, text, FONT_SMALL)
    w = tw + pad_x * 2
    h = FONT_SMALL.size + pad_y * 2
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=fill, outline=outline or fill, width=2)
    draw.text((x + pad_x, y + pad_y - 1), text, font=FONT_SMALL, fill=INK)
    return w


def draw_lane_label(draw: ImageDraw.ImageDraw, y: int, text: str, color: str) -> None:
    label_w = max(520, text_width(draw, text, FONT_LANE) + 44)
    draw.rounded_rectangle((70, y - 14, 70 + label_w, y + 32), radius=18, fill=color)
    draw.text((92, y - 6), text, font=FONT_LANE, fill=WHITE)
    draw.line((90 + label_w, y + 9, W - 70, y + 9), fill="#dce4ef", width=3)


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)

    draw.text((75, 48), "Full Current Inventory RAG Pipeline", font=FONT_TITLE, fill=INK)
    draw.text(
        (80, 136),
        "Boutique retail chatbot: catalog sync, multilingual intent, structured retrieval, vector search, answer verification, and UI delivery.",
        font=FONT_SUBTITLE,
        fill=MUTED,
    )

    x0 = 85
    gap = 35
    box_w = 550
    row_h = 285
    xs = [x0 + i * (box_w + gap) for i in range(5)]

    colors = {
        "data": "#1d8aa5",
        "api": "#2f8f5b",
        "retrieve": "#d57b1f",
        "answer": "#6266bd",
        "ops": "#697386",
    }

    draw_lane_label(draw, 215, "Layer 1: Catalog + Index", colors["data"])
    y = 255
    row1 = [
        (
            "Source Stores",
            [
                "JSONL inventory stores product id, SKU, category, price, stock, tags, and variants.",
                "POS CSV and webhooks can update stock and attributes.",
                "Orders and business signals sit beside catalog data.",
            ],
            "data/inventory/catalog.jsonl",
        ),
        (
            "Schema + Enrichment",
            [
                "Pydantic validates every item before search.",
                "Catalog audit checks missing fields, inactive items, price, and stock.",
                "Retail enrichment expands category attributes and aliases.",
            ],
            "schemas.py + catalog_audit.py",
        ),
        (
            "Search Document Build",
            [
                "Each item becomes text plus exact metadata.",
                "Metadata keeps category, brand, color, size, design id, price, and stock.",
                "Namespace separates inventory from other RAG data.",
            ],
            "inventory_service.py",
        ),
        (
            "Embedding + Vector Store",
            [
                "Embeddings use multilingual, transformers, OpenAI-compatible, or deterministic mode.",
                "Vector store can be local JSONL, Elasticsearch, Pinecone, or Milvus.",
                "Elasticsearch adds kNN, lexical search, and filters.",
            ],
            "embedder.py + vector_store_base.py",
        ),
        (
            "Sync + Rebuild",
            [
                "Sync endpoints validate catalog and rebuild vectors.",
                "Deterministic ids make updates replace old vectors.",
                "Audit files record imports, rebuilds, and issues.",
            ],
            "pos_sync.py + /inventory/sync/*",
        ),
    ]
    for i, (title, bullets, code) in enumerate(row1):
        draw_box(draw, (xs[i], y, xs[i] + box_w, y + row_h), title=title, bullets=bullets, accent=colors["data"], code=code)
        if i < len(row1) - 1:
            arrow(draw, (xs[i] + box_w + 4, y + row_h // 2), (xs[i + 1] - 12, y + row_h // 2))

    draw_lane_label(draw, 590, "Layer 2: Customer Runtime", colors["api"])
    y = 630
    row2 = [
        (
            "Chat UI",
            [
                "Customer chats from the frontend page.",
                "A hideable side panel can show live catalog items.",
                "API key header protects inventory and order APIs.",
            ],
            "frontend/chat.html",
        ),
        (
            "FastAPI Gateway",
            [
                "Routes expose chat, catalog, order, image, policy, and sync APIs.",
                "Swagger UI is available at /docs.",
                "Static chat UI is mounted under /frontend.",
            ],
            "main.py + routes_inventory.py",
        ),
        (
            "Inventory Service",
            [
                "Loads catalog, embedder, vector store, reranker, memory, and answer modules.",
                "Creates trace id, confidence, hits, product ids, and abstention reason.",
                "Keeps recent turns for follow-up context.",
            ],
            "services/inventory_service.py",
        ),
        (
            "Language + Slots",
            [
                "Bangla and Banglish text is normalized.",
                "Slot extraction finds category, color, size, budget, occasion, gender, and design id.",
                "Regex and fuzzy matching are fallback logic.",
            ],
            "fashion_retail.py + llm_slot_extractor.py",
        ),
        (
            "Route Decision",
            [
                "Routes small talk, search, same-design color, size, styling, compare, policy, order, and image queries.",
                "Ambiguous requests ask clarification.",
                "Out-of-domain requests abstain.",
            ],
            "intent_classifier + policy.py",
        ),
    ]
    for i, (title, bullets, code) in enumerate(row2):
        draw_box(draw, (xs[i], y, xs[i] + box_w, y + row_h), title=title, bullets=bullets, accent=colors["api"], code=code)
        if i < len(row2) - 1:
            arrow(draw, (xs[i] + box_w + 4, y + row_h // 2), (xs[i + 1] - 12, y + row_h // 2))

    draw_lane_label(draw, 965, "Layer 3: Retrieval + Decisioning", colors["retrieve"])
    y = 1005
    row3 = [
        (
            "Structured Retail Search",
            [
                "Best path for exact catalog facts: category, color, size, design, price, stock, and gender.",
                "Handles same-design color and size availability.",
                "In-stock exact matches rank first.",
            ],
            "FashionRetailAssistant",
        ),
        (
            "Vector Retrieval",
            [
                "If structured search is not enough, the query is embedded and searched against vectors.",
                "Local store is simple; Elasticsearch adds scalable kNN.",
                "Filters support eq, in, gte, and lte.",
            ],
            "LocalVectorStore / ElasticsearchVectorStore",
        ),
        (
            "Lexical + Hybrid Signals",
            [
                "Product ids, SKUs, names, brands, and categories are matched lexically.",
                "Banglish aliases and fuzzy correction improve coverage.",
                "Hybrid search catches semantic intent and exact facts.",
            ],
            "bm25_index.py + elasticsearch_store.py",
        ),
        (
            "Ranking + Business Fit",
            [
                "Reranker and scorer reorder by relevance, stock, price fit, and selling logic.",
                "Cross-sell can pair sarees with bags, jewelry, shoes, or cosmetics.",
                "Restock logic can use business signals.",
            ],
            "reranker.py + decisioning.py",
        ),
        (
            "Evidence Contract",
            [
                "Only selected catalog facts may enter the answer.",
                "Contract separates supported claims, missing facts, ids, and notes.",
                "This is the anti-hallucination layer.",
            ],
            "evidence_contract.py",
        ),
    ]
    for i, (title, bullets, code) in enumerate(row3):
        draw_box(draw, (xs[i], y, xs[i] + box_w, y + row_h), title=title, bullets=bullets, accent=colors["retrieve"], code=code)
        if i < len(row3) - 1:
            arrow(draw, (xs[i] + box_w + 4, y + row_h // 2), (xs[i + 1] - 12, y + row_h // 2))

    draw_lane_label(draw, 1340, "Layer 4: Answer + Safety + Output", colors["answer"])
    y = 1380
    row4 = [
        (
            "Answer Planning",
            [
                "Planner chooses direct answer, list, comparison, follow-up, or abstention.",
                "Question-family policy defines required evidence.",
                "Preference extraction preserves customer constraints.",
            ],
            "answer_planner.py + preferences.py",
        ),
        (
            "Prompted LLM Path",
            [
                "Optional Ollama/OpenAI-compatible generation rewrites supported facts naturally.",
                "Prompt must preserve prices, stock, SKU, and limitations.",
                "Low temperature keeps support replies controlled.",
            ],
            "natural_answer.py + generator.py",
        ),
        (
            "Deterministic Path",
            [
                "If LLM is off or confidence is low, templates answer from structured facts.",
                "Safer for exact stock, price, size, and same-design questions.",
                "Bangla/Banglish localization adapts wording.",
            ],
            "fashion_retail.py",
        ),
        (
            "Verification",
            [
                "Verifier checks answer claims against catalog evidence.",
                "Unsupported answers abstain or ask clarification.",
                "Response includes trace id, confidence, product ids, and hits.",
            ],
            "verification.py + schemas.py",
        ),
        (
            "Customer Response",
            [
                "UI renders answer, helpful buttons, suggestions, metadata, and catalog view.",
                "Order and feedback APIs capture next actions.",
                "Traces and eval docs support the test-fix loop.",
            ],
            "chat.html + routes_feedback.py",
        ),
    ]
    for i, (title, bullets, code) in enumerate(row4):
        draw_box(draw, (xs[i], y, xs[i] + box_w, y + row_h), title=title, bullets=bullets, accent=colors["answer"], code=code)
        if i < len(row4) - 1:
            arrow(draw, (xs[i] + box_w + 4, y + row_h // 2), (xs[i + 1] - 12, y + row_h // 2))

    # Cross-lane arrows.
    arrow(draw, (xs[3] + box_w // 2, 540), (xs[3] + box_w // 2, 630 - 18), color="#72a8b8", width=4)
    arrow(draw, (xs[4] + box_w // 2, 915), (xs[4] + box_w // 2, 1005 - 18), color="#9aa86f", width=4)
    arrow(draw, (xs[4] + box_w // 2, 1290), (xs[4] + box_w // 2, 1380 - 18), color="#b88c67", width=4)
    draw.text((92, 1698), "Feedback, test questions, and sync audit findings loop back into catalog quality and prompt tuning.", font=FONT_SMALL, fill=MUTED)

    # Prompt and tuning strip.
    strip_y = 1770
    draw.rounded_rectangle((75, strip_y, W - 75, strip_y + 95), radius=22, fill="#eef3f8", outline="#cbd6e5", width=2)
    draw.text((105, strip_y + 18), "Main tuning controls:", font=FONT_LANE, fill=INK)
    x = 380
    for label, fill in [
        ("Catalog schema quality", "#d5f0f5"),
        ("Bangla/Banglish aliases", "#dff3e8"),
        ("Slot extraction prompt", "#fce7cf"),
        ("Evidence-only answer prompt", "#e3e4fb"),
        ("Reranking weights", "#f1edf9"),
        ("Abstention threshold", "#f8e5e5"),
        ("Eval question set", "#edf0f5"),
    ]:
        used = pill(draw, (x, strip_y + 24), label, fill=fill, outline="#c8d2df")
        x += used + 18

    draw.text(
        (78, H - 45),
        "Current stack: FastAPI, Pydantic, JSONL/SQLite mirror, local or Elasticsearch vector store, transformers/multilingual/OpenAI embeddings, optional Ollama/OpenAI-compatible LLM, custom retail decision logic.",
        font=FONT_SMALL,
        fill=MUTED,
    )

    image.save(OUTPUT_PATH, format="PNG", optimize=True)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
