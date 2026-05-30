from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "docs" / "assets" / "memory_system_flow.png"

W, H = 3200, 2300
BG = "#f6f8fb"
INK = "#172033"
MUTED = "#607086"
LINE = "#8797ad"
WHITE = "#ffffff"


def font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
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


FONT_TITLE = font(70, bold=True)
FONT_SUBTITLE = font(30)
FONT_SECTION = font(28, bold=True)
FONT_BOX_TITLE = font(29, bold=True)
FONT_BODY = font(20)
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
    line_height = getattr(fnt, "size", 20) + line_gap
    for line in wrap_text(draw, text, fnt, max_width):
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_height
    return y


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    color: str = LINE,
    width: int = 5,
) -> None:
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


def box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    title: str,
    bullets: list[str],
    accent: str,
    code: str | None = None,
    fill: str = WHITE,
) -> None:
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle((x1 + 7, y1 + 9, x2 + 7, y2 + 9), radius=22, fill="#d8deea")
    draw.rounded_rectangle((x1, y1, x2, y2), radius=22, fill=fill, outline="#c9d3e3", width=2)
    draw.rounded_rectangle((x1, y1, x2, y1 + 14), radius=10, fill=accent)
    draw.text((x1 + 24, y1 + 28), title, font=FONT_BOX_TITLE, fill=INK)
    y = y1 + 74
    max_width = x2 - x1 - 58
    for bullet in bullets:
        draw.ellipse((x1 + 26, y + 9, x1 + 35, y + 18), fill=accent)
        y = draw_wrapped(draw, (x1 + 48, y), bullet, fnt=FONT_BODY, fill=INK, max_width=max_width)
        y += 8
    if code:
        tag_h = 36
        tag_y = y2 - tag_h - 18
        draw.rounded_rectangle((x1 + 22, tag_y, x2 - 22, tag_y + tag_h), radius=12, fill="#eef3f8")
        draw.text((x1 + 38, tag_y + 9), code, font=FONT_TINY, fill=MUTED)


