#!/usr/bin/env python3
"""
generate_aarth_font.py
======================
Generates aarth.ttf and aarth.woff2 from Ath raster images (alphabet ± digits).

Pipeline:
  1. Download the source PNG from Wikimedia Commons (or use a local file).
  2. Pre-process with OpenCV: grayscale → threshold.
  3. Detect glyph boxes; merge disconnected overlines / umlauts into the
     parent glyph; keep the 4×7 alphabet grid (drop the header) and, when
     present, the numeral cells 0–9 from the same sheet or ``--digits-image``.
  4. For each glyph: split ink into components, 8× silhouette-blur, potrace.
  5. Build a TTF font via fontTools (TTFont + pens), then compress to WOFF2.

Usage:
    python generate_aarth_font.py [--image PATH_OR_URL]
    python generate_aarth_font.py --write-template templates/

Requirements (install once):
    pip install opencv-python-headless pillow fonttools brotli
    sudo apt-get install potrace          # Debian/Ubuntu
    # macOS:  brew install potrace
    # Windows: download from http://potrace.sourceforge.net/
"""

import argparse
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
# Optional numerals 0–9 follow the alphabet on the same sheet (or a second
# raster passed as --digits-image) and map to ASCII digits.
#
# Row 0: a  i  u  é  o  e  c      → a  i  u  U+00E9  o  e  c
# Row 1: s  t  l  n  h  p  f      → s  t  l  n  h  p  f
# Row 2: m  ï  ai y  œ  r  ü      → m  U+00EF  U+0061U+0069→'A'  y  U+0153  r  U+00FC
# Row 3: au ÿ  eu g  z  d  b      → U+0061U+0075→'I'  U+00FF  U+0065U+0075→'E'  g  z  d  b
# Row 4: 0  1  2  3  4  5  6      → 0 1 2 3 4 5 6
# Row 5: 7  8  9                  → 7 8 9
#
# For simplicity the digraphs / special vowels get mapped to uppercase ASCII
# placeholders so they can be used in CSS/HTML if needed.
# ---------------------------------------------------------------------------

ALPHABET_COLS = 7
ALPHABET_ROWS = 4
DIGIT_COUNT = 10

ALPHABET_CODEPOINTS = [
    # row 0
    ord('a'), ord('i'), ord('u'), 0x00E9, ord('o'), ord('e'), ord('c'),
    # row 1
    ord('s'), ord('t'), ord('l'), ord('n'), ord('h'), ord('p'), ord('f'),
    # row 2
    ord('m'), 0x00EF, ord('A'), ord('y'), 0x0153, ord('r'), 0x00FC,
    # row 3
    ord('I'), 0x00FF, ord('E'), ord('g'), ord('z'), ord('d'), ord('b'),
]

ALPHABET_NAMES = [
    'a', 'i', 'u', 'eacute', 'o', 'e', 'c',
    's', 't', 'l', 'n', 'h', 'p', 'f',
    'm', 'idieresis', 'ai', 'y', 'oe', 'r', 'udieresis',
    'au', 'ydieresis', 'eu', 'g', 'z', 'd', 'b',
]

# Labels printed under each cell on the input template (typing keys).
ALPHABET_LABELS = [
    'a', 'i', 'u', 'é', 'o', 'e', 'c',
    's', 't', 'l', 'n', 'h', 'p', 'f',
    'm', 'ï', 'ai', 'y', 'œ', 'r', 'ü',
    'au', 'ÿ', 'eu', 'g', 'z', 'd', 'b',
]

DIGIT_CODEPOINTS = [ord(c) for c in '0123456789']
DIGIT_NAMES = [
    'zero', 'one', 'two', 'three', 'four',
    'five', 'six', 'seven', 'eight', 'nine',
]
DIGIT_LABELS = list('0123456789')

# Full inventory in template order (alphabet, then digits).
GLYPH_CODEPOINTS = ALPHABET_CODEPOINTS + DIGIT_CODEPOINTS
GLYPH_NAMES = ALPHABET_NAMES + DIGIT_NAMES
GLYPH_LABELS = ALPHABET_LABELS + DIGIT_LABELS

# Row-major cell layout for the fill-in source template.
GLYPH_LAYOUT = [
    ALPHABET_LABELS[0:7],
    ALPHABET_LABELS[7:14],
    ALPHABET_LABELS[14:21],
    ALPHABET_LABELS[21:28],
    DIGIT_LABELS[0:7],
    DIGIT_LABELS[7:10],
]

SOURCE_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/2/23/Ath_%28alphabet%29.png"
)

