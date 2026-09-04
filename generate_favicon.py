#!/usr/bin/env python3
"""Generate browser favicons from the circular emblem photograph.

The source is a detailed 3D emblem. Direct 16×16 downscale loses the
yin-yang and the red/blue gems, so small sizes crop toward the center
and slightly enlarge those gems before resampling. Transparency is
applied only outside the outer silhouette; interior whites stay opaque.
"""

from __future__ import annotations

import argparse
import io
import struct
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / "assets" / "favicon-source.jpg"
DEFAULT_OUT = ROOT

PNG_SIZES = (16, 32, 48, 180, 192, 512)
ICO_SIZES = (16, 32, 48)


def _exterior_mask(rgb: np.ndarray) -> np.ndarray:
    """True only for the canvas background, flood-filled from the corners.

    Interior whites (yin-yang, metallic highlights) stay part of the emblem.
    """
    rgb_u8 = np.clip(rgb, 0, 255).astype(np.uint8)
    lum = rgb_u8.mean(axis=2)
    chroma = rgb_u8.max(axis=2) - rgb_u8.min(axis=2)
    candidate = (lum >= 236) & (chroma <= 32)
    height, width = candidate.shape
    fill = np.zeros((height, width), np.uint8)
    fill[candidate] = 255
    for x, y in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        if fill[y, x] == 255:
            cv2.floodFill(fill, None, (x, y), 64)
    exterior = fill == 64
    emblem = np.where(exterior, 0, 255).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    emblem = cv2.morphologyEx(emblem, cv2.MORPH_CLOSE, kernel)
    return emblem == 0


def _feathered_alpha(exterior: np.ndarray, feather: float = 1.4) -> np.ndarray:
    """Opaque inside the silhouette; transparent only outside it."""
    inside = np.where(exterior, 0, 255).astype(np.uint8)
    outside = np.where(exterior, 255, 0).astype(np.uint8)
    dist_in = cv2.distanceTransform(inside, cv2.DIST_L2, 3)
    dist_out = cv2.distanceTransform(outside, cv2.DIST_L2, 3)
    return np.clip(0.5 + (dist_in - dist_out) / (2.0 * feather), 0.0, 1.0).astype(np.float32)


def _silhouette_bounds(emblem: np.ndarray) -> tuple[float, float, float]:
    ys, xs = np.where(emblem)
    if xs.size == 0:
        raise ValueError("favicon source has no non-white emblem")
    cx = (float(xs.min()) + float(xs.max())) / 2.0
    cy = (float(ys.min()) + float(ys.max())) / 2.0
    radius = float(np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2).max())
    return cx, cy, radius


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask
    h, w = mask.shape
    padded = np.pad(mask.astype(np.uint8), radius)
    out = np.zeros_like(mask, dtype=bool)
    r2 = radius * radius
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= r2:
                out |= padded[radius + dy : radius + dy + h, radius + dx : radius + dx + w].astype(bool)
    return out


def _gem_masks(rgba: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    r, g, b, a = rgba[:, :, 0], rgba[:, :, 1], rgba[:, :, 2], rgba[:, :, 3]
    red = (r > 120) & (r > g * 1.3) & (r > b * 1.2) & (a > 80)
    blue = (b > 120) & (b > r * 1.2) & (b > g * 1.05) & (a > 80)
    return red, blue


def load_emblem(path: Path) -> Image.Image:
    """Return a square RGBA emblem; transparency is only outside the silhouette."""
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    h, w = rgb.shape[:2]
    exterior = _exterior_mask(rgb)
    alpha = _feathered_alpha(exterior)
    cx, cy, radius = _silhouette_bounds(~exterior)

    rgba = np.zeros((h, w, 4), dtype=np.float32)
    rgba[..., :3] = rgb
    rgba[..., 3] = alpha * 255

    inside = alpha > 0.5
    for c in range(3):
        channel = rgba[..., c]
        lo, hi = np.percentile(channel[inside], (1, 99))
        rgba[..., c] = np.clip((channel - lo) * (255.0 / max(hi - lo, 1.0)), 0, 255)

    red, blue = _gem_masks(rgba)
    rgba[red, :3] = np.clip(rgba[red, :3] * [1.16, 0.78, 0.78] + [18, 0, 0], 0, 255)
    rgba[blue, :3] = np.clip(rgba[blue, :3] * [0.72, 0.82, 1.18] + [0, 0, 22], 0, 255)

    master = Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), "RGBA")
    pad = int(round(radius * 0.045))
    left = max(0, int(round(cx - radius)) - pad)
    top = max(0, int(round(cy - radius)) - pad)
    right = min(w, int(round(cx + radius)) + pad)
    bottom = min(h, int(round(cy + radius)) + pad)
    side = min(right - left, bottom - top)
    cx_i, cy_i = int(round(cx)), int(round(cy))
    half = side // 2
    left = max(0, min(w - side, cx_i - half))
    top = max(0, min(h - side, cy_i - half))
    return master.crop((left, top, left + side, top + side))