def decision_box(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    *,
    title: str,
    bullets: list[str],
    accent: str,
    code: str | None = None,
) -> tuple[int, int, int, int]:
    cx, cy = center
    w, h = 520, 280
    pts = [(cx, cy - h // 2), (cx + w // 2, cy), (cx, cy + h // 2), (cx - w // 2, cy)]
    shadow = [(x + 7, y + 9) for x, y in pts]
    draw.polygon(shadow, fill="#d8deea")
    draw.polygon(pts, fill=WHITE, outline="#c9d3e3")
    draw.line((pts[0], pts[1], pts[2], pts[3], pts[0]), fill=accent, width=6)
    draw.text((cx - text_width(draw, title, FONT_BOX_TITLE) // 2, cy - 94), title, font=FONT_BOX_TITLE, fill=INK)
    y = cy - 46
    max_width = 360
    for bullet in bullets:
        y = draw_wrapped(draw, (cx - 180, y), bullet, fnt=FONT_BODY, fill=INK, max_width=max_width)
        y += 8
    if code:
        draw.text((cx - text_width(draw, code, FONT_TINY) // 2, cy + 93), code, font=FONT_TINY, fill=MUTED)
    return (cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2)


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, *, fill: str = MUTED) -> None:
    x, y = xy
    tw = text_width(draw, text, FONT_SMALL)
    draw.rounded_rectangle((x, y, x + tw + 28, y + 34), radius=17, fill="#eef3f8", outline="#d3dde9")
    draw.text((x + 14, y + 8), text, font=FONT_SMALL, fill=fill)


def lane(draw: ImageDraw.ImageDraw, y: int, text: str, color: str) -> None:
    draw.rounded_rectangle((95, y, W - 95, y + 44), radius=22, fill=color)
    draw.text((125, y + 10), text, font=FONT_SECTION, fill=WHITE)


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    draw.text((120, 82), "Conversation Memory System Flow", font=FONT_TITLE, fill=INK)
    draw.text(
        (124, 166),
        "How the chatbot starts, continues, refines, or safely exits a shopping flow",
        font=FONT_SUBTITLE,
        fill=MUTED,
    )

    lane(draw, 245, "1. Input and Context", "#24736f")
    top_boxes = {
        "customer": (120, 325, 610, 555),
        "frontend": (720, 325, 1210, 555),
        "api": (1320, 325, 1810, 555),
        "state": (1920, 325, 2410, 555),
        "hydrate": (2520, 325, 3080, 555),
    }
    box(
        draw,
        top_boxes["customer"],
        title="Customer Turn",
        bullets=["Bangla, Banglish, English text", "Optional image upload", "Natural follow-ups like price, size, color"],
        accent="#2a9d8f",
        code="chat.html / chat.js",
    )
    box(
        draw,
        top_boxes["frontend"],
        title="Frontend Context",
        bullets=["Sends session_id", "Recent visible turns", "Focused product IDs and answer plan"],
        accent="#2a9d8f",
        code="frontend/chat.js",
    )
    box(
        draw,
        top_boxes["api"],
        title="Ask Endpoint",
        bullets=["Receives InventoryAskRequest", "Runs service orchestration", "Returns answer + product cards + trace"],
        accent="#2a9d8f",
        code="InventoryService.ask",
    )
    box(
        draw,
        top_boxes["state"],
        title="Server State",
        bullets=["Reads SQLite by session_id", "Product focus, active slots, TTL", "Survives page refresh"],
        accent="#2a9d8f",
        code="conversation_state.py",
    )
    box(
        draw,
        top_boxes["hydrate"],
        title="Safe Hydration",
        bullets=["Restores context only when safe", "Blocks stale focus on new category", "Adds active filters for slot updates"],
        accent="#2a9d8f",
        code="conversation_context.py",
    )
    arrow(draw, (610, 440), (720, 440))
    arrow(draw, (1210, 440), (1320, 440))
    arrow(draw, (1810, 440), (1920, 440))
    arrow(draw, (2410, 440), (2520, 440))

    lane(draw, 640, "2. Flow Router", "#415a77")
    router = decision_box(
        draw,
        (1600, 840),
        title="decide_flow",
        bullets=["Classify the turn by role", "New product beats old memory", "Support/safety never writes shopping preference"],
        accent="#5e81ac",
        code="conversation_flow.py",
    )
    arrow(draw, (2800, 555), (1845, 745))

    route_y = 1080
    route_boxes = [
        (
            "START_NEW_FLOW",
            (120, route_y, 560, route_y + 230),
            "#457b9d",
            ["Fresh product/category", "Clear stale product focus", "Search new category"],
        ),
        (
            "UPDATE_FLOW_SLOTS",
            (640, route_y, 1080, route_y + 230),
            "#2a9d8f",
            ["Slot-only refinement", "Keep active category", "Apply color/size/budget"],
        ),
        (
            "CONTINUE_FOCUS",
            (1160, route_y, 1600, route_y + 230),
            "#8d99ae",
            ["Price, stock, size", "Use focused product/list", "Requires fresh TTL"],
        ),
        (
            "COMPARE_OR_SIMILAR",
            (1680, route_y, 2120, route_y + 230),
            "#6d597a",
            ["Similar, cheaper, matching", "Use current anchor", "Retrieve alternatives"],
        ),
        (
            "SUPPORT_ROUTE",
            (2200, route_y, 2640, route_y + 230),
            "#e9a23b",
            ["Delivery, return, order", "Answer policy", "Do not overwrite focus"],
        ),
        (
            "SAFETY_ROUTE",
            (2720, route_y, 3080, route_y + 230),
            "#c44536",
            ["Medical, legal, crisis", "Safe boundary", "No commerce memory"],
        ),
    ]
    for title, xy, accent, bullets in route_boxes:
        box(draw, xy, title=title, bullets=bullets, accent=accent)
        arrow(draw, (1600, router[3]), ((xy[0] + xy[2]) // 2, xy[1]), color="#a5b4c6", width=4)

    lane(draw, 1390, "3. Retrieval and Answer", "#5c677d")
    lower_boxes = {
        "policy": (120, 1480, 620, 1740),
        "retrieval": (760, 1480, 1260, 1740),
        "answer": (1400, 1480, 1900, 1740),
        "trace": (2040, 1480, 2540, 1740),
        "write": (2680, 1480, 3080, 1740),
    }
    box(
        draw,
        lower_boxes["policy"],
        title="Memory Policy",
        bullets=["Check TTL and confidence", "Allow only clear follow-ups", "Ignore old focus on new category"],
        accent="#5c677d",
        code="memory_policy.py",
    )
    box(
        draw,
        lower_boxes["retrieval"],
        title="Catalog Retrieval",
        bullets=["Use hydrated filters", "Prefer in-stock products", "Ground answer in catalog facts"],
        accent="#5c677d",
        code="fashion_retail.py",
    )
    box(
        draw,
        lower_boxes["answer"],
        title="Answer Builder",
        bullets=["Direct answer when evidence exists", "Product cards with price/stock", "Ask only one useful question if needed"],
        accent="#5c677d",
        code="inventory_service.py",
    )
    box(
        draw,
        lower_boxes["trace"],
        title="Response Trace",
        bullets=["flow_action and reason", "active_category_key", "retrieval_scope and ignored memory reason"],
        accent="#5c677d",
        code="memory_resolution",
    )
    box(
        draw,
        lower_boxes["write"],
        title="Safe Writeback",
        bullets=["Save product focus and slots", "Attach source, confidence, TTL", "Block unsafe/off-topic preferences"],
        accent="#5c677d",
        code="record_turn",
    )
    arrow(draw, (340, route_y + 230), (340, 1480), width=4)
    arrow(draw, (860, route_y + 230), (370, 1480), width=4)
    arrow(draw, (1380, route_y + 230), (370, 1480), width=4)
    arrow(draw, (1900, route_y + 230), (370, 1480), width=4)
    arrow(draw, (2420, route_y + 230), (1650, 1480), width=4)
    arrow(draw, (2900, route_y + 230), (1650, 1480), width=4)
    arrow(draw, (620, 1610), (760, 1610))
    arrow(draw, (1260, 1610), (1400, 1610))
    arrow(draw, (1900, 1610), (2040, 1610))
    arrow(draw, (2540, 1610), (2680, 1610))

    lane(draw, 1835, "4. Guardrails and Tests", "#2f3e46")
    guard = (120, 1925, 1000, 2165)
    tests = (1120, 1925, 2000, 2165)
    manual = (2120, 1925, 3080, 2165)
    box(
        draw,
        guard,
        title="Non-Negotiable Guardrails",
        bullets=[
            "Product focus only for clear follow-ups",
            "30 minute default product TTL",
            "New category always overrides old category",
            "Unsafe/support text never becomes preference",
        ],
        accent="#2f3e46",
    )
    box(
        draw,
        tests,
        title="Regression Tests",
        bullets=[
            "Dummy flow regression: 15/15",
            "Memory flow eval: 100/100",
            "Focused pytest stack covers service wiring",
        ],
        accent="#2f3e46",
        code="scripts/run_dummy_flow_regression.py",
    )
    box(
        draw,
        manual,
        title="Manual UI Test",
        bullets=[
            "Salwar Kameez -> wedding red -> price",
            "Then switch to black shoe -> size 42",
            "Delivery/safety detours must not corrupt product flow",
        ],
        accent="#2f3e46",
        code="http://.../frontend/chat.html",
    )

    label(draw, (116, 2200), "Best next UI addition: Memory Inspector showing flow_action, active_category, focused product, TTL, and ignored-memory reason.")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT_PATH, quality=95)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()