EM = 1000          # units per em
ASCENDER = 800
DESCENDER = -200
CAP_HEIGHT = 700   # target height every glyph is scaled to
X_HEIGHT = 500
GLYPH_LSB = 40     # left/right side bearing in font units

# Source PNG is ~20–30px with an 8-level gray ramp. Otsu (box detection)
# makes a thin dark core; potrace on that greymap traces each stroke as a
# ribbon whose Béziers sag and leave a white sliver (especially Ath 'h').
#
# Instead: take a *silhouette* of each ink component, upscale, blur so the
# 0.5 isosurface is a smooth outer contour, then potrace. One filled outline
# cannot pinch hollow. Components (umlaut dots, overlines) are assigned by
# nearest Otsu seed so blur cannot melt them into the letter body.
SOURCE_INK_LEVEL = 0.6   # include anti-aliased fringe as ink
TRACE_SCALE = 8
# Blur the *native* signed-distance field (stair period = 1px), then
# cubic-upsample so potrace sees a dense, already-smooth 0.5 isosurface.
TRACE_SDF_SIGMA = 1.2
TRACE_BLACKLEVEL = 0.5   # midpoint of the SDF ramp (0-level of the field)
# Box detection ignores light-gray template titles/guides (blank sheets
# have no black glyphs, so Otsu would otherwise promote captions to ink).
DETECT_INK_MAX = 110


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def download_image(url: str, dest: Path) -> None:
    print(f"[download] {url} → {dest}")
    headers = {"User-Agent": "AarthFontGenerator/1.0 (educational project)"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def load_grayscale(image_path: Path) -> np.ndarray:
    """Load the source PNG as a single-channel grayscale image."""
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    return img


def binarize(gray: np.ndarray) -> np.ndarray:
    """Return a binary (0/255) image where glyphs are WHITE on BLACK."""
    # The source image is black ink on white paper → invert after threshold
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Glyphs are dark (0) on white (255); invert so glyphs are white on black
    binary = cv2.bitwise_not(binary)
    # Drop light-gray template captions/guides. On a blank sheet Otsu would
    # treat those as the only "ink".
    binary = np.where(gray < DETECT_INK_MAX, binary, 0).astype(np.uint8)
    # Do not apply morphological opening: 2×2 opening eats umlaut dots (~4×4).
    return binary


def load_and_binarize(image_path: Path) -> np.ndarray:
    """Return a binary (0/255) OpenCV image where glyphs are WHITE on BLACK."""
    return binarize(load_grayscale(image_path))


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
    mcx = mx + mw / 2
    if not (bx - 4 <= mcx <= bx + bw + 4 or _x_overlap(mark, base) >= 0.3 * min(mw, bw)):
        return False
    gap = by - (my + mh)
    return gap <= max_gap_px


def merge_diacritic_boxes(boxes: list) -> list:
    """
    Union-find merge of disconnected accents into the glyph they belong to.

    Overlines and umlaut dots are separate contours from the letter body.
    Latin labels sit *below* their glyph and are left unmerged.
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


def _letter_sized_boxes(boxes: list) -> list:
    """Drop short Latin labels; keep letter-sized (and header-sample) boxes.

    Wikipedia source letters are ~25px with ~8px labels. A high-res fill-in
    template has much taller bodies, so the cutoff scales with the tallest box.
    """
    if not boxes:
        return []
    max_h = max(b[3] for b in boxes)
    threshold = max(18, int(max_h * 0.40))
    return [b for b in boxes if b[3] >= threshold]


def _is_grid_content_row(row: list) -> bool:
    n = len(row)
    return n in (3, ALPHABET_COLS, DIGIT_COUNT)


def collect_contour_boxes(binary: np.ndarray, min_area: int = 8) -> list:
    """Bounding boxes of ink blobs, ignoring hairline noise and page-wide rules."""
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w * h < min_area:
            continue
        if w > binary.shape[1] * 0.8:
            continue
        boxes.append((x, y, w, h))
    return boxes


def select_alphabet_grid(boxes: list, expected: int = 28) -> list:
    """Backward-compatible wrapper: alphabet cells only (no numerals)."""
    alphabet, _digits = select_glyph_grid(boxes)
    if len(alphabet) == expected:
        return alphabet
    return alphabet


def select_glyph_grid(boxes: list) -> tuple[list, list]:
    """
    Split letter-sized boxes into the 4×7 alphabet and optional numerals.

    The source PNG has a short header above a 4×7 alphabet grid, plus small
    Latin labels under each glyph. After diacritic merging, letter bodies are
    tall while labels are short. Extra rows after the alphabet are digits:
    either one 10-wide row, or 7 + 3 (0–6 then 7–9), matching the template.
    """
    letter_boxes = _letter_sized_boxes(boxes)
    rows = group_boxes_into_rows(letter_boxes)
    if rows and not _is_grid_content_row(rows[0]):
        rows = rows[1:]
    if not rows:
        return [], []

    seven_rows = [row for row in rows if len(row) == ALPHABET_COLS]
    if len(seven_rows) >= ALPHABET_ROWS:
        alphabet: list = []
        last_alpha_i = -1
        taken = 0
        for i, row in enumerate(rows):
            if taken < ALPHABET_ROWS and len(row) == ALPHABET_COLS:
                alphabet.extend(row)
                taken += 1
                last_alpha_i = i
                if taken == ALPHABET_ROWS:
                    break
        digits: list = []
        for row in rows[last_alpha_i + 1:]:
            digits.extend(row)
        return alphabet, digits[:DIGIT_COUNT]

    # Digits-only sheet: one row of 10, or 7+3 (0–6 then 7–9).
    if _looks_like_digits_only(rows):
        return [], [box for row in rows for box in row][:DIGIT_COUNT]

    # Partial alphabet (no complete 4×7 and not a numeral sheet).
    return [box for row in rows for box in row], []


def _looks_like_digits_only(rows: list) -> bool:
    flat_n = sum(len(row) for row in rows)
    if flat_n != DIGIT_COUNT:
        return False
    if len(rows) == 1 and len(rows[0]) == DIGIT_COUNT:
        return True
    if len(rows) == 2 and len(rows[0]) == ALPHABET_COLS and len(rows[1]) == 3:
        return True
    return False


def find_glyph_boxes(binary: np.ndarray, min_area: int = 8):
    """
    Find bounding boxes of the 28 alphabet glyphs (and optional 0–9), including
    disconnected overlines and umlaut dots.

    Returns list of (x, y, w, h) sorted top-to-bottom, left-to-right by row.
    Alphabet cells come first; numeral cells follow when present.
    """
    alphabet, digits = find_alphabet_and_digit_boxes(binary, min_area=min_area)
    return alphabet + digits


def find_alphabet_and_digit_boxes(binary: np.ndarray, min_area: int = 8) -> tuple[list, list]:
    """Return ``(alphabet_boxes, digit_boxes)`` from one raster sheet."""
    boxes = collect_contour_boxes(binary, min_area=min_area)
    if not boxes:
        return [], []
    boxes = merge_diacritic_boxes(boxes)
    return select_glyph_grid(boxes)


def find_digit_boxes(binary: np.ndarray, min_area: int = 8) -> list:
    """Find up to 10 numeral boxes on a digits-only or combined raster."""
    alphabet, digits = find_alphabet_and_digit_boxes(binary, min_area=min_area)
    if digits:
        return digits
    if len(alphabet) == DIGIT_COUNT:
        return alphabet
    return []


def crop_glyph(binary: np.ndarray, box, padding: int = 4) -> np.ndarray:
    x, y, w, h = box
    img_h, img_w = binary.shape
    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(img_w, x + w + padding)
    y2 = min(img_h, y + h + padding)
    return binary[y1:y2, x1:x2]


def _nearest_seed_labels(loose: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    """Assign every ``loose`` ink pixel to the nearest connected seed.

    ``seeds`` is a labeled image (0 = background). Overlapping gray fringe
    between an umlaut and its letter body goes to whichever core is closer,
    so a later blur cannot weld diacritics onto the stem.
    """
    n = int(seeds.max())
    if n <= 0:
        return seeds
    assigned = np.zeros(seeds.shape, dtype=np.int32)
    min_dist = np.full(seeds.shape, np.inf, dtype=np.float32)
    for i in range(1, n + 1):
        seed = (seeds == i).astype(np.uint8)
        dist = cv2.distanceTransform(1 - seed, cv2.DIST_L2, 5)
        closer = loose & (dist < min_dist)
        assigned[closer] = i
        min_dist[closer] = dist[closer]
        assigned[seed.astype(bool)] = i
    return assigned


def split_ink_components(gray_crop: np.ndarray, otsu_crop: np.ndarray) -> list[np.ndarray]:
    """
    One ink mask (255 = ink) per disconnected mark in the crop.

    Seeds come from the Otsu detection mask (sharp cores, separate dots).
    Each seed claims nearby anti-aliased fringe (``SOURCE_INK_LEVEL``).
    """
    loose = gray_crop < SOURCE_INK_LEVEL * 255
    strict = otsu_crop > 0
    n_labels, seeds = cv2.connectedComponents(strict.astype(np.uint8), connectivity=8)
    labels = _nearest_seed_labels(loose, seeds)
    masks = []
    for i in range(1, n_labels):
        masks.append(np.where(labels == i, 255, 0).astype(np.uint8))
    return masks


def prepare_component_for_trace(ink_mask: np.ndarray) -> np.ndarray:
    """Smooth a component's silhouette via SDF, then 8× for potrace."""
    ink = np.where(ink_mask > 0, 255, 0).astype(np.uint8)
    dist_in = cv2.distanceTransform(ink, cv2.DIST_L2, 5)
    dist_out = cv2.distanceTransform(cv2.bitwise_not(ink), cv2.DIST_L2, 5)
    sdf = dist_in.astype(np.float32) - dist_out.astype(np.float32)
    k = int(max(3, round(TRACE_SDF_SIGMA * 6))) | 1
    sdf = cv2.GaussianBlur(sdf, (k, k), sigmaX=TRACE_SDF_SIGMA)
    h, w = sdf.shape
    up = cv2.resize(
        sdf,
        (w * TRACE_SCALE, h * TRACE_SCALE),
        interpolation=cv2.INTER_CUBIC,
    )
    # Map SDF 0 → 127.5 so --blacklevel 0.5 follows the smoothed outline.
    # ±4 px covers the ramp; interior stays dark, exterior paper.
    gray = np.clip(127.5 - up * (127.5 / 4.0), 0, 255).astype(np.uint8)
    return gray


def prepare_glyph_for_trace(
    gray: np.ndarray, binary: np.ndarray, box, padding: int = 4,
) -> list[np.ndarray]:
    """Return one blurred silhouette greymap per ink component of ``box``."""
    gray_crop = crop_glyph(gray, box, padding)
    otsu_crop = crop_glyph(binary, box, padding)
    masks = split_ink_components(gray_crop, otsu_crop)
    return [prepare_component_for_trace(mask) for mask in masks]


def _potrace_pgm(glyph_img: np.ndarray, pgm_path: Path, svg_path: Path) -> str | None:
    Image.fromarray(glyph_img).convert("L").save(str(pgm_path))
    try:
        subprocess.run(
            [
                "potrace", "--svg", "--turdsize", "0",
                "--blacklevel", str(TRACE_BLACKLEVEL),
                "--output", str(svg_path), str(pgm_path),
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"  [warn] potrace failed: {exc.stderr.decode()}")
        return None
    except FileNotFoundError:
        print("  [error] potrace not found. Install it with: sudo apt-get install potrace")
        sys.exit(1)
    return parse_svg_path(svg_path)


def glyph_to_svg_path(glyph_img: np.ndarray, tmp_dir: Path, idx: int) -> str | None:
    """
    Save a greymap as PGM, run potrace, return the SVG path 'd' string.
    Potrace produces a path with (0,0) at bottom-left in PostScript coords.
    """
    return _potrace_pgm(
        glyph_img,
        tmp_dir / f"glyph_{idx:03d}.pgm",
        tmp_dir / f"glyph_{idx:03d}.svg",
    )


def trace_glyph(gray: np.ndarray, binary: np.ndarray, box, tmp_dir: Path, idx: int) -> str | None:
    """Trace every ink component of a glyph and concatenate the path data."""
    parts = []
    for c_idx, canvas in enumerate(prepare_glyph_for_trace(gray, binary, box)):
        d = _potrace_pgm(
            canvas,
            tmp_dir / f"glyph_{idx:03d}_{c_idx:02d}.pgm",
            tmp_dir / f"glyph_{idx:03d}_{c_idx:02d}.svg",
        )
        if d:
            parts.append(d)
    return " ".join(parts) or None


def parse_svg_path(svg_file: Path) -> str | None:
    """
    Return the concatenated 'd' data of *every* <path> in the SVG.

    Potrace emits one <path> per outline and additional <path> elements for
    counters/holes (e.g. the bowl of 'a'), so we must keep them all — using
    only the first path drops the holes. Each 'd' string starts with its own
    absolute 'M', so simple concatenation yields a valid multi-subpath.

    Coordinates are left in potrace's raw path space (10 units per source
    pixel, y-up); the potrace <g transform> is intentionally *not* baked in
    here because build_font() rescales each glyph from its own bounding box.
    """
    try:
        tree = ET.parse(str(svg_file))
        root = tree.getroot()
        ns = {"svg": "http://www.w3.org/2000/svg"}
        paths = root.findall(".//svg:path", ns)
        if not paths:
            paths = root.findall(".//{http://www.w3.org/2000/svg}path")
        ds = [p.get("d", "").strip() for p in paths if p.get("d")]
        if ds:
            return " ".join(ds)
    except ET.ParseError:
        pass
    return None


# ---------------------------------------------------------------------------
# SVG path → fontTools pen
# ---------------------------------------------------------------------------

def layout_glyph(svg_d: str, target_height: float, lsb: float, scale: float | None = None):
    """
    Fit a potrace SVG path to the font's em, without drawing yet.

    Potrace path coordinates are y-up and 10x the source-pixel size (the SVG's
    own ``<g transform="translate(0,H) scale(0.1,-0.1)">`` compensates for that
    when rendered). A single uniform positive scale keeps the aspect ratio and
    preserves contour orientation, so counters/holes fill correctly.

    When ``scale`` is omitted the glyph is stretched to ``target_height``.
    Passing a shared ``scale`` (from the tallest outline) keeps letter bodies
    consistent so overlines/umlauts sit above the cap rather than shrinking
    the whole glyph.

    Returns ``(recording_pen, affine, advance)`` — replaying ``recording_pen``
    through ``TransformPen(target_pen, affine)`` places the glyph on the
    baseline with ``lsb`` units of left side bearing — or ``None`` when the
    path is empty/degenerate.
    """
    from fontTools.svgLib.path import parse_path
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.boundsPen import ControlBoundsPen

    rec = RecordingPen()
    parse_path(svg_d, rec)

    bounds = ControlBoundsPen(None)
    rec.replay(bounds)
    if bounds.bounds is None:
        return None
    x_min, y_min, x_max, y_max = bounds.bounds
    raw_h = y_max - y_min
    raw_w = x_max - x_min
    if raw_h <= 0:
        return None

    if scale is None:
        scale = target_height / raw_h
    # font_x = scale*x + (lsb - scale*x_min);  font_y = scale*y - scale*y_min
    affine = (scale, 0.0, 0.0, scale, lsb - scale * x_min, -scale * y_min)
    advance = int(round(raw_w * scale)) + 2 * int(lsb)
    return rec, affine, advance


# ---------------------------------------------------------------------------
# Font building
# ---------------------------------------------------------------------------

def build_font(glyph_data: list[dict], output_dir: Path):
    """
    glyph_data: list of {codepoint, name, svg_d}
    Builds a CFF-based OTF (natively supports cubic Beziers from potrace), then:
      - saves as aarth.ttf  (OTF binary; .ttf extension for broad compatibility)
      - compresses to aarth.woff2

    Each glyph is scaled with a *shared* factor taken from the tallest outline
    (typically a letter plus overline/umlaut) so bodies stay the same size and
    diacritics sit above the cap height instead of shrinking the whole glyph.
    """
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.svgLib.path import parse_path
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.boundsPen import ControlBoundsPen

    glyph_names = [".notdef"] + [g["name"] for g in glyph_data]

    # Measure every outline so we can pick one scale for the whole font.
    max_raw_h = 0.0
    for g in glyph_data:
        if not g["svg_d"]:
            continue
        rec = RecordingPen()
        try:
            parse_path(g["svg_d"], rec)
        except Exception:
            continue
        bounds = ControlBoundsPen(None)
        rec.replay(bounds)
        if bounds.bounds:
            max_raw_h = max(max_raw_h, bounds.bounds[3] - bounds.bounds[1])
    shared_scale = (CAP_HEIGHT / max_raw_h) if max_raw_h > 0 else None

    # Build CFF charstrings, capturing each glyph's advance width as we draw it.
    charStrings = {}
    metrics = {".notdef": (500, 0)}
    default_advance = int(CAP_HEIGHT * 0.6) + 2 * GLYPH_LSB

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
        layout = None
        if g["svg_d"]:
            try:
                layout = layout_glyph(g["svg_d"], CAP_HEIGHT, GLYPH_LSB, scale=shared_scale)
            except Exception as exc:
                print(f"  [warn] layout failed for {g['name']}: {exc}")

        advance = layout[2] if layout else default_advance
        pen = T2CharStringPen(advance, None)
        if layout:
            rec, affine, _ = layout
            rec.replay(TransformPen(pen, affine))
        charStrings[g["name"]] = pen.getCharString()
        metrics[g["name"]] = (advance, 0)

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
# Input template (alphabet 4×7 + numerals 0–9)
# ---------------------------------------------------------------------------

_TEMPLATE_SANS = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
_TEMPLATE_SANS_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
_TEMPLATE_JP = Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc")

CELL_W = 128
CELL_H = 168
GLYPH_AREA_H = 118
GAP_X = 20
GAP_Y = 28
MARGIN_X = 56
MARGIN_TOP = 118
MARGIN_BOTTOM = 72
GUIDE_FILL = (252, 252, 250)
GUIDE_OUTLINE = (236, 236, 230)
LABEL_FILL = (168, 168, 168)
TITLE_FILL = (168, 168, 168)
NOTE_FILL = (176, 176, 176)


def _try_font(path: Path, size: int):
    from PIL import ImageFont
    if path.is_file():
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def _centered_text(draw, xy, text, font, fill):
    x, y, w, h = xy
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        (x + (w - tw) / 2 - bbox[0], y + (h - th) / 2 - bbox[1]),
        text, font=font, fill=fill,
    )


def _draw_corner_ticks(draw, box_xy, tick: int = 14) -> None:
    """Light corner marks that stay below the Otsu ink threshold."""
    x0, y0, x1, y1 = box_xy
    draw.line((x0, y0, x0 + tick, y0), fill=GUIDE_OUTLINE, width=2)
    draw.line((x0, y0, x0, y0 + tick), fill=GUIDE_OUTLINE, width=2)
    draw.line((x1 - tick, y0, x1, y0), fill=GUIDE_OUTLINE, width=2)
    draw.line((x1, y0, x1, y0 + tick), fill=GUIDE_OUTLINE, width=2)
    draw.line((x0, y1 - tick, x0, y1), fill=GUIDE_OUTLINE, width=2)
    draw.line((x0, y1, x0 + tick, y1), fill=GUIDE_OUTLINE, width=2)
    draw.line((x1, y1 - tick, x1, y1), fill=GUIDE_OUTLINE, width=2)
    draw.line((x1 - tick, y1, x1, y1), fill=GUIDE_OUTLINE, width=2)


def _paste_glyph_in_cell(canvas, src_rgb: np.ndarray, box, cell_xy, padding: int = 6):
    """Paste a cropped source glyph, scaled to fit the cell's glyph area."""
    x, y, w, h = box
    img_h, img_w = src_rgb.shape[:2]
    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(img_w, x + w + padding)
    y2 = min(img_h, y + h + padding)
    crop = src_rgb[y1:y2, x1:x2]
    if crop.size == 0:
        return
    crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB) if crop.ndim == 3 else crop
    glyph = Image.fromarray(crop_rgb)
    inner_w = CELL_W - 16
    inner_h = GLYPH_AREA_H - 16
    gw, gh = glyph.size
    scale = min(inner_w / gw, inner_h / gh)
    new_size = (max(1, int(gw * scale)), max(1, int(gh * scale)))
    glyph = glyph.resize(new_size, Image.Resampling.LANCZOS)
    cx, cy = cell_xy
    px = cx + (CELL_W - new_size[0]) // 2
    py = cy + (GLYPH_AREA_H - new_size[1]) // 2
    canvas.paste(glyph, (px, py))


