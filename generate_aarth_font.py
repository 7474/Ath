#!/usr/bin/env python3
"""
generate_aarth_font.py
======================
Generates aarth.ttf and aarth.woff2 from the Ath (Ath alphabet) raster image.

Pipeline:
  1. Download the source PNG from Wikimedia Commons (or use a local file).
  2. Pre-process with OpenCV: grayscale → threshold → noise removal.
  3. Detect glyph bounding boxes via contour finding; sort top→bottom, left→right.
  4. For each glyph: save as PBM bitmap, call `potrace` to produce an SVG path.
  5. Build a TTF font via fontTools (TTFont + pens), then compress to WOFF2.

Usage:
    python generate_aarth_font.py [--image PATH_OR_URL]

Requirements (install once):
    pip install opencv-python-headless pillow fonttools brotli
    sudo apt-get install potrace          # Debian/Ubuntu
    # macOS:  brew install potrace
    # Windows: download from http://potrace.sourceforge.net/
"""

import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Mapping: glyph extraction order (row-major, L→R) → Unicode code points
# The Ath/Ath alphabet has 28 phonemes; we map them to lowercase ASCII
# letters plus a handful of digraph keys following the "Nine Lives" convention.
#
# Row 0: a  i  u  é  o  e  c      → a  i  u  U+00E9  o  e  c
# Row 1: s  t  l  n  h  p  f      → s  t  l  n  h  p  f
# Row 2: m  ï  ai y  œ  r  ü      → m  U+00EF  U+0061U+0069→'A'  y  U+0153  r  U+00FC
# Row 3: au ÿ  eu g  z  d  b      → U+0061U+0075→'I'  U+00FF  U+0065U+0075→'E'  g  z  d  b
#
# For simplicity the digraphs / special vowels get mapped to uppercase ASCII
# placeholders so they can be used in CSS/HTML if needed.
# ---------------------------------------------------------------------------

GLYPH_CODEPOINTS = [
    # row 0
    ord('a'), ord('i'), ord('u'), 0x00E9, ord('o'), ord('e'), ord('c'),
    # row 1
    ord('s'), ord('t'), ord('l'), ord('n'), ord('h'), ord('p'), ord('f'),
    # row 2
    ord('m'), 0x00EF, ord('A'), ord('y'), 0x0153, ord('r'), 0x00FC,
    # row 3
    ord('I'), 0x00FF, ord('E'), ord('g'), ord('z'), ord('d'), ord('b'),
]

GLYPH_NAMES = [
    'a', 'i', 'u', 'eacute', 'o', 'e', 'c',
    's', 't', 'l', 'n', 'h', 'p', 'f',
    'm', 'idieresis', 'ai', 'y', 'oe', 'r', 'udieresis',
    'au', 'ydieresis', 'eu', 'g', 'z', 'd', 'b',
]

SOURCE_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/2/23/Ath_%28alphabet%29.png"
)

