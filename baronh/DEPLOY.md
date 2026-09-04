# 翻訳エージェントの実行場所

エージェントの本体は Python（`baronh/agent.py`）である。クラウド製品は **実行場所** と **モデルの口** に過ぎない。同じコンテナをローカルでも Cloud Run でも動かす。

GitHub Pages は静的ホストなのでエージェントを実行しない。ブラウザは `POST {agentUrl}/api/translate` するだけである。

## このプロジェクトに合うもの

平易さの順。

| 構成 | 向く理由 | 向かない理由 |
|---|---|---|
| **ローカル `python -m baronh serve`** | 辞書のベクトル索引はプロセス内。モデルだけ外部 | 公開 URL が無い。生成 AI が必須 |
| **Cloud Run + Vertex AI（Gemini の OpenAI 互換口）** | コンテナ 1 個、ゼロスケール、CORS、Secrets。いまのコードのまま | GCP プロジェクトが要る |
| **Cloud Run + 任意の OpenAI 互換** | Vertex 以外（OpenAI / LiteLLM / 自前 vLLM）も同じ | モデル課金は別 |
| **AWS Lambda Function URL または App Runner + Bedrock** | 同じ HTTP API を載せるだけ | コンテナよりコールドスタートが大きい場合がある |
| **Amazon Bedrock AgentCore Runtime** | 既存エージェントをほぼ書き換えず包める。セッション隔離、長時間実行 | この翻訳は同期の短いループなので過剰。ローカル再現が重い |
| **Vertex AI Agent Engine（旧 Agent Engine）** | Memory Bank や ADK と組むとき | 状態を跨ぐ会話が本筋ではない。Cloud Run の方が単純 |
| **Azure Container Apps + Azure OpenAI** | Cloud Run と同型 | Azure を既に使っているとき向け |
| **Cloudflare Workers / Durable Objects** | エッジ | Python エージェントを載せ直す必要がある |
| **LangGraph Cloud / 専用エージェント PaaS** | グラフ型の長いワークフロー | ツール 4 個の短ループには不要 |

推奨は **Cloud Run（またはローカル serve）にエージェントを置き、モデルは OpenAI 互換 URL で差し替える** こと。AgentCore や Agent Engine は、あとから同じ `translate_agent()` をエントリに包めばよい。

## エージェントがやること

同期の短ループである。セッション記憶やブラウザ操作は使わない。

1. 原文を簡易ベクトル索引で検索し、文法全文をシステムプロンプトへ載せる
2. 生成 AI が `search_lexicon` / `find_synonyms` などで辞書を追加検索する（モデル必須）
3. 文の組み立てはモデル。規則下訳は渡さない
4. アーヴ語の語形を辞書と照合する

Memory Bank や AgentCore Memory は、この翻訳にはまだ要らない。

## ローカル

```bash
python3 -m baronh serve
# http://127.0.0.1:8765/web/
# POST http://127.0.0.1:8765/api/translate
```

エージェントは生成 AI が必須。環境変数を付ける。

```bash
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=https://api.openai.com/v1   # または互換口
export OPENAI_CHAT_MODEL=gpt-4o-mini
python3 -m baronh translate "星たちの光を見ます" --from ja --to baronh --engine agent
```

## Cloud Run + Vertex AI（平易な公開構成）

同じイメージを Cloud Run に載せ、Gemini を OpenAI 互換で呼ぶ。ビルドコンテキストはリポジトリ根（`deploy/Dockerfile` の COPY が根からのパスだから）。

```bash
docker build -f deploy/Dockerfile -t baronh-agent .
# または:
# gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/REPO/baronh-agent -f deploy/Dockerfile

gcloud run deploy baronh-agent \
  --image REGION-docker.pkg.dev/PROJECT/REPO/baronh-agent \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars OPENAI_BASE_URL=https://aiplatform.googleapis.com/v1/projects/PROJECT/locations/asia-northeast1/endpoints/openapi,OPENAI_CHAT_MODEL=google/gemini-2.0-flash,BARONH_CORS_ORIGIN=https://7474.github.io
```

認証トークンを `OPENAI_API_KEY` に載せるか、サイドカー / ADC で OpenAI 互換プロキシを挟む。GitHub Pages から叩くなら `BARONH_CORS_ORIGIN` を Pages のオリジンに固定する。

翻訳ページの「生成AI設定」にある「エージェント URL」に `https://<service>-<hash>.run.app/api/translate` を入れる。

`deploy/Dockerfile` は翻訳に必要なファイルだけを含む。フォント生成用の OpenCV は入れない。

## Amazon Bedrock AgentCore

AgentCore Runtime は、既存のエージェントコードを microVM に載せる枠である。このリポジトリでは次が対応する。

- Runtime のエントリで `translate_agent()` を呼ぶ
- ツールは AgentCore Gateway ではなく、いまの Python ツール（辞書はプロセス内）で足りる
- Memory / Browser / Code Interpreter は使わない

向き: セッション隔離や 8 時間級の非同期が要るとき。単発のアーヴ語翻訳には Cloud Run の方が平易。

Bedrock のモデルを使うだけなら、AgentCore を経由せず **Lambda URL / App Runner + Bedrock Converse（または OpenAI 互換プロキシ）** でもよい。

## Vertex AI Agent Engine

Agent Engine は Gemini + Memory Bank 向けのランタイムである。会話を跨いでユーザの用語を覚える、といった要件が無い限り Cloud Run でよい。載せるなら ADK のツールから `find_synonyms` / `lookup_lexicon` を呼ぶ。

## その他のマネージド

- **OpenAI Assistants / Responses API ホスト**: ツール定義を向こうに預ける。辞書はこちらが持っているので、結局 HTTP で自前ツールを呼ぶことになり、Cloud Run と同じ形に戻る。
- **LiteLLM / Cloudflare AI Gateway**: モデル口の集約。エージェント本体は引き続きこのコンテナ。
- **Fly.io / Railway / Modal**: Dockerfile をそのまま。ホビー公開向け。
- **Cloudflare Workers AI**: JS への移植が要る。辞書 2400 語は載るが、格変化と類義語ロジックの二重管理になる。

## API

`POST /api/translate`

```json
{
  "text": "星たちの光を見ます",
  "source_lang": "ja",
  "target_lang": "baronh",
  "engine": "agent"
}
```

`engine` は `agent`（既定）/ `local` / `openai`。`GET /api/health`、`GET /api/synonyms?q=光`、`GET /api/search?q=光`（ベクトル検索）もある。モデルが無ければ `engine=agent` は 503。

環境変数: `PORT`（Cloud Run）、`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_CHAT_MODEL`、`BARONH_CORS_ORIGIN`。