def write_source_template(
    dest: Path,
    alphabet_image: Path | None = None,
    blank: bool = False,
) -> Path:
    """
    Write a labeled raster template: 4×7 alphabet cells + 0–9 numeral cells.

    Reading sheet (``blank=False``): when ``alphabet_image`` is given, detected
    Ath letters are copied into the alphabet cells so the sheet can be used as
    ``--image`` immediately; numeral cells stay empty.

    Blank sheet (``blank=True``): every cell is empty (corner ticks only) so
    all 38 glyphs can be drawn from scratch.
    """
    from PIL import ImageDraw

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    n_rows = len(GLYPH_LAYOUT)
    n_cols = ALPHABET_COLS
    width = MARGIN_X * 2 + n_cols * CELL_W + (n_cols - 1) * GAP_X
    height = MARGIN_TOP + n_rows * CELL_H + (n_rows - 1) * GAP_Y + MARGIN_BOTTOM
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    title_font = _try_font(_TEMPLATE_SANS_BOLD, 28)
    jp_font = _try_font(_TEMPLATE_JP, 16)
    note_font = _try_font(_TEMPLATE_SANS, 14)
    label_font = _try_font(_TEMPLATE_SANS, 18)
    small_font = _try_font(_TEMPLATE_SANS, 13)
    caption_font = jp_font if _TEMPLATE_JP.is_file() else note_font

    if blank:
        draw.text((MARGIN_X, 28), "Aarth blank template", font=title_font, fill=TITLE_FILL)
        draw.text(
            (MARGIN_X, 64),
            "全グリフ未記入  字母 4×7 ＋ 数字 0–9   /   Draw every glyph. Labels stay below.",
            font=caption_font,
            fill=NOTE_FILL,
        )
    else:
        draw.text((MARGIN_X, 28), "Aarth source template", font=title_font, fill=TITLE_FILL)
        draw.text(
            (MARGIN_X, 64),
            "読み取り用  字母埋め込み ＋ 数字空欄   /   Draw numerals in the empty cells.",
            font=caption_font,
            fill=NOTE_FILL,
        )

    alphabet_boxes = []
    src_bgr = None
    if (
        not blank
        and alphabet_image is not None
        and Path(alphabet_image).is_file()
    ):
        src_bgr = cv2.imread(str(alphabet_image), cv2.IMREAD_COLOR)
        gray = load_grayscale(Path(alphabet_image))
        binary = binarize(gray)
        alphabet_boxes, _digits = find_alphabet_and_digit_boxes(binary)

    slot = 0
    for r, row_labels in enumerate(GLYPH_LAYOUT):
        for c, label in enumerate(row_labels):
            cx = MARGIN_X + c * (CELL_W + GAP_X)
            cy = MARGIN_TOP + r * (CELL_H + GAP_Y)
            is_digit = r >= ALPHABET_ROWS
            box_xy = (cx, cy, cx + CELL_W, cy + GLYPH_AREA_H)
            empty = blank or is_digit
            if empty:
                # Corner ticks only — a closed grey box would survive Otsu as a
                # fake "glyph" when the cell has no ink yet.
                _draw_corner_ticks(draw, box_xy)
            else:
                draw.rounded_rectangle(
                    box_xy, radius=10, fill=GUIDE_FILL, outline=GUIDE_OUTLINE, width=1,
                )
                if slot < len(alphabet_boxes) and src_bgr is not None:
                    _paste_glyph_in_cell(canvas, src_bgr, alphabet_boxes[slot], (cx, cy))
            slot += 1
            _centered_text(
                draw,
                (cx, cy + GLYPH_AREA_H + 6, CELL_W, CELL_H - GLYPH_AREA_H - 6),
                label,
                label_font,
                LABEL_FILL,
            )

    footer = (
        "Row-major order: 28 letters, then 0–9. "
        "python3 generate_aarth_font.py --image this.png"
    )
    draw.text((MARGIN_X, height - 44), footer, font=small_font, fill=NOTE_FILL)

    canvas.save(str(dest), "PNG")
    kind = "blank template" if blank else "source template"
    print(f"[output] {kind} → {dest}")
    return dest