EM = 1000          # units per em
ASCENDER = 800
DESCENDER = -200
CAP_HEIGHT = 700
X_HEIGHT = 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def download_image(url: str, dest: Path) -> None:
    print(f"[download] {url} → {dest}")
    headers = {"User-Agent": "AarthFontGenerator/1.0 (educational project)"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def load_and_binarize(image_path: Path) -> np.ndarray:
    """Return a binary (0/255) OpenCV image where glyphs are WHITE on BLACK."""
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    # The source image is black ink on white paper → invert after threshold
    _, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Glyphs are dark (0) on white (255); invert so glyphs are white on black
    binary = cv2.bitwise_not(binary)
    # Remove small noise
    kernel = np.ones((2, 2), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    return binary


def find_glyph_boxes(binary: np.ndarray, min_area: int = 300):
    """
    Find bounding boxes of individual glyphs.
    Returns list of (x, y, w, h) sorted top-to-bottom, left-to-right by row.
    """
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w * h < min_area:
            continue
        # Ignore very wide boxes that are likely separator lines
        if w > binary.shape[1] * 0.8:
            continue
        boxes.append((x, y, w, h))

    if not boxes:
        return boxes

    # Sort into rows using a y-tolerance of half the median glyph height
    heights = sorted([h for _, _, _, h in boxes])
    median_h = heights[len(heights) // 2]
    row_tol = median_h * 0.6

    boxes.sort(key=lambda b: b[1])  # sort by y first

    rows = []
    current_row = [boxes[0]]
    for box in boxes[1:]:
        if abs(box[1] - current_row[-1][1]) < row_tol:
            current_row.append(box)
        else:
            rows.append(sorted(current_row, key=lambda b: b[0]))
            current_row = [box]
    rows.append(sorted(current_row, key=lambda b: b[0]))

    result = [box for row in rows for box in row]
    return result


def crop_glyph(binary: np.ndarray, box, padding: int = 4) -> np.ndarray:
    x, y, w, h = box
    img_h, img_w = binary.shape
    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(img_w, x + w + padding)
    y2 = min(img_h, y + h + padding)
    return binary[y1:y2, x1:x2]


def glyph_to_svg_path(glyph_img: np.ndarray, tmp_dir: Path, idx: int) -> str | None:
    """
    Save glyph as PBM, run potrace, return the SVG path 'd' string.
    Potrace produces a path with (0,0) at bottom-left in PostScript coords.
    """
    pbm_path = tmp_dir / f"glyph_{idx:03d}.pbm"
    svg_path = tmp_dir / f"glyph_{idx:03d}.svg"

    # Convert to pure B/W PIL image
    pil = Image.fromarray(glyph_img).convert("1")
    pil.save(str(pbm_path))

    try:
        subprocess.run(
            ["potrace", "--svg", "--output", str(svg_path), str(pbm_path)],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"  [warn] potrace failed for glyph {idx}: {exc.stderr.decode()}")
        return None
    except FileNotFoundError:
        print("  [error] potrace not found. Install it with: sudo apt-get install potrace")
        sys.exit(1)

    return parse_svg_path(svg_path)


def parse_svg_path(svg_file: Path) -> str | None:
    """Extract the 'd' attribute from the first <path> in the SVG."""
    try:
        tree = ET.parse(str(svg_file))
        root = tree.getroot()
        ns = {"svg": "http://www.w3.org/2000/svg"}
        paths = root.findall(".//svg:path", ns)
        if not paths:
            paths = root.findall(".//{http://www.w3.org/2000/svg}path")
        if paths:
            return paths[0].get("d", "")
    except ET.ParseError:
        pass
    return None


# ---------------------------------------------------------------------------
# SVG path → fontTools pen
# ---------------------------------------------------------------------------

def _parse_number(s: str) -> tuple[float, str]:
    """Parse one floating-point number from string, return (value, rest)."""
    s = s.lstrip()
    m = re.match(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", s)
    if not m:
        raise ValueError(f"Expected number in: {s!r}")
    return float(m.group()), s[m.end():]


def _parse_coord_pair(s: str) -> tuple[tuple[float, float], str]:
    s = s.lstrip(" ,")
    x, s = _parse_number(s)
    s = s.lstrip(" ,")
    y, s = _parse_number(s)
    return (x, y), s


def svg_path_to_pen_commands(d: str, pen, sx: float, sy: float, dx: float, dy: float):
    """
    Replay an SVG path 'd' string onto a fontTools pen, applying scale+offset.
    sx/sy: scale; dx/dy: translation (in font units).
    Potrace SVG uses y-down coords starting from top-left of the bitmap.
    Font units use y-up.  We flip y: font_y = dy - (svg_y * sy).
    """

    def tx(x):
        return dx + x * sx

    def ty(y):
        return dy - y * sy  # flip y

    tokens = d.strip()
    i = 0
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    cmd = None
    in_subpath = False

    def advance():
        nonlocal tokens
        tokens = tokens.lstrip(" ,\n\r\t")

    def next_pair():
        nonlocal tokens
        advance()
        pair, tokens = _parse_coord_pair(tokens)
        return pair

    def next_num():
        nonlocal tokens
        advance()
        val, tokens = _parse_number(tokens)
        return val

    advance()
    while tokens:
        if tokens[0].isalpha():
            cmd = tokens[0]
            tokens = tokens[1:]
            advance()
        if cmd is None:
            break

        if cmd == "M":
            if in_subpath:
                pen.endPath()
            pt = next_pair()
            current = (tx(pt[0]), ty(pt[1]))
            start = current
            pen.moveTo(current)
            in_subpath = True
            cmd = "L"  # subsequent coords are lineTo
        elif cmd == "m":
            if in_subpath:
                pen.endPath()
            pt = next_pair()
            current = (current[0] + tx(pt[0]) - dx, current[1] + (-(pt[1] * sy)))
            # relative M: recalc properly
            current = (tx(0) + pt[0] * sx + (current[0] - tx(0)),
                       ty(0) - pt[1] * sy + (current[1] - ty(0)))
            # simpler: absolute position
            # Actually potrace always emits absolute M, so handle simply:
            # treat as absolute
            sx2, sy2 = sx, sy
            cx = dx + pt[0] * sx2
            cy = dy - pt[1] * sy2
            if in_subpath:
                pass  # already ended
            current = (cx, cy)
            start = current
            pen.moveTo(current)
            in_subpath = True
            cmd = "l"
        elif cmd == "L":
            pt = next_pair()
            current = (tx(pt[0]), ty(pt[1]))
            pen.lineTo(current)
        elif cmd == "l":
            pt = next_pair()
            current = (current[0] + pt[0] * sx, current[1] - pt[1] * sy)
            pen.lineTo(current)
        elif cmd == "C":
            p1 = next_pair()
            p2 = next_pair()
            p3 = next_pair()
            current = (tx(p3[0]), ty(p3[1]))
            pen.curveTo(
                (tx(p1[0]), ty(p1[1])),
                (tx(p2[0]), ty(p2[1])),
                current,
            )
        elif cmd == "c":
            p1 = next_pair()
            p2 = next_pair()
            p3 = next_pair()
            ox, oy = current
            pen.curveTo(
                (ox + p1[0] * sx, oy - p1[1] * sy),
                (ox + p2[0] * sx, oy - p2[1] * sy),
                (ox + p3[0] * sx, oy - p3[1] * sy),
            )
            current = (ox + p3[0] * sx, oy - p3[1] * sy)
        elif cmd in ("Z", "z"):
            if in_subpath:
                pen.closePath()
                in_subpath = False
            advance()
            cmd = None
            continue
        else:
            # Skip unknown command
            tokens = tokens[1:]
            continue

        advance()

    if in_subpath:
        pen.endPath()


# ---------------------------------------------------------------------------
# Font building
# ---------------------------------------------------------------------------

def build_font(glyph_data: list[dict], output_dir: Path):
    """
    glyph_data: list of {codepoint, name, svg_d, img_w, img_h, sx, sy, dx, dy, advance}
    Builds a CFF-based OTF (natively supports cubic Beziers from potrace), then:
      - saves as aarth.ttf  (OTF binary; .ttf extension for broad compatibility)
      - compresses to aarth.woff2
    """
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen

    glyph_names = [".notdef"] + [g["name"] for g in glyph_data]
    metrics = {".notdef": (500, 0)}
    for g in glyph_data:
        metrics[g["name"]] = (g["advance"], 0)

    # Build CFF charstrings
    charStrings = {}

    # .notdef — simple open rectangle
    pen = T2CharStringPen(500, None)
    pen.moveTo((50, 0))
    pen.lineTo((450, 0))
    pen.lineTo((450, 700))
    pen.lineTo((50, 700))
    pen.closePath()
    pen.moveTo((80, 30))
    pen.lineTo((80, 670))
    pen.lineTo((420, 670))
    pen.lineTo((420, 30))
    pen.closePath()
    charStrings[".notdef"] = pen.getCharString()

    for g in glyph_data:
        pen = T2CharStringPen(g["advance"], None)
        if g["svg_d"]:
            try:
                svg_path_to_pen_commands(
                    g["svg_d"], pen,
                    g["sx"], g["sy"], g["dx"], g["dy"],
                )
            except Exception as exc:
                print(f"  [warn] pen replay failed for {g['name']}: {exc}")
        charStrings[g["name"]] = pen.getCharString()

    fb = FontBuilder(EM, isTTF=False)
    fb.setupGlyphOrder(glyph_names)
    fb.setupHorizontalMetrics(metrics)
    fb.setupCharacterMap({g["codepoint"]: g["name"] for g in glyph_data})
    fb.setupCFF(
        psName="Aarth",
        fontInfo={
            "version": "1.0",
            "FullName": "Aarth Regular",
            "FamilyName": "Aarth",
            "Weight": "Regular",
        },
        charStringsDict=charStrings,
        privateDict={"defaultWidthX": 0, "nominalWidthX": 0},
    )
    fb.setupNameTable({"familyName": "Aarth", "styleName": "Regular"})
    fb.setupHorizontalHeader(ascent=ASCENDER, descent=DESCENDER)
    fb.setupHead(unitsPerEm=EM)
    fb.setupOS2(
        sTypoAscender=ASCENDER,
        sTypoDescender=DESCENDER,
        sTypoLineGap=0,
        usWinAscent=ASCENDER,
        usWinDescent=abs(DESCENDER),
        sxHeight=X_HEIGHT,
        sCapHeight=CAP_HEIGHT,
        fsType=0,
    )
    fb.setupPost()

    ttf_path = output_dir / "aarth.ttf"
    fb.font.save(str(ttf_path))
    print(f"[output] {ttf_path}")

    woff2_path = output_dir / "aarth.woff2"
    from fontTools.ttLib.woff2 import compress
    compress(str(ttf_path), str(woff2_path))
    print(f"[output] {woff2_path}")

    return ttf_path, woff2_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate Aarth webfont from Ath alphabet image")
    parser.add_argument("--image", default=None,
                        help="Path to PNG image or URL (default: download from Wikimedia)")
    parser.add_argument("--output-dir", default=".", help="Directory for output files")
    parser.add_argument("--debug", action="store_true", help="Save debug images")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Acquire image ---
    if args.image and not args.image.startswith("http"):
        image_path = Path(args.image)
    else:
        image_path = output_dir / "Ath_alphabet.png"
        url = args.image if args.image else SOURCE_URL
        if not image_path.exists():
            download_image(url, image_path)
        else:
            print(f"[info] using cached {image_path}")

    # --- 2. Pre-process ---
    print("[process] binarizing image …")
    binary = load_and_binarize(image_path)

    # --- 3. Detect glyph boxes ---
    print("[process] detecting glyphs …")
    boxes = find_glyph_boxes(binary)
    print(f"  found {len(boxes)} candidate glyph boxes")

    if args.debug:
        debug_img = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
        for x, y, w, h in boxes:
            cv2.rectangle(debug_img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.imwrite(str(output_dir / "debug_boxes.png"), debug_img)

    # Warn if too few/many glyphs found
    expected = len(GLYPH_CODEPOINTS)
    if len(boxes) < expected:
        print(f"  [warn] expected {expected} glyphs but only found {len(boxes)}. "
              "The font will be partial.")
    if len(boxes) > expected:
        print(f"  [info] more boxes than expected ({len(boxes)} > {expected}); "
              "using first {expected}.")
        boxes = boxes[:expected]

    # --- 4. Vectorise each glyph ---
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        glyph_data = []

        for idx, box in enumerate(boxes):
            if idx >= expected:
                break
            codepoint = GLYPH_CODEPOINTS[idx]
            name = GLYPH_NAMES[idx]
            print(f"  [{idx:02d}] {name} (U+{codepoint:04X}) …", end="", flush=True)

            crop = crop_glyph(binary, box)
            svg_d = glyph_to_svg_path(crop, tmp_dir, idx)

            if svg_d:
                print(" ok")
            else:
                print(" (no path)")

            # Compute scale/offset to fit glyph into EM square
            _, _, gw, gh = box
            # We want glyph height to fill ASCENDER - DESCENDER
            glyph_height_fu = ASCENDER - DESCENDER  # 1000
            sy = glyph_height_fu / gh if gh > 0 else 1.0
            sx = sy  # uniform scale
            advance = int(gw * sx) + 20

            glyph_data.append({
                "codepoint": codepoint,
                "name": name,
                "svg_d": svg_d,
                "img_w": gw,
                "img_h": gh,
                "sx": sx,
                "sy": sy,
                "dx": 10,           # left side bearing
                "dy": ASCENDER,     # baseline offset (y-flip origin)
                "advance": advance,
            })

        print("[build] assembling font …")
        build_font(glyph_data, output_dir)

    print("[done] aarth.ttf and aarth.woff2 created.")


if __name__ == "__main__":
    main()
