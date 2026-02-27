#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${ASK_MATH_ORACLE_REPO_URL:-https://github.com/imathwy/ask-math-oracle-mcp.git}"
TARGET_DIR="${ASK_MATH_ORACLE_TARGET_DIR:-$(mktemp -d)/ask-math-oracle-mcp}"

echo "Cloning: ${REPO_URL}"
git clone --depth 1 "${REPO_URL}" "${TARGET_DIR}"

cd "${TARGET_DIR}"
chmod +x scripts/quickstart.sh scripts/register_codex_mcp.sh
./scripts/quickstart.sh "$@"

echo
echo "Install source: ${TARGET_DIR}"
echo "If install succeeded, restart Codex session to reload MCP processes."