def write_source_templates(
    dest: Path,
    alphabet_image: Path | None = None,
) -> tuple[Path, Path]:
    """Write the reading sheet and the all-empty blank sheet.

    ``dest`` may be a directory (canonical filenames) or a ``.png`` path for
    the reading sheet; the blank sheet is always ``ath_blank_template.png``
    next to it.
    """
    dest = Path(dest)
    image_suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    if dest.suffix.lower() in image_suffixes:
        filled = dest
        blank = dest.with_name("ath_blank_template.png")
    else:
        dest.mkdir(parents=True, exist_ok=True)
        filled = dest / "ath_source_template.png"
        blank = dest / "ath_blank_template.png"
    write_source_template(filled, alphabet_image=alphabet_image, blank=False)
    write_source_template(blank, alphabet_image=None, blank=True)
    return filled, blank


def _acquire_image(spec: str | None, output_dir: Path, fallback_name: str) -> Path:
    if spec and not spec.startswith("http"):
        return Path(spec)
    dest = output_dir / fallback_name
    url = spec if spec else SOURCE_URL
    if not dest.exists():
        download_image(url, dest)
    else:
        print(f"[info] using cached {dest}")
    return dest


def _trace_boxes(
    gray, binary, boxes, names, codepoints, tmp_dir: Path, glyph_data: list, idx0: int = 0,
):
    for i, box in enumerate(boxes):
        idx = idx0 + i
        codepoint = codepoints[i]
        name = names[i]
        print(f"  [{idx:02d}] {name} (U+{codepoint:04X}) …", end="", flush=True)
        svg_d = trace_glyph(gray, binary, box, tmp_dir, idx)
        print(" ok" if svg_d else " (no path)")
        glyph_data.append({"codepoint": codepoint, "name": name, "svg_d": svg_d})


