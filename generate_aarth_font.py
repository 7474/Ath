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
CAP_HEIGHT = 700   # target height every glyph is scaled to
X_HEIGHT = 500
GLYPH_LSB = 40     # left/right side bearing in font units


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

def layout_glyph(svg_d: str, target_height: float, lsb: float):
    """
    Fit a potrace SVG path to the font's em, without drawing yet.

    Potrace path coordinates are y-up and 10x the source-pixel size (the SVG's
    own ``<g transform="translate(0,H) scale(0.1,-0.1)">`` compensates for that
    when rendered). Because we fit each glyph by its own bounding box, the
    constant 10x factor and any origin offset cancel out, so that group
    transform does not need to be applied here. A single uniform positive scale
    keeps the aspect ratio and preserves contour orientation, so counters/holes
    fill correctly.

    Returns ``(recording_pen, affine, advance)`` — replaying ``recording_pen``
    through ``TransformPen(target_pen, affine)`` scales the glyph to
    ``target_height`` font units, resting on the baseline with ``lsb`` units of
    left side bearing — or ``None`` when the path is empty/degenerate.
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

    Each glyph is scaled from its own outline bounding box to CAP_HEIGHT and set
    on the baseline, so all glyphs share a consistent size regardless of the
    source pixel dimensions.
    """
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.pens.transformPen import TransformPen

    glyph_names = [".notdef"] + [g["name"] for g in glyph_data]

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
                layout = layout_glyph(g["svg_d"], CAP_HEIGHT, GLYPH_LSB)
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

            # build_font() scales each glyph from its own outline bounding box,
            # so no per-box scale/offset needs to be computed here.
            glyph_data.append({
                "codepoint": codepoint,
                "name": name,
                "svg_d": svg_d,
            })

        print("[build] assembling font …")
        build_font(glyph_data, output_dir)

    print("[done] aarth.ttf and aarth.woff2 created.")


if __name__ == "__main__":
    main()
