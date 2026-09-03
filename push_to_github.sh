#!/usr/bin/env bash
# push_to_github.sh
# GitHub (https://github.com/7474/Ath) へ全コミットを push するスクリプト。
#
# 事前準備:
#   環境変数 GITHUB_PAT に repo スコープの Personal Access Token を設定してください。
#   例: export GITHUB_PAT=ghp_xxxxxxxxxxxxxxxxxxxx
#
# 実行:
#   bash push_to_github.sh

set -euo pipefail

GITHUB_REPO="https://github.com/7474/Ath.git"

if [[ -z "${GITHUB_PAT:-}" ]]; then
  echo "[error] 環境変数 GITHUB_PAT が設定されていません。"
  echo "  export GITHUB_PAT=<your_personal_access_token>"
  exit 1
fi

REMOTE_URL="https://x-access-token:${GITHUB_PAT}@github.com/7474/Ath.git"

echo "[info] GitHub remote を設定 …"
git remote add github "$REMOTE_URL" 2>/dev/null || \
  git remote set-url github "$REMOTE_URL"

echo "[info] main ブランチを push …"
git push github main

echo "[done] push 完了: https://github.com/7474/Ath"
echo ""
echo "次のステップ — GitHub Pages を有効化:"
echo "  1. https://github.com/7474/Ath/settings/pages を開く"
echo "  2. Source: Deploy from a branch"
echo "  3. Branch: main / docs → Save"
echo "  公開 URL: https://7474.github.io/Ath/"