def _crop_center(im: Image.Image, fraction: float) -> Image.Image:
    fraction = min(1.0, max(0.2, fraction))
    width, height = im.size
    side = int(round(min(width, height) * fraction))
    left = (width - side) // 2
    top = (height - side) // 2
    return im.crop((left, top, left + side, top + side))


def _emphasize_gems(im: Image.Image, radius: int) -> Image.Image:
    arr = np.array(im).astype(np.float32)
    red, blue = _gem_masks(arr)
    if radius > 0:
        red = _dilate(red, radius)
        blue = _dilate(blue, radius)
    arr[red, :3] = [228, 26, 36]
    arr[blue, :3] = [24, 58, 232]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def render_size(emblem: Image.Image, size: int) -> Image.Image:
    if size <= 16:
        prepared = _emphasize_gems(_crop_center(emblem, 0.66), 22)
    elif size <= 32:
        prepared = _emphasize_gems(_crop_center(emblem, 0.88), 10)
    elif size <= 48:
        prepared = _emphasize_gems(emblem, 4)
    else:
        prepared = emblem

    current = prepared
    if current.size[0] > size * 4:
        mid = max(size * 2, 64)
        current = current.resize((mid, mid), Image.Resampling.LANCZOS)
        current = current.filter(ImageFilter.UnsharpMask(radius=1.0, percent=110, threshold=1))
    out = current.resize((size, size), Image.Resampling.LANCZOS)
    if size <= 48:
        out = out.filter(
            ImageFilter.UnsharpMask(
                radius=0.55 if size <= 32 else 0.75,
                percent=150 if size <= 32 else 115,
                threshold=0,
            )
        )
    return out


def flatten_on_black(im: Image.Image) -> Image.Image:
    bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
    return Image.alpha_composite(bg, im.convert("RGBA")).convert("RGBA")


def write_ico(path: Path, images: list[Image.Image]) -> None:
    """Write a PNG-in-ICO file so each size keeps its own pixel art."""
    payloads: list[bytes] = []
    for im in images:
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        payloads.append(buf.getvalue())
    offset = 6 + 16 * len(images)
    with path.open("wb") as fh:
        fh.write(struct.pack("<HHH", 0, 1, len(images)))
        for im, data in zip(images, payloads):
            width, height = im.size
            fh.write(
                struct.pack(
                    "<BBBBHHII",
                    width if width < 256 else 0,
                    height if height < 256 else 0,
                    0,
                    0,
                    1,
                    32,
                    len(data),
                    offset,
                )
            )
            offset += len(data)
        for data in payloads:
            fh.write(data)


def generate(source: Path, out_dir: Path) -> dict[str, Path]:
    emblem = load_emblem(source)
    out_dir = out_dir.resolve()
    icons_dir = out_dir / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    rendered = {size: render_size(emblem, size) for size in PNG_SIZES}
    rendered[180] = flatten_on_black(rendered[180])

    written: dict[str, Path] = {}
    mapping = {
        16: icons_dir / "favicon-16.png",
        32: icons_dir / "favicon-32.png",
        48: icons_dir / "favicon-48.png",
        180: icons_dir / "apple-touch-icon.png",
        192: icons_dir / "icon-192.png",
        512: icons_dir / "icon-512.png",
    }
    for size, dest in mapping.items():
        rendered[size].save(dest, format="PNG", optimize=True)
        written[dest.name] = dest

    ico_path = out_dir / "favicon.ico"
    write_ico(ico_path, [rendered[size] for size in ICO_SIZES])
    written[ico_path.name] = ico_path
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    if not args.source.is_file():
        raise SystemExit(f"missing favicon source: {args.source}")
    written = generate(args.source, args.out)
    for name, path in written.items():
        print(f"{name}: {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
