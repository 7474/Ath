# Aarth — Ath Alphabet Webfont

[アース（Ath）](https://ja.wikipedia.org/wiki/%E3%82%A2%E3%83%BC%E3%83%B4%E8%AA%9E) の字形を抽出し、Web フォント（`aarth.ttf` / `aarth.woff2`）にしたものです。

字母（森岡浩之）に加え、数字 0–9（赤井孝美）もグリフ化します。既定の入力は `templates/ath_source_filled.png` です。自前のラスタを使う場合は [入力テンプレート](#入力テンプレート) を `--image` または `--digits-image` で渡してください。

## デモ

公開デモ（GitHub Pages）: **https://7474.github.io/Ath/**

GitHub Pages はプロジェクトのショーケース用です。他サイトからフォントを URL 指定する場合は [jsDelivr](#jsdelivr) を使ってください。

## 出典・ライセンス

[Wikipedia「アーヴ語」](https://ja.wikipedia.org/wiki/%E3%82%A2%E3%83%BC%E3%83%B4%E8%AA%9E) によれば、アースの**字母は原作者の森岡浩之**、**数字は原作イラストの赤井孝美**が設計しました。アーヴ語およびアースは森岡浩之『星界シリーズ』の架空言語・文字体系であり、本フォントはその設定に基づく**二次創作**です。

| 区分 | 設計 | ラスタ出典 | ラスタのライセンス |
|---|---|---|---|
| 字母 28 字 | 森岡浩之 | [Ath (alphabet).png](https://commons.wikimedia.org/wiki/File:Ath_(alphabet).png) | パブリックドメイン |
| 数字 0–9 | 赤井孝美 | [TRON 9-9830](https://commons.wikimedia.org/wiki/File:TRON_9-9830.gif)–[9-9839](https://commons.wikimedia.org/wiki/File:TRON_9-9839.gif)（`templates/digits/`） | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) |

数字ラスタが CC BY-SA 3.0 のため、それを含む結合成果物（記入済みテンプレートと本ウェブフォント）も **CC BY-SA 3.0** です。再利用・改変時は出典表示（設計者・ラスタ出典・ライセンス）と同一ライセンスでの共有が必要です。詳細は [LICENSE.md](LICENSE.md) を参照してください。

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
| 0 | U+0030 | `0` |
| 1 | U+0031 | `1` |
| 2 | U+0032 | `2` |
| 3 | U+0033 | `3` |
| 4 | U+0034 | `4` |
| 5 | U+0035 | `5` |
| 6 | U+0036 | `6` |
| 7 | U+0037 | `7` |
| 8 | U+0038 | `8` |
| 9 | U+0039 | `9` |

数字 0–9 は赤井孝美の設計に基づく TRON ラスタを既定で取り込みます。`--image Ath_alphabet.png` のように字母画像だけを渡すと、字母 28 字のみになります。

---

## 生成AI翻訳と音声合成

デモの「生成AI翻訳と音声合成」は、**Chat Completions（翻訳）** と **音声合成** を分けます。文法・種辞書は毎回全部は載せません。入力から関連チャンクを検索し、対応していればモデルが `search_lexicon` / `search_grammar` で追加取得します（ベクトル RAG ではなくキーワード検索 + ツール呼び出し）。

OpenAI 公式のほか、互換 API は Base URL で指定します。

```bash
python3 ath_translate_llm.py --api-base https://api.openai.com/v1 \
  --api-key "$OPENAI_API_KEY" --model gpt-4o-mini '星たちよ'

# 互換 API の例（Ollama）
python3 ath_translate_llm.py --api-base http://127.0.0.1:11434/v1 \
  --model llama3.2 --no-tools '星たちよ'
```

流れ:

1. 検索 → 文法カード / 種語彙（`knowledge/`）
2. `POST {base}/chat/completions` → アーヴ語をアース用キーで返す
3. キーを IPA に変換（TTS はウェブフォントを読めない）
4. 任意で `POST {base}/audio/speech`。多くの互換サーバは chat のみ。OpenAI TTS も英日向けなので、Baronh の正確な発音には音素対応エンジンが別途必要です。

環境変数 `OPENAI_BASE_URL`（または `OPENAI_API_BASE`）/ `OPENAI_API_KEY` / `OPENAI_MODEL` を参照します。種データは完全な辞書ではなく、[Wikipedia「アーヴ語」](https://ja.wikipedia.org/wiki/%E3%82%A2%E3%83%BC%E3%83%B4%E8%AA%9E) の公開記述に基づく要約です。

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

1. 既定では `templates/ath_source_filled.png` を読む（`--image <path>` でも指定可。無ければ Wikimedia Commons の字母画像）。
2. 画像を二値化し、28 個の字母領域を検出する。同じシートまたは `--digits-image` に数字 0–9 があれば続けて検出する。
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

## 入力テンプレート

字母と数字を **1 枚のラスタ画像** から読むときのセル配置です。左上から行優先（左→右、上→下）。ラベルはセルの下に小さく書き、グリフ本体より十分低くしてください（検出時にラベルは捨てます）。

```
a   i   u   é   o   e   c
s   t   l   n   h   p   f
m   ï   ai  y   œ   r   ü
au  ÿ   eu  g   z   d   b
0   1   2   3   4   5   6
7   8   9
```

同じ配置のシートを同梱しています。

| ファイル | 用途 |
|---|---|
| `templates/ath_source_filled.png` | **読み取り用（既定）。** 字母（森岡浩之）＋数字（赤井孝美 / CC BY-SA 3.0） |
| `templates/ath_source_template.png` | **読み取り用。** 字母だけ埋め込み、数字セルは空欄 |
| `templates/ath_blank_template.png` | **未記入。** 字母・数字とも空欄。全グリフを手描きするとき |
| `templates/digits/` | 数字 0–9 の CC BY-SA 3.0 ラスタ（TRON 9-9830–9-9839） |

再生成:

```bash
python3 generate_aarth_font.py --write-template templates/
```

読み取り用（字母＋数字）:

![Aarth filled source template](templates/ath_source_filled.png)

読み取り用（数字空欄）:

![Aarth source template](templates/ath_source_template.png)

未記入（空白）:

![Aarth blank template](templates/ath_blank_template.png)

使い方:

1. 既定の生成は記入済みシートを使います。数字だけ描き直すなら空欄シートをコピーし、空の数字セルに黒インクで 0–9 を描く。全字形を描くなら未記入シートを使う。
2. 白地・黒字形のまま PNG で保存する（ガイドやラベルは薄いグレーのまま残してよい）。
3. フォントを生成する。

```bash
# 既定（字母＋数字の記入済みテンプレート）
python3 generate_aarth_font.py

# 字母＋数字が 1 枚に入っている場合
python3 generate_aarth_font.py --image path/to/filled_template.png

# 字母は従来画像、数字だけ別ラスタ（7+3 または横 10 セル）
python3 generate_aarth_font.py --image Ath_alphabet.png --digits-image path/to/digits.png
```

数字だけを描く場合も、上の 5–6 行目と同じ **7+3**（または横一列の 10 セル）にしてください。アースの数字字形は原作イラストの赤井孝美氏による設計です。ラスタは CC BY-SA 3.0 です。全グリフを自前で描く場合は未記入テンプレートを使ってください。

---

## Command-line options

| Option | Default | Description |
|---|---|---|
| `--image` | filled template if present | Local path or HTTP URL of the alphabet (or combined) PNG |
| `--digits-image` | off | Optional PNG of numerals 0–9 (`7+3` or one row of 10) |
| `--write-template` | off | Write reading + blank templates to a PNG path or directory, then exit |
| `--output-dir` | `.` | Directory to write output files |
| `--debug` | off | Save `debug_boxes.png` (and `debug_digit_boxes.png` when digits are present) |

---

## Pipeline overview

```
Ath_(alphabet).png  [+ optional digits raster / extra template rows]
        │
        ▼
  OpenCV binarise + denoise
        │
        ▼
  cv2.findContours → merge overlines/umlauts
        → 4×7 alphabet boxes, then 0–9 if present (row-major)
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
