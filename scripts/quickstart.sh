#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REGISTER_SH="$ROOT_DIR/scripts/register_codex_mcp.sh"
MCP_NAME="${MCP_NAME:-ask-math-oracle}"
MCP_STARTUP_TIMEOUT_SEC="${MCP_STARTUP_TIMEOUT_SEC:-60}"

OPENAI_KEY="${ASK_MATH_ORACLE_OPENAI_API_KEY:-${OPENAI_API_KEY:-}}"
ANTHROPIC_KEY="${ASK_MATH_ORACLE_ANTHROPIC_API_KEY:-${ANTHROPIC_API_KEY:-}}"
GOOGLE_KEY="${ASK_MATH_ORACLE_GOOGLE_API_KEY:-${GOOGLE_API_KEY:-}}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/quickstart.sh [options]

Options:
  --openai-key <KEY>      Set OpenAI key for this run
  --anthropic-key <KEY>   Set Anthropic key for this run
  --google-key <KEY>      Set Google key for this run
  --mcp-name <NAME>       MCP server name (default: ask-math-oracle)
  -h, --help              Show this help

Examples:
  ./scripts/quickstart.sh --openai-key "$OPENAI_API_KEY"
  ./scripts/quickstart.sh --anthropic-key "$ANTHROPIC_API_KEY"
  ./scripts/quickstart.sh --openai-key "$OPENAI_API_KEY" --anthropic-key "$ANTHROPIC_API_KEY" --google-key "$GOOGLE_API_KEY"
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --openai-key)
      OPENAI_KEY="${2:-}"
      shift 2
      ;;
    --anthropic-key)
      ANTHROPIC_KEY="${2:-}"
      shift 2
      ;;
    --google-key)
      GOOGLE_KEY="${2:-}"
      shift 2
      ;;
    --mcp-name)
      MCP_NAME="${2:-ask-math-oracle}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${OPENAI_KEY}" && -z "${ANTHROPIC_KEY}" && -z "${GOOGLE_KEY}" ]]; then
  echo "No API key found in env or CLI flags." >&2
  echo "Quick input mode: paste ONE key to continue." >&2
  echo "Tip: you can also pass --openai-key/--anthropic-key/--google-key." >&2
  read -r -p "Provider [openai/anthropic/google] (default: openai): " provider
  provider="${provider:-openai}"
  case "${provider}" in
    openai)
      read -r -s -p "OpenAI API key: " OPENAI_KEY
      echo
      ;;
    anthropic)
      read -r -s -p "Anthropic API key: " ANTHROPIC_KEY
      echo
      ;;
    google)
      read -r -s -p "Google API key: " GOOGLE_KEY
      echo
      ;;
    *)
      echo "Unsupported provider: ${provider}" >&2
      exit 1
      ;;
  esac
fi

if [[ -z "${OPENAI_KEY}" && -z "${ANTHROPIC_KEY}" && -z "${GOOGLE_KEY}" ]]; then
  echo "At least one key is required." >&2
  exit 1
fi

export ASK_MATH_ORACLE_OPENAI_API_KEY="${OPENAI_KEY:-}"
export ASK_MATH_ORACLE_ANTHROPIC_API_KEY="${ANTHROPIC_KEY:-}"
export ASK_MATH_ORACLE_GOOGLE_API_KEY="${GOOGLE_KEY:-}"
export MCP_STARTUP_TIMEOUT_SEC

cd "$ROOT_DIR"
"$REGISTER_SH" "$MCP_NAME"

echo
echo "Installed MCP server: $MCP_NAME"
echo "Startup timeout: ${MCP_STARTUP_TIMEOUT_SEC}s"
echo "Active CODEX_HOME: ${CODEX_HOME:-$HOME/.codex}"
echo "Minimal usage in agent: call tool 'ask_math_oracle' with"
echo "  {\"problem\":\"<your math blocker>\",\"provider\":\"auto\"}"
