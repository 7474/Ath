# Aarth — Ath Alphabet Webfont Generator

## GitHub Pages デモ

> **公開 URL（GitHub Pages）**: `https://7474.github.io/Ath/`
>
> フォントをダウンロードせずに使う場合のエンドポイント:
> - スタイルシート: `https://7474.github.io/Ath/aarth.css`
> - WOFF2: `https://7474.github.io/Ath/aarth.woff2`
> - TTF: `https://7474.github.io/Ath/aarth.ttf`
>
> `main` ブランチへの push をトリガーに GitHub Actions が自動でフォントを再生成し、
> `docs/` フォルダの内容を GitHub Pages へデプロイします。
>
> **GitHub Pages の有効化手順**（初回のみリポジトリオーナーが実施）:
> 1. https://github.com/7474/Ath/settings/pages を開く
> 2. **Source** → `Deploy from a branch`
> 3. **Branch** → `main` / `docs`
> 4. Save



Automatically extracts glyph shapes from the **Ath (Ath alphabet)** raster image,
vectorises them with Potrace, and packages the result as a ready-to-use webfont
(`aarth.ttf` / `aarth.woff2`).

---

## Quick start

### 1. Install system tools

```bash
# Debian / Ubuntu
sudo apt-get install potrace

# macOS
brew install potrace

# Windows — download the binary from http://potrace.sourceforge.net/
```

### 2. Install Python packages

```bash
pip install opencv-python-headless pillow fonttools brotli
```

### 3. Generate the font

```bash
python3 generate_aarth_font.py
```

The script will:
1. Download `Ath_(alphabet).png` from Wikimedia Commons (or use `--image <path>`) if no local copy is found.
2. Binarise the image and detect 28 glyph bounding boxes.
3. Vectorise each glyph via `potrace` (bitmap → SVG cubic Bézier).
4. Build a CFF-based OpenType font and compress it to WOFF2.

Output files are written to the current directory by default (`--output-dir`).

```
aarth.ttf    — OpenType/CFF font (broadest compatibility)
aarth.woff2  — Compressed webfont for modern browsers
```

### 4. Preview in a browser

Open `index.html` via a local HTTP server (make sure `aarth.css`, `aarth.woff2`, and `aarth.ttf` are in the same folder).

```bash
python3 -m http.server 8000
# http://127.0.0.1:8000/
```

---

## Command-line options

| Option | Default | Description |
|---|---|---|
| `--image` | Wikimedia URL | Local path or HTTP URL of the source PNG |
| `--output-dir` | `.` | Directory to write output files |
| `--debug` | off | Save `debug_boxes.png` showing detected bounding boxes |

---

## Character mapping

The 28 Ath phonemes are mapped to the following Unicode code points:

| Ath phoneme | Unicode | Key to type |
|---|---|---|
| a | U+0061 | `a` |
| i | U+0069 | `i` |
| u | U+0075 | `u` |
| é | U+00E9 | `é` |
| o | U+006F | `o` |
| e | U+0065 | `e` |
| c | U+0063 | `c` |
| s | U+0073 | `s` |
| t | U+0074 | `t` |
| l | U+006C | `l` |
| n | U+006E | `n` |
| h | U+0068 | `h` |
| p | U+0070 | `p` |
| f | U+0066 | `f` |
| m | U+006D | `m` |
| ï | U+00EF | `ï` |
| ai (digraph) | U+0041 | `A` |
| y | U+0079 | `y` |
| œ | U+0153 | `œ` |
| r | U+0072 | `r` |
| ü | U+00FC | `ü` |
| au (digraph) | U+0049 | `I` |
| ÿ | U+00FF | `ÿ` |
| eu (digraph) | U+0045 | `E` |
| g | U+0067 | `g` |
| z | U+007A | `z` |
| d | U+0064 | `d` |
| b | U+0062 | `b` |

---

## CSS / HTML usage

フォントファイルをプロジェクトにコピーしなくても、公開 URL を指定して使えます。
`aarth.css` の `@font-face` は相対パスなので、**CSS 自身の URL** を基準に `aarth.woff2` / `aarth.ttf` が解決されます。別サイトから CSS を `<link>` しても、フォントは CSS と同じオリジンから取得されます。

クロスオリジンの `@font-face` には配信元の `Access-Control-Allow-Origin` が必要です。GitHub Pages と jsDelivr はこれを返します。`raw.githubusercontent.com` は MIME 型が `text/plain` になるため使わないでください。

デモページ上のスニペットは、表示中のホストに合わせた絶対 URL に書き換わります。

### 1. スタイルシートを link する（推奨）

GitHub Pages の公開 URL（この README 先頭）を使った例:

```html
<link rel="stylesheet" href="https://7474.github.io/Ath/aarth.css">
<style>
  .ath { font-family: 'Aarth', serif; }
</style>
<p class="ath">aarth lotr atosr</p>
```

GitHub Pages を使わず Git 上の `docs/` を CDN 配信する場合（jsDelivr）:

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/7474/Ath@main/docs/aarth.css">
```

本番では `@main` の代わりにコミット SHA を指定すると、フォント再生成の影響を受けません。

### 2. `@font-face` にフォント URL を直接書く

```css
@font-face {
  font-family: 'Aarth';
  src: url('https://7474.github.io/Ath/aarth.woff2') format('woff2'),
       url('https://7474.github.io/Ath/aarth.ttf')   format('truetype');
  font-weight: normal;
  font-style:  normal;
  font-display: swap;
}
```

### 3. ローカルに置く（オフライン用）

```html
<style>
  @font-face {
    font-family: 'Aarth';
    src: url('aarth.woff2') format('woff2'),
         url('aarth.ttf')   format('truetype');
    font-weight: normal;
    font-style:  normal;
    font-display: swap;
  }

  .ath {
    font-family: 'Aarth', serif;
  }
</style>

<p class="ath">aarth lotr atosr</p>
```

---

## Pipeline overview

```
Ath_(alphabet).png
        │
        ▼
  OpenCV binarise + denoise
        │
        ▼
  cv2.findContours → 28 glyph bounding boxes (sorted row-major)
        │
        ▼  (per glyph)
  crop → PBM bitmap → potrace --svg → SVG path 'd' string
        │
        ▼
  Scale & translate to 1000-unit EM (ascender=800, descender=-200)
        │
        ▼
  fontTools FontBuilder (CFF/OTF, cubic Bézier)
        │
        ├──▶ aarth.ttf
        └──▶ aarth.woff2  (via fontTools woff2 compress)
```
