# 言語パック — 実在言語に近づける道と、架空言語の設計手順

このディレクトリは、リポジトリの翻訳・読み上げを **「1 言語にベタ書きした規則」から「言語定義 + 転移エンジン」** へ開くための記述形式である。

既存のアーヴ語経路（`baronh/translate.py` / `grammar.py` / サーバエージェント）は壊さない。アーヴ語は `langs/baronh/` にメタデータとして写し、実行は従来実装へ委譲する。新規の架空言語は `langs/mina/` を複製して設計する。

## いまの実装が実在言語の MT / ASR と違うところ

| 層 | このリポジトリ（従来） | 実在言語の典型 |
|---|---|---|
| 解析 | 助詞と辞書語釈の最長一致 | 形態素解析 + 係り受け / ニューラル encoder |
| 意味 | 表層スロット（格・主題・動詞） | 文ベクトル、あるいは UD / AMR などのグラフ |
| 生成 | 格変化表 + 語順ヒューリスティック | decoder、あるいは実現文法 |
| 語彙 | 数千語・類義語寄せ | 数万〜、サブワード |
| TTS | 正書法 → 仮名 → 日本語音声 | G2P → IPA → 言語専用 vocoder |
| ASR | なし | 音響モデル + 言語モデル（しばしば WFST） |

近づけるとは、いきなり巨大モデルに置き換えることではない。**層を分け、各層を「表」から「統計 / ニューラル」へ差し替えられるようにする**ことである。言語パックはその差し込み口である。

```
日本語 / 英語                 目標言語（架空でも実在でも）
    │                              ▲
    ▼                              │
 解析（A） ── 中間表現（B）── 実現（C）
    │                              │
    └──── 語彙転移（lexicon）───┘
                   │
            音韻（D）G2P / 逆 G2P
                   │
         TTS（仮名・IPA） / ASR（制約付き）
```

- **A 解析**: いまは日本語助詞と英語前置詞の規則。実在言語なら Sudachi + GiNZA、あるいは NLLB の encoder。
- **B 中間表現**: いまは格役割のスロット列。次は Universal Dependencies、その先は文埋め込み。
- **C 実現**: いまはパックの接辞表。実在言語なら inflect ライブラリやニューラル decoder。
- **D 音韻**: いまは表引き G2P。実在言語なら Phonetisaurus / eSpeak、音響は Whisper / wav2vec。

架空言語では B・C・D を人が書く。実在言語では A と音響を既存モデルに任せ、C だけ辞書で縛る、といった混ぜ方ができる。

## 実在言語の翻訳へ近づけるアプローチ

優先度は「いまの辞書規模で効く順」。

1. **転移翻訳（本ディレクトリが実装）**  
   日本語・英語を格スロットへ落とし、目標言語の形態・統語で表層化する。語彙が限られた架空言語では、seq2seq より制御しやすい。アーヴ語の規則ベースはこれの専用実装である。

2. **制約付き生成 AI（既存のサーバエージェント）**  
   文法全文 + ベクトル検索した見出しだけを根拠に文を組む。公式対訳が無い言語の本線。実在の低資源言語でも、用語集 RAG として同じ形が使える。

3. **中間表現を厚くする**  
   スロット列 → UD（`nsubj`, `obj`, `obl`）→ 必要なら AMR。日本語解析だけ GiNZA に差し替えると、目標言語の規則はそのままに品質が上がる。

4. **対訳が十分ある実在言語**  
   自前エンジンを捨て、[NLLB](https://github.com/facebookresearch/fairseq/tree/nllb) / MADLAD / 商用 MT に任せる。言語パックは用語集・固有名詞・読みの層だけ残す。

5. **ハイブリッド**  
   ja/en はニューラル、架空言語はパック実現。中間を英語か UD にする。本リポジトリの ja↔en がアーヴ語を挟む二段翻訳なのは、この形の貧しい版である。

やらない方がよいこと: 数千語の辞書だけで end-to-end の Transformer を一から学習する。過学習し、造語も止められない。アーヴ語エージェントが造語を拒否している理由と同じである。

## 音声合成・音声認識へ近づけるアプローチ

1. **G2P を仮名プロキシから IPA へ**（`python -m baronh g2p --ipa`）  
   日本語 TTS に載せる仮名は近似である。IPA があれば eSpeak の `[[phonemes]]`、Piper の phoneme 入力、OpenAI TTS へ「読み」として渡せる。

2. **制約付き認識**（`python -m baronh recognize`）  
   音響モデルは持たない。仮名読み・IPA・正書法を、語形索引（辞書×形態）の最長一致で表層に落とす。これは小型のレキシコン FST である。Whisper の書き起こしをこの層へ渡せば、架空言語の「音声認識」になる。

3. **音響を足すとき**  
   - まず Whisper / wav2vec の汎用モデルで音素列に近い出力を得る  
   - ホットワード・プロンプトに見出しと形態を載せる  
   - 出力を `recognize` に通す  
   録音が貯まったら、その言語の G2P で強制アラインしてから細く fine-tune する。最初から fine-tune しない。

4. **専用 TTS**  
   仮名 + 日本語声のまま品質を上げるより、IPA → 言語非依存 vocoder の方が、架空音韻（`œ`, `gh=[ʒ]`）に忠実である。

## 新規の架空言語を設計する手順

1. 雛形を複製する。

```bash
python3 -m baronh init-lang keth --name-ja ケス語 --name-en Keth --autonym keth
```

2. `langs/keth/language.json` をこの順で書く（語彙より先に音韻と形態）。

   - **phonology**: 音素、音節、黙字、IPA、仮名読み表  
   - **morphology**: 格、語幹の切り方、接辞、動詞の態と語尾  
   - **syntax**: 語順、主題・疑問・呼格の助詞、コピュラ省略  
   - **lexicon.json**: `lemma / pos / gloss_ja / gloss_en / declension / stem / paradigm`

3. 格役割は日本語助詞と同じ集合（主格・対格・生格・与格・向格・奪格・具格 + 主題）にしておくと、解析側を共有できる。音形は自由である。

4. 動かす。

```bash
python3 -m baronh translate "私はケスです" --from ja --to keth --show-analysis
python3 -m baronh g2p "na ya kethde." --lang keth
python3 -m baronh g2p "na ya kethde." --lang keth --ipa
python3 -m baronh recognize "ナヤケスデ" --lang keth
python3 -m baronh grammar --lang keth
```

5. 生成 AI を載せるなら、`grammar` の出力をシステムプロンプトにし、辞書はベクトル検索する。アーヴ語エージェントと同じハーネスである。

設計上の約束（アーヴ語と同じ）:

- 辞書に無い普通名詞は造語しない  
- 固有名詞だけ発音転記してよい（パックに strategy を足す）  
- 翻訳 API と TTS は別呼び出し  
- 辞書全文をプロンプトに載せない

## 同梱パック

| id | 役割 | 実行エンジン |
|---|---|---|
| `baronh` | アーヴ語の記述。本番翻訳は従来コード | `morphology.engine=baronh` |
| `mina` | 膠着・CV 音節の雛形。転移エンジンの回帰対象 | `suffix` + `table` |

ミーナ語は作品設定ではなく、スキーマを試すための小さな言語である。

## ファイル

```
langs/
  language.schema.json
  baronh/language.json
  mina/language.json
  mina/lexicon.json
```

Python 側は `baronh/langpack.py`（読込・形態）、`baronh/transfer.py`（転移翻訳）、`baronh/g2p.py`（読み・IPA）、`baronh/asr.py`（制約付き認識）。
