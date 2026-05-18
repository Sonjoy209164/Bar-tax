from __future__ import annotations

from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "assets" / "image_search_workflow.png"

W, H = 2400, 1650
BG = "#ffffff"
INK = "#172033"
MUTED = "#5f6b7a"
GRID = "#e8edf3"
BLUE = "#e8f1ff"
BLUE_STROKE = "#2f69c9"
GREEN = "#eaf7ee"
GREEN_STROKE = "#26834f"
YELLOW = "#fff6dd"
YELLOW_STROKE = "#b47a00"
RED = "#fff0f0"
RED_STROKE = "#c84d4d"
PURPLE = "#f3edff"
PURPLE_STROKE = "#7b55c7"
GRAY = "#f6f8fb"
GRAY_STROKE = "#8994a3"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    base = "/usr/share/fonts/truetype/dejavu"
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(Path(base) / name), size)


TITLE = font(46, bold=True)
SUBTITLE = font(24)
SECTION = font(26, bold=True)
BODY = font(22)
SMALL = font(18)
TINY = font(16)


def draw_grid(draw: ImageDraw.ImageDraw) -> None:
    for x in range(80, W, 80):
        draw.line((x, 0, x, H), fill=GRID, width=1)
    for y in range(80, H, 80):
        draw.line((0, y, W, y), fill=GRID, width=1)


def wrap(text: str, chars: int) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        if not raw.strip():
            lines.append("")
            continue
        lines.extend(textwrap.wrap(raw, width=chars, break_long_words=False))
    return lines


def rounded_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    title: str,
    body: str,
    *,
    fill: str,
    stroke: str,
    title_font: ImageFont.FreeTypeFont = SECTION,
    body_font: ImageFont.FreeTypeFont = SMALL,
    body_chars: int = 30,
) -> None:
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=20, fill=fill, outline=stroke, width=3)
    draw.text((x1 + 24, y1 + 18), title, fill=INK, font=title_font)
    y = y1 + 58
    for line in wrap(body, body_chars):
        draw.text((x1 + 24, y), line, fill=MUTED, font=body_font)
        y += 25


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    color: str = "#34495e",
    width: int = 4,
    label: str | None = None,
    label_offset: tuple[int, int] = (0, 0),
) -> None:
    draw.line((*start, *end), fill=color, width=width)
    ex, ey = end
    sx, sy = start
    if abs(ex - sx) >= abs(ey - sy):
        direction = 1 if ex >= sx else -1
        points = [(ex, ey), (ex - 18 * direction, ey - 10), (ex - 18 * direction, ey + 10)]
    else:
        direction = 1 if ey >= sy else -1
        points = [(ex, ey), (ex - 10, ey - 18 * direction), (ex + 10, ey - 18 * direction)]
    draw.polygon(points, fill=color)
    if label:
        lx = (sx + ex) // 2 + label_offset[0]
        ly = (sy + ey) // 2 + label_offset[1]
        bbox = draw.textbbox((lx, ly), label, font=TINY)
        pad = 7
        draw.rounded_rectangle(
            (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad),
            radius=8,
            fill="#ffffff",
            outline="#d8dee8",
            width=1,
        )
        draw.text((lx, ly), label, fill=MUTED, font=TINY)


def elbow_arrow(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    *,
    color: str = "#34495e",
    width: int = 4,
    label: str | None = None,
    label_at: tuple[int, int] | None = None,
) -> None:
    if len(points) < 2:
        return
    for start, end in zip(points, points[1:]):
        draw.line((*start, *end), fill=color, width=width)
    start = points[-2]
    end = points[-1]
    ex, ey = end
    sx, sy = start
    if abs(ex - sx) >= abs(ey - sy):
        direction = 1 if ex >= sx else -1
        arrow_head = [(ex, ey), (ex - 18 * direction, ey - 10), (ex - 18 * direction, ey + 10)]
    else:
        direction = 1 if ey >= sy else -1
        arrow_head = [(ex, ey), (ex - 10, ey - 18 * direction), (ex + 10, ey - 18 * direction)]
    draw.polygon(arrow_head, fill=color)
    if label and label_at:
        lx, ly = label_at
        bbox = draw.textbbox((lx, ly), label, font=TINY)
        pad = 7
        draw.rounded_rectangle(
            (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad),
            radius=8,
            fill="#ffffff",
            outline="#d8dee8",
            width=1,
        )
        draw.text((lx, ly), label, fill=MUTED, font=TINY)


