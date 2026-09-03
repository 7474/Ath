#!/usr/bin/env python3
"""
generate_aarth_font.py
======================
Generates aarth.ttf and aarth.woff2 from the Ath (Ath alphabet) raster image.

Pipeline:
  1. Download the source PNG from Wikimedia Commons (or use a local file).
  2. Pre-process with OpenCV: grayscale → threshold.
  3. Detect glyph bounding boxes via contour finding; merge disconnected
     overlines / umlauts into the parent glyph; sort top→bottom, left→right.
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
import re
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
    # Glyphs are dark (0) on white (255); invert so glyphs are white on black.
    # Do not apply morphological opening: 2×2 opening eats umlaut dots (~4×4).
    return cv2.bitwise_not(binary)


def _box_area(box) -> int:
    return box[2] * box[3]


def _union_box(a, b):
    x1 = min(a[0], b[0])
    y1 = min(a[1], b[1])
    x2 = max(a[0] + a[2], b[0] + b[2])
    y2 = max(a[1] + a[3], b[1] + b[3])
    return (x1, y1, x2 - x1, y2 - y1)


def _x_overlap(a, b) -> int:
    return max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))


def _is_diacritic_above(mark, base, max_gap_px: float) -> bool:
    """True if `mark` is a small accent sitting above `base` (overline / umlaut)."""
    mx, my, mw, mh = mark
    bx, by, bw, bh = base
    if _box_area(mark) >= _box_area(base) * 0.45:
        return False
    # Horizontal association: mark centre falls in the base, or the boxes overlap.
    mcx = mx + mw / 2
    if not (bx - 4 <= mcx <= bx + bw + 4 or _x_overlap(mark, base) >= 0.3 * min(mw, bw)):
        return False
    # Vertical: mark is above (or slightly overlapping) the base, with a small gap.
    gap = by - (my + mh)
    return gap <= max_gap_px


def merge_diacritic_boxes(boxes: list) -> list:
    """
    Union-find merge of disconnected accents into the glyph they belong to.

    Overlines and umlaut dots are separate contours from the letter body.
    Latin labels sit *below* their glyph and are larger relative to a mark,
    so they are left unmerged.
    """
    n = len(boxes)
    if n <= 1:
        return list(boxes)

    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(n):
        for j in range(i + 1, n):
            a, b = boxes[i], boxes[j]
            # The upper box is the one with smaller y.
            if a[1] <= b[1]:
                upper, lower = a, b
            else:
                upper, lower = b, a
            max_gap = max(10.0, 0.4 * lower[3])
            if _is_diacritic_above(upper, lower, max_gap):
                union(i, j)

    groups: dict[int, list] = {}
    for i, box in enumerate(boxes):
        groups.setdefault(find(i), []).append(box)

    merged = []
    for group in groups.values():
        acc = group[0]
        for extra in group[1:]:
            acc = _union_box(acc, extra)
        merged.append(acc)
    return merged


def group_boxes_into_rows(boxes: list) -> list[list]:
    """Cluster boxes into rows by y, then sort each row left-to-right."""
    if not boxes:
        return []
    heights = sorted(h for _, _, _, h in boxes)
    median_h = heights[len(heights) // 2]
    row_tol = median_h * 0.6
    ordered = sorted(boxes, key=lambda b: b[1])
    rows = []
    current = [ordered[0]]
    for box in ordered[1:]:
        if abs(box[1] - current[-1][1]) < row_tol:
            current.append(box)
        else:
            rows.append(sorted(current, key=lambda b: b[0]))
            current = [box]
    rows.append(sorted(current, key=lambda b: b[0]))
    return rows


def select_alphabet_grid(boxes: list, expected: int = 28) -> list:
    """
    Keep 7-column rows of letter-sized boxes.

    The source PNG has a 6-item header ('Ath' + three sample glyphs) above a
    4×7 alphabet grid, plus small Latin labels under each glyph. After
    diacritic merging, letter bodies are tall (~25px) while labels are short.
    """
    letter_boxes = [b for b in boxes if b[3] >= 18]
    rows = group_boxes_into_rows(letter_boxes)
    grid_rows = [row for row in rows if len(row) == 7]
    result = [box for row in grid_rows for box in row]
    if len(result) == expected:
        return result
    # Fallback: drop a short header row if present.
    if rows and len(rows[0]) != 7:
        rest = [box for row in rows[1:] for box in row]
        if len(rest) == expected:
            return rest
    return result


def find_glyph_boxes(binary: np.ndarray, min_area: int = 8):
    """
    Find bounding boxes of the 28 alphabet glyphs, including disconnected
    overlines and umlaut dots.

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

    boxes = merge_diacritic_boxes(boxes)
    return select_alphabet_grid(boxes, expected=len(GLYPH_CODEPOINTS))


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

    OpenCV stores glyphs as white-on-black; potrace traces black pixels, so the
    crop is inverted first. `--unit 1` keeps path coordinates in pixels, with
    origin at the bottom-left and y pointing up (potrace's group transform).
    `--turdsize 0` preserves umlaut dots.
    """
    pbm_path = tmp_dir / f"glyph_{idx:03d}.pbm"
    svg_path = tmp_dir / f"glyph_{idx:03d}.svg"

    ink_black = cv2.bitwise_not(glyph_img)
    pil = Image.fromarray(ink_black).convert("1")
    pil.save(str(pbm_path))

    try:
        subprocess.run(
            [
                "potrace", "--svg", "--unit", "1", "--turdsize", "0",
                "--output", str(svg_path), str(pbm_path),
            ],
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
    """Extract and join 'd' attributes from all <path> elements in the SVG."""
    try:
        tree = ET.parse(str(svg_file))
        root = tree.getroot()
        paths = root.findall(".//{http://www.w3.org/2000/svg}path")
        ds = [p.get("d", "") for p in paths if p.get("d")]
        if ds:
            return " ".join(ds)
    except ET.ParseError:
        pass
    return None


# ---------------------------------------------------------------------------
# SVG path → fontTools pen
# ---------------------------------------------------------------------------

_PATH_TOKEN_RE = re.compile(
    r"[MmZzLlHhVvCcSsQqTtAa]|[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
)


def svg_path_to_pen_commands(d: str, pen, sx: float, sy: float, dx: float, dy: float):
    """
    Replay an SVG path 'd' string onto a fontTools pen, applying scale+offset.

    Potrace `--unit 1` path coordinates are in pixels, origin at the bitmap
    bottom-left, y-up — the same orientation as font units. No y-flip.
    Relative `m` starts a new subpath (overline / umlaut dots).
    """

    def tx(x):
        return dx + x * sx

    def ty(y):
        return dy + y * sy

    tokens = _PATH_TOKEN_RE.findall(d)
    i = 0
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    cmd = None
    in_subpath = False

    def read_pair():
        nonlocal i
        x = float(tokens[i])
        y = float(tokens[i + 1])
        i += 2
        return x, y

    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            i += 1
            if cmd in ("Z", "z"):
                if in_subpath:
                    pen.closePath()
                    in_subpath = False
                    current = start
                cmd = None
                continue

        if cmd is None:
            break

        if cmd == "M":
            if in_subpath:
                pen.endPath()
            px, py = read_pair()
            current = (tx(px), ty(py))
            start = current
            pen.moveTo(current)
            in_subpath = True
            cmd = "L"
        elif cmd == "m":
            if in_subpath:
                pen.endPath()
            px, py = read_pair()
            current = (current[0] + px * sx, current[1] + py * sy)
            start = current
            pen.moveTo(current)
            in_subpath = True
            cmd = "l"
        elif cmd == "L":
            px, py = read_pair()
            current = (tx(px), ty(py))
            pen.lineTo(current)
        elif cmd == "l":
            px, py = read_pair()
            current = (current[0] + px * sx, current[1] + py * sy)
            pen.lineTo(current)
        elif cmd == "H":
            px = float(tokens[i]); i += 1
            current = (tx(px), current[1])
            pen.lineTo(current)
        elif cmd == "h":
            px = float(tokens[i]); i += 1
            current = (current[0] + px * sx, current[1])
            pen.lineTo(current)
        elif cmd == "V":
            py = float(tokens[i]); i += 1
            current = (current[0], ty(py))
            pen.lineTo(current)
        elif cmd == "v":
            py = float(tokens[i]); i += 1
            current = (current[0], current[1] + py * sy)
            pen.lineTo(current)
        elif cmd == "C":
            x1, y1 = read_pair()
            x2, y2 = read_pair()
            x3, y3 = read_pair()
            current = (tx(x3), ty(y3))
            pen.curveTo((tx(x1), ty(y1)), (tx(x2), ty(y2)), current)
        elif cmd == "c":
            x1, y1 = read_pair()
            x2, y2 = read_pair()
            x3, y3 = read_pair()
            ox, oy = current
            current = (ox + x3 * sx, oy + y3 * sy)
            pen.curveTo(
                (ox + x1 * sx, oy + y1 * sy),
                (ox + x2 * sx, oy + y2 * sy),
                current,
            )
        else:
            # Unsupported command: skip its letter; numbers are consumed by
            # the next recognised command or will trip the alpha check.
            if tok.isalpha():
                continue
            i += 1
            continue

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
    fb.setupHorizontalHeader(ascent=EM, descent=DESCENDER)
    fb.setupHead(unitsPerEm=EM)
    fb.setupOS2(
        sTypoAscender=ASCENDER,
        sTypoDescender=DESCENDER,
        sTypoLineGap=0,
        usWinAscent=EM,          # extra room for overlines / umlauts + crop padding
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
        for i, (x, y, w, h) in enumerate(boxes):
            cv2.rectangle(debug_img, (x, y), (x + w, y + h), (0, 255, 0), 1)
            label = GLYPH_NAMES[i] if i < len(GLYPH_NAMES) else str(i)
            cv2.putText(
                debug_img, label, (x, max(12, y - 2)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 180, 255), 1, cv2.LINE_AA,
            )
        cv2.imwrite(str(output_dir / "debug_boxes.png"), debug_img)

    # Warn if too few/many glyphs found
    expected = len(GLYPH_CODEPOINTS)
    if len(boxes) != expected:
        print(f"  [warn] expected {expected} glyphs but found {len(boxes)}.")
        if len(boxes) < expected:
            print("  The font will be partial.")
        else:
            print(f"  using first {expected}.")
            boxes = boxes[:expected]

    # Uniform scale so letter bodies stay consistent; diacritics occupy extra
    # height above the body instead of shrinking the whole glyph to fit.
    CROP_PAD = 4
    max_h = max((h for _, _, _, h in boxes), default=1)
    uniform_sy = (ASCENDER - DESCENDER) / max_h if max_h else 1.0

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

            x, y, gw, gh = box
            crop = crop_glyph(binary, box, padding=CROP_PAD)
            svg_d = glyph_to_svg_path(crop, tmp_dir, idx)

            if svg_d:
                print(" ok")
            else:
                print(" (no path)")

            sx = sy = uniform_sy
            crop_h = crop.shape[0]
            crop_x1 = max(0, x - CROP_PAD)
            crop_y1 = max(0, y - CROP_PAD)
            # Potrace --unit 1: origin at crop bottom-left, y-up, pixel units.
            box_bottom_in_crop = (y + gh) - crop_y1          # from top of crop
            box_left_in_crop = x - crop_x1
            y_path_box_bottom = crop_h - box_bottom_in_crop  # from bottom (path y)
            dx = 10 - box_left_in_crop * sx
            dy = DESCENDER - y_path_box_bottom * sy
            advance = int(gw * sx) + 20

            glyph_data.append({
                "codepoint": codepoint,
                "name": name,
                "svg_d": svg_d,
                "img_w": gw,
                "img_h": gh,
                "sx": sx,
                "sy": sy,
                "dx": dx,
                "dy": dy,
                "advance": advance,
            })

        print("[build] assembling font …")
        build_font(glyph_data, output_dir)

    print("[done] aarth.ttf and aarth.woff2 created.")


if __name__ == "__main__":
    main()