def _write_debug_boxes(binary, labeled_boxes: list[tuple], dest: Path) -> None:
    debug_img = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    for (x, y, w, h), label in labeled_boxes:
        cv2.rectangle(debug_img, (x, y), (x + w, y + h), (0, 255, 0), 1)
        cv2.putText(
            debug_img, label, (x, max(12, y - 2)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 180, 255), 1, cv2.LINE_AA,
        )
    cv2.imwrite(str(dest), debug_img)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate Aarth webfont from Ath raster images (alphabet ± digits)",
    )
    parser.add_argument("--image", default=None,
                        help="Path to PNG image or URL (default: download from Wikimedia)")
    parser.add_argument(
        "--digits-image", default=None,
        help="Optional raster of Ath numerals 0–9 (7+3 or 10-wide grid; see --write-template)",
    )
    parser.add_argument(
        "--write-template", default=None, metavar="PATH",
        help="Write reading + blank templates (PNG path or directory) and exit",
    )
    parser.add_argument("--output-dir", default=".", help="Directory for output files")
    parser.add_argument("--debug", action="store_true", help="Save debug images")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.write_template:
        alphabet_src = None
        if args.image and not args.image.startswith("http"):
            alphabet_src = Path(args.image)
        elif (Path("Ath_alphabet.png")).is_file():
            alphabet_src = Path("Ath_alphabet.png")
        write_source_templates(Path(args.write_template), alphabet_image=alphabet_src)
        return

    # --- 1. Acquire image ---
    image_path = _acquire_image(args.image, output_dir, "Ath_alphabet.png")

    # --- 2. Pre-process ---
    print("[process] binarizing image …")
    gray = load_grayscale(image_path)
    binary = binarize(gray)

    # --- 3. Detect glyph boxes ---
    print("[process] detecting glyphs …")
    alphabet_boxes, digit_boxes = find_alphabet_and_digit_boxes(binary)
    print(
        f"  found {len(alphabet_boxes)} alphabet"
        f" + {len(digit_boxes)} digit boxes on --image"
    )

    digits_gray = gray
    digits_binary = binary
    if args.digits_image:
        digits_path = Path(args.digits_image)
        print(f"[process] reading digits image {digits_path} …")
        digits_gray = load_grayscale(digits_path)
        digits_binary = binarize(digits_gray)
        digit_boxes = find_digit_boxes(digits_binary)
        print(f"  found {len(digit_boxes)} digit boxes on --digits-image")

    if args.debug:
        labeled = [
            (box, ALPHABET_NAMES[i] if i < len(ALPHABET_NAMES) else str(i))
            for i, box in enumerate(alphabet_boxes)
        ]
        if digit_boxes and not args.digits_image:
            labeled += [
                (box, DIGIT_NAMES[i] if i < len(DIGIT_NAMES) else str(i))
                for i, box in enumerate(digit_boxes)
            ]
        _write_debug_boxes(binary, labeled, output_dir / "debug_boxes.png")
        if args.digits_image and digit_boxes:
            d_labeled = [
                (box, DIGIT_NAMES[i] if i < len(DIGIT_NAMES) else str(i))
                for i, box in enumerate(digit_boxes)
            ]
            _write_debug_boxes(
                digits_binary, d_labeled, output_dir / "debug_digit_boxes.png",
            )

    n_alpha = len(alphabet_boxes)
    n_digit = len(digit_boxes)
    if n_alpha != len(ALPHABET_CODEPOINTS):
        print(
            f"  [warn] expected {len(ALPHABET_CODEPOINTS)} alphabet glyphs "
            f"but found {n_alpha}. The font will be partial."
        )
    if n_digit and n_digit != DIGIT_COUNT:
        print(
            f"  [warn] expected {DIGIT_COUNT} digits but found {n_digit}."
        )
    if n_alpha == len(ALPHABET_CODEPOINTS) and n_digit == 0:
        print("  [info] no numerals in the source; font will omit 0–9.")

    alphabet_boxes = alphabet_boxes[:len(ALPHABET_CODEPOINTS)]
    digit_boxes = digit_boxes[:DIGIT_COUNT]

    # --- 4. Vectorise each glyph ---
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        glyph_data = []

        _trace_boxes(
            gray, binary, alphabet_boxes,
            ALPHABET_NAMES[:len(alphabet_boxes)],
            ALPHABET_CODEPOINTS[:len(alphabet_boxes)],
            tmp_dir, glyph_data, idx0=0,
        )
        if digit_boxes:
            _trace_boxes(
                digits_gray, digits_binary, digit_boxes,
                DIGIT_NAMES[:len(digit_boxes)],
                DIGIT_CODEPOINTS[:len(digit_boxes)],
                tmp_dir, glyph_data, idx0=len(alphabet_boxes),
            )

        print("[build] assembling font …")
        build_font(glyph_data, output_dir)

    print("[done] aarth.ttf and aarth.woff2 created.")


if __name__ == "__main__":
    main()