def make() -> None:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_grid(draw)

    draw.text((100, 65), "Image Search Workflow: From Screenshot To Grounded Reply", fill=INK, font=TITLE)
    draw.text(
        (100, 125),
        "Visual model suggests candidates. Catalog identity and business facts decide what the bot can safely claim.",
        fill=MUTED,
        font=SUBTITLE,
    )

    # Column headers
    headers = [
        (100, "1. Input"),
        (470, "2. Retrieval"),
        (980, "3. Decision"),
        (1600, "4. Reply"),
    ]
    for x, text in headers:
        draw.text((x, 200), text, fill=INK, font=SECTION)

    # Main lane boxes
    rounded_box(
        draw,
        (90, 255, 395, 430),
        "Customer",
        "Uploads screenshot and optional text.\nExample: 'white color ache?'",
        fill=BLUE,
        stroke=BLUE_STROKE,
        body_chars=26,
    )
    rounded_box(
        draw,
        (90, 505, 395, 680),
        "Chat UI",
        "frontend/chat.js sends image_b64, text, session_id, top_k.",
        fill=BLUE,
        stroke=BLUE_STROKE,
        body_chars=27,
    )
    rounded_box(
        draw,
        (90, 755, 395, 930),
        "API Route",
        "POST /inventory/image-search or /inventory/ask with image.",
        fill=BLUE,
        stroke=BLUE_STROKE,
        body_chars=27,
    )

    rounded_box(
        draw,
        (470, 255, 820, 430),
        "Service Orchestrator",
        "InventoryService creates query_image_id and chooses retrieval engine.",
        fill=PURPLE,
        stroke=PURPLE_STROKE,
        body_chars=30,
    )
    rounded_box(
        draw,
        (470, 505, 820, 700),
        "CLIP Visual Search",
        "full_visual, pattern_visual, text_visual_tags channels with cosine similarity.",
        fill=GREEN,
        stroke=GREEN_STROKE,
        body_chars=31,
    )
    rounded_box(
        draw,
        (470, 775, 820, 950),
        "Metadata Fallback",
        "Used if CLIP cannot load. Safer than crashing, weaker than true vision.",
        fill=YELLOW,
        stroke=YELLOW_STROKE,
        body_chars=31,
    )
    rounded_box(
        draw,
        (470, 1030, 820, 1205),
        "Raw Candidates",
        "ImageMatchResult list: product_id, visual score, match channel, reasons.",
        fill=GRAY,
        stroke=GRAY_STROKE,
        body_chars=31,
    )

    rounded_box(
        draw,
        (980, 255, 1340, 430),
        "Catalog Truth",
        "catalog.jsonl provides price, stock, images, variant_group_id, design_id.",
        fill=GREEN,
        stroke=GREEN_STROKE,
        body_chars=31,
    )
    rounded_box(
        draw,
        (980, 505, 1340, 700),
        "Owner Corrections",
        "Exact, same_design, similar, or no_match overrides raw visual guess.",
        fill=YELLOW,
        stroke=YELLOW_STROKE,
        body_chars=31,
    )
    rounded_box(
        draw,
        (980, 775, 1340, 950),
        "Enrich Hits",
        "Adds image_kind, is_reference, stock, color, design_id, variant_group_id.",
        fill=PURPLE,
        stroke=PURPLE_STROKE,
        body_chars=31,
    )
    rounded_box(
        draw,
        (980, 1030, 1340, 1205),
        "Safety Gates",
        "Primary anchor, exact-match gate, outlier pruning, reference-photo guard.",
        fill=RED,
        stroke=RED_STROKE,
        body_chars=31,
    )
    rounded_box(
        draw,
        (980, 1280, 1340, 1455),
        "Variant Resolver",
        "Finds same-design colors/sizes using variant_group_id and design_id.",
        fill=GREEN,
        stroke=GREEN_STROKE,
        body_chars=31,
    )

    rounded_box(
        draw,
        (1600, 255, 1985, 430),
        "Business Check",
        "Requested color, requested size, stock, price, availability.",
        fill=GREEN,
        stroke=GREEN_STROKE,
        body_chars=34,
    )
    rounded_box(
        draw,
        (1600, 505, 1985, 700),
        "Decision Label",
        "confirmed_exact, confirmed_same_design_variant, likely_same_design, similar_style, no_confident_match.",
        fill=PURPLE,
        stroke=PURPLE_STROKE,
        body_chars=35,
    )
    rounded_box(
        draw,
        (1600, 775, 1985, 970),
        "Answer Writer",
        "Writes seller-like reply. Wording matches evidence strength.",
        fill=BLUE,
        stroke=BLUE_STROKE,
        body_chars=34,
    )
    rounded_box(
        draw,
        (1600, 1050, 1985, 1235),
        "Product Cards",
        "Shows image, name, price, stock, color, size, match badge.",
        fill=BLUE,
        stroke=BLUE_STROKE,
        body_chars=34,
    )
    rounded_box(
        draw,
        (1600, 1310, 1985, 1495),
        "Trace + Memory",
        "Stores previous image result for follow-ups and saves debug trace.",
        fill=GRAY,
        stroke=GRAY_STROKE,
        body_chars=34,
    )

    # Side notes
    rounded_box(
        draw,
        (2055, 255, 2305, 545),
        "Trust Rule",
        "Never claim exact only because CLIP score is high. Exact needs product_photo or owner-confirmed identity.",
        fill="#fffaf0",
        stroke=YELLOW_STROKE,
        title_font=font(23, bold=True),
        body_font=TINY,
        body_chars=24,
    )
    rounded_box(
        draw,
        (2055, 620, 2305, 920),
        "Same Design Rule",
        "variant_group_id and design_id are stronger than raw similarity for color variants.",
        fill="#f4fff7",
        stroke=GREEN_STROKE,
        title_font=font(23, bold=True),
        body_font=TINY,
        body_chars=24,
    )
    rounded_box(
        draw,
        (2055, 995, 2305, 1295),
        "Feedback Loop",
        "Failures and owner corrections improve future ranking without daily fine-tuning.",
        fill="#f6f8fb",
        stroke=GRAY_STROKE,
        title_font=font(23, bold=True),
        body_font=TINY,
        body_chars=24,
    )

    # Main arrows
    arrow(draw, (245, 430), (245, 505), label="image preview")
    arrow(draw, (245, 680), (245, 755), label="request")
    elbow_arrow(
        draw,
        [(395, 842), (430, 842), (430, 342), (470, 342)],
        label="service call",
        label_at=(385, 470),
    )
    arrow(draw, (645, 430), (645, 505), label="if CLIP loads")
    arrow(draw, (645, 430), (645, 775), label="fallback", label_offset=(20, 80))
    arrow(draw, (645, 700), (645, 1030), label="raw visual hits")
    arrow(draw, (645, 950), (645, 1030), label="raw metadata hits")

    arrow(draw, (820, 1118), (980, 592), label="candidate list", label_offset=(-45, -125))
    arrow(draw, (1160, 430), (1160, 505), label="owner truth")
    arrow(draw, (1160, 700), (1160, 775), label="corrected hits")
    arrow(draw, (1160, 950), (1160, 1030), label="enriched hits")
    arrow(draw, (1160, 1205), (1160, 1280), label="safe anchor")

    elbow_arrow(
        draw,
        [(1340, 1368), (1465, 1368), (1465, 342), (1600, 342)],
        label="variant + stock facts",
        label_at=(1405, 645),
    )
    arrow(draw, (1792, 430), (1792, 505), label="facts checked")
    arrow(draw, (1792, 700), (1792, 775), label="label controls wording")
    arrow(draw, (1792, 970), (1792, 1050), label="render")
    arrow(draw, (1792, 1235), (1792, 1310), label="remember")

    # Data truth arrows
    arrow(draw, (980, 342), (820, 592), color=GREEN_STROKE, label="catalog images")
    arrow(draw, (1160, 430), (1160, 775), color=GREEN_STROKE, label="catalog facts", label_offset=(55, 40))
    arrow(draw, (1340, 342), (1600, 342), color=GREEN_STROKE, label="price/stock")

    # Side note arrows
    arrow(draw, (1985, 592), (2055, 400), color=YELLOW_STROKE)
    arrow(draw, (1985, 1402), (2055, 1145), color=GRAY_STROKE)

    # Footer
    draw.rounded_rectangle((90, 1540, 2310, 1605), radius=18, fill="#172033", outline="#172033")
    draw.text(
        (120, 1558),
        "Mental model: CLIP finds candidates -> catalog confirms identity -> policy controls confidence -> answer writer sells clearly.",
        fill="#ffffff",
        font=SUBTITLE,
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUTPUT, quality=96)
    print(OUTPUT)


if __name__ == "__main__":
    make()
