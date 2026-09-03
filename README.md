# Aarth — Ath Alphabet Webfont

[アース（Ath）](https://ja.wikipedia.org/wiki/%E3%82%A2%E3%83%BC%E3%83%B4%E8%AA%9E) の字形を抽出し、Web フォント（`aarth.ttf` / `aarth.woff2`）にしたものです。

## デモ

公開デモ（GitHub Pages）: **https://7474.github.io/Ath/**

GitHub Pages はプロジェクトのショーケース用です。他サイトからフォントを URL 指定する場合は [jsDelivr](#jsdelivr) を使ってください。

## 出典・ライセンス

字形の出典は、日本語版 Wikipedia「[アーヴ語](https://ja.wikipedia.org/wiki/%E3%82%A2%E3%83%BC%E3%83%B4%E8%AA%9E)」に添付されているパブリックドメイン画像 [Ath (alphabet).png](https://ja.wikipedia.org/wiki/%E3%82%A2%E3%83%BC%E3%83%B4%E8%AA%9E#/media/%E3%83%95%E3%82%A1%E3%82%A4%E3%83%AB:Ath_(alphabet).png/2) です。著作権者により [パブリックドメイン](https://commons.wikimedia.org/wiki/File:Ath_(alphabet).png) として公開されています。

アーヴ語およびアースは、森岡浩之『星界シリーズ』に登場する架空言語・文字体系です（字母の設計は原作者の森岡浩之）。本フォントはその設定に基づく**二次創作**です。二次創作であることを前提に、自由に使っていただいて構いません。

関連情報は [Wikipedia「アーヴ語」](https://ja.wikipedia.org/wiki/%E3%82%A2%E3%83%BC%E3%83%B4%E8%AA%9E) を参照してください。

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

## Quick start

リポジトリをクローンしたあと、次の手順でフォントをローカル生成できます。

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
pip install -r requirements.txt
```

### 3. Generate the font

```bash
python3 generate_aarth_font.py
```

スクリプトは次を行います。

1. ローカルに画像がなければ Wikimedia Commons から `Ath_(alphabet).png` を取得する（`--image <path>` でも指定可）。
2. 画像を二値化し、28 個のグリフ領域を検出する。
3. 成分ごとにシルエットを整え、`potrace` でベクター化する（bitmap → SVG cubic Bézier）。
4. CFF ベースの OpenType フォントを組み立て、WOFF2 に圧縮する。

出力はデフォルトでカレントディレクトリです（`--output-dir`）。

```
aarth.ttf    — OpenType/CFF font（互換性が広い）
aarth.woff2  — モダンブラウザ向けの圧縮 Web フォント
```

### 4. Preview in a browser

`index.html` をローカル HTTP サーバで開きます（同じフォルダに `aarth.css`、`aarth.woff2`、`aarth.ttf` があること）。

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

## Pipeline overview

```
Ath_(alphabet).png
        │
        ▼
  OpenCV binarise + denoise
        │
        ▼
  cv2.findContours → merge overlines/umlauts → 28 glyph boxes (row-major)
        │
        ▼  (per glyph)
  per-component silhouette → SDF smooth + 8× → PGM → potrace --svg --blacklevel → SVG path
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
