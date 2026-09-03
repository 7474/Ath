# Aarth — Ath Alphabet Webfont Generator

## GitHub Pages デモ

> **デモ URL（GitHub Pages）**: `https://7474.github.io/Ath/`
>
> GitHub Pages はプロジェクトのショーケース用です。他サイトからフォントを URL 指定する場合は [jsDelivr](#jsdelivr) を使ってください。
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

### jsDelivr

[jsDelivr](https://www.jsdelivr.com/) に登録・申請する手続きはありません。GitHub エンドポイントは **公開リポジトリに push されたファイルを自動配信**します。アカウント作成、npm 公開、設定ファイル、ダッシュボード操作も不要で、URL を書くだけで使えます。

```
https://cdn.jsdelivr.net/gh/<user>/<repo>@<ref>/<path>
```

このリポジトリでは次のとおりです。`aarth.css` の `@font-face` は相対パスなので、フォントは CSS と同じ jsDelivr URL から解決されます。

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/7474/Ath@main/docs/aarth.css">
<style>
  .ath { font-family: 'Aarth', serif; }
</style>
<p class="ath">aarth lotr atosr</p>
```

`@font-face` を自分で書く場合:

```css
@font-face {
  font-family: 'Aarth';
  src: url('https://cdn.jsdelivr.net/gh/7474/Ath@main/docs/aarth.woff2') format('woff2'),
       url('https://cdn.jsdelivr.net/gh/7474/Ath@main/docs/aarth.ttf')   format('truetype');
  font-weight: normal;
  font-style:  normal;
  font-display: swap;
}
```

- リポジトリが **public** であることだけが条件です（private は配信されません）。
- 初回アクセス時に GitHub から取得してキャッシュします。数秒かかることがあります。
- `@main` はブランチ参照で、[キャッシュは約 12 時間](https://github.com/jsdelivr/jsdelivr#caching)です。本番ではコミット SHA を指定すると内容が固定されます。
- クロスオリジンの `@font-face` に必要な `Access-Control-Allow-Origin` は jsDelivr が返します。
- `raw.githubusercontent.com` は MIME 型が `text/plain` になるため使わないでください。
- 公式: [GitHub からの使い方](https://github.com/jsdelivr/jsdelivr#github) / [URL 変換](https://www.jsdelivr.com/github)

GitHub Pages は [プロジェクトのショーケース用](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features#pages) です。デモページからの利用は想定どおりですが、他サイトからの恒常的な直リンクには jsDelivr を使ってください。

デモページ上のスニペットは、表示中のホストに合わせた絶対 URL にも書き換わります。

### ローカルに置く（オフライン用）

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
