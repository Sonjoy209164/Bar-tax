from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageChops, ImageOps


PreprocessVariant = Literal["full", "crop", "gray"]
PREPROCESS_VERSION = "image-preprocess-v1"


@dataclass(frozen=True)
class ImagePreprocessResult:
    image_id: str
    source: str
    full_path: str
    crop_path: str
    gray_path: str
    meta_path: str
    width: int
    height: int
    crop_width: int
    crop_height: int
    dominant_color: str | None
    color_family: str | None
    preprocess_version: str = PREPROCESS_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def preprocess_image_source(
    *,
    source: str,
    image_id: str,
    cache_root: str | Path = "data/inventory/image_cache",
    max_size: int = 900,
) -> ImagePreprocessResult:
    """Normalize image source and save full/crop/grayscale variants.

    This intentionally stays dependency-light. It does not try to solve full
    product segmentation; it removes obvious flat borders and creates stable
    images for embedding/debugging.
    """

    cache_dir = Path(cache_root) / safe_id(image_id)
    cache_dir.mkdir(parents=True, exist_ok=True)

    image = load_image(source)
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    full = image.copy()
    crop = trim_flat_border(full)
    gray = ImageOps.grayscale(crop).convert("RGB")
    dominant_color, color_family = dominant_color_name(crop)

    full_path = cache_dir / "full.jpg"
    crop_path = cache_dir / "crop.jpg"
    gray_path = cache_dir / "gray.jpg"
    meta_path = cache_dir / "meta.json"

    full.save(full_path, format="JPEG", quality=90, optimize=True)
    crop.save(crop_path, format="JPEG", quality=90, optimize=True)
    gray.save(gray_path, format="JPEG", quality=90, optimize=True)

    result = ImagePreprocessResult(
        image_id=image_id,
        source=source,
        full_path=full_path.as_posix(),
        crop_path=crop_path.as_posix(),
        gray_path=gray_path.as_posix(),
        meta_path=meta_path.as_posix(),
        width=full.width,
        height=full.height,
        crop_width=crop.width,
        crop_height=crop.height,
        dominant_color=dominant_color,
        color_family=color_family,
    )
    meta_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def load_image(source: str) -> Image.Image:
    if source.startswith("data:image/"):
        _, payload = source.split(",", 1)
        return Image.open(io.BytesIO(base64.b64decode(payload)))
    if source.startswith("base64:"):
        return Image.open(io.BytesIO(base64.b64decode(source.split(":", 1)[1])))
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(source)
    return Image.open(path)


def trim_flat_border(image: Image.Image) -> Image.Image:
    if image.width < 32 or image.height < 32:
        return image
    background = Image.new("RGB", image.size, image.getpixel((0, 0)))
    diff = ImageChops.difference(image, background)
    diff = ImageChops.add(diff, diff, 2.0, -18)
    bbox = diff.getbbox()
    if bbox is None:
        return center_crop(image)
    left, top, right, bottom = bbox
    margin_x = max(8, int((right - left) * 0.04))
    margin_y = max(8, int((bottom - top) * 0.04))
    left = max(0, left - margin_x)
    top = max(0, top - margin_y)
    right = min(image.width, right + margin_x)
    bottom = min(image.height, bottom + margin_y)
    if right - left < image.width * 0.25 or bottom - top < image.height * 0.25:
        return center_crop(image)
    return image.crop((left, top, right, bottom))


def center_crop(image: Image.Image) -> Image.Image:
    side = min(image.width, image.height)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    return image.crop((left, top, left + side, top + side))


def dominant_color_name(image: Image.Image) -> tuple[str | None, str | None]:
    sample = image.copy()
    sample.thumbnail((80, 80), Image.Resampling.BILINEAR)
    pixels = list(sample.convert("RGB").getdata())
    if not pixels:
        return None, None

    filtered = [
        pixel for pixel in pixels
        if not (pixel[0] > 238 and pixel[1] > 238 and pixel[2] > 238)
    ] or pixels
    avg = tuple(sum(pixel[i] for pixel in filtered) / len(filtered) for i in range(3))
    name = nearest_color_name(avg)
    return name, color_family(name)


def nearest_color_name(rgb: tuple[float, float, float]) -> str:
    palette = {
        "black": (20, 20, 20),
        "white": (238, 238, 232),
        "grey": (128, 128, 128),
        "red": (180, 35, 35),
        "maroon": (100, 25, 35),
        "pink": (220, 120, 160),
        "blue": (45, 95, 180),
        "navy": (20, 35, 90),
        "green": (45, 130, 70),
        "olive": (85, 95, 45),
        "yellow": (220, 190, 45),
        "gold": (190, 145, 45),
        "brown": (120, 75, 45),
        "cream": (225, 210, 175),
        "purple": (115, 70, 155),
        "orange": (220, 120, 45),
        "silver": (180, 185, 190),
    }
    return min(
        palette,
        key=lambda name: sum((rgb[i] - palette[name][i]) ** 2 for i in range(3)),
    )


def color_family(name: str | None) -> str | None:
    if not name:
        return None
    return {
        "navy": "blue",
        "maroon": "red",
        "olive": "green",
        "cream": "white",
        "silver": "silver",
        "gold": "gold",
    }.get(name, name)


def safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-") or "image"
