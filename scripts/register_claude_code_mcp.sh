#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_PY="$ROOT_DIR/ask_math_oracle_mcp/server.py"
MCP_NAME="${MCP_NAME:-ask-math-oracle}"
CLAUDE_SCOPE="${CLAUDE_SCOPE:-user}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/register_claude_code_mcp.sh [options]

Options:
  --mcp-name <NAME>       MCP server name (default: ask-math-oracle)
  --scope <SCOPE>         Claude MCP scope: user | project | local (default: user)
  -h, --help              Show this help
EOF
}

require_value() {
  local opt="$1"
  if [[ "${2+x}" != "x" || "$2" == --* ]]; then
    echo "Missing value for ${opt}" >&2
    usage >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mcp-name)
      require_value "$@"
      MCP_NAME="${2:-ask-math-oracle}"
      shift 2
      ;;
    --scope)
      require_value "$@"
      CLAUDE_SCOPE="${2:-user}"
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

case "$CLAUDE_SCOPE" in
  user|project|local) ;;
  *)
    echo "ERROR: --scope must be one of: user, project, local." >&2
    exit 1
    ;;
esac

if ! command -v claude >/dev/null 2>&1; then
  echo "ERROR: 'claude' command not found. Install Claude Code CLI first." >&2
  exit 1
fi

ask_key_namespace_present=0
if [[ "${ASK_MATH_ORACLE_OPENAI_API_KEY+x}" == "x" ]]; then
  ask_key_namespace_present=1
fi
if [[ "${ASK_MATH_ORACLE_ANTHROPIC_API_KEY+x}" == "x" ]]; then
  ask_key_namespace_present=1
fi
if [[ "${ASK_MATH_ORACLE_GOOGLE_API_KEY+x}" == "x" ]]; then
  ask_key_namespace_present=1
fi

if [[ "${ask_key_namespace_present}" -eq 1 ]]; then
  OPENAI_KEY="${ASK_MATH_ORACLE_OPENAI_API_KEY:-}"
  ANTHROPIC_KEY="${ASK_MATH_ORACLE_ANTHROPIC_API_KEY:-}"
  GOOGLE_KEY="${ASK_MATH_ORACLE_GOOGLE_API_KEY:-}"
else
  OPENAI_KEY="${OPENAI_API_KEY:-}"
  ANTHROPIC_KEY="${ANTHROPIC_API_KEY:-}"
  GOOGLE_KEY="${GOOGLE_API_KEY:-}"
fi

if [[ -z "${OPENAI_KEY}" && -z "${ANTHROPIC_KEY}" && -z "${GOOGLE_KEY}" ]]; then
  echo "ERROR: at least one API key is required." >&2
  echo "Set one of: OPENAI / ANTHROPIC / GOOGLE keys." >&2
  exit 1
fi

env_args=()
if [[ -n "${OPENAI_KEY}" ]]; then
  env_args+=(--env "ASK_MATH_ORACLE_OPENAI_API_KEY=${OPENAI_KEY}")
fi
if [[ -n "${ANTHROPIC_KEY}" ]]; then
  env_args+=(--env "ASK_MATH_ORACLE_ANTHROPIC_API_KEY=${ANTHROPIC_KEY}")
fi
if [[ -n "${GOOGLE_KEY}" ]]; then
  env_args+=(--env "ASK_MATH_ORACLE_GOOGLE_API_KEY=${GOOGLE_KEY}")
fi
if [[ -n "${ASK_MATH_ORACLE_OPENAI_BASE_URL:-}" ]]; then
  env_args+=(--env "ASK_MATH_ORACLE_OPENAI_BASE_URL=${ASK_MATH_ORACLE_OPENAI_BASE_URL}")
fi
if [[ -n "${ASK_MATH_ORACLE_OPENAI_MODEL:-}" ]]; then
  env_args+=(--env "ASK_MATH_ORACLE_OPENAI_MODEL=${ASK_MATH_ORACLE_OPENAI_MODEL}")
fi
if [[ -n "${ASK_MATH_ORACLE_ANTHROPIC_BASE_URL:-}" ]]; then
  env_args+=(--env "ASK_MATH_ORACLE_ANTHROPIC_BASE_URL=${ASK_MATH_ORACLE_ANTHROPIC_BASE_URL}")
fi
if [[ -n "${ASK_MATH_ORACLE_ANTHROPIC_MODEL:-}" ]]; then
  env_args+=(--env "ASK_MATH_ORACLE_ANTHROPIC_MODEL=${ASK_MATH_ORACLE_ANTHROPIC_MODEL}")
fi
if [[ -n "${ASK_MATH_ORACLE_ANTHROPIC_VERSION:-}" ]]; then
  env_args+=(--env "ASK_MATH_ORACLE_ANTHROPIC_VERSION=${ASK_MATH_ORACLE_ANTHROPIC_VERSION}")
fi
if [[ -n "${ASK_MATH_ORACLE_GEMINI_MODEL:-}" ]]; then
  env_args+=(--env "ASK_MATH_ORACLE_GEMINI_MODEL=${ASK_MATH_ORACLE_GEMINI_MODEL}")
fi
if [[ -n "${ASK_MATH_ORACLE_TIMEOUT_SEC:-}" ]]; then
  env_args+=(--env "ASK_MATH_ORACLE_TIMEOUT_SEC=${ASK_MATH_ORACLE_TIMEOUT_SEC}")
fi
if [[ -n "${ASK_MATH_ORACLE_REASONING_EFFORT:-}" ]]; then
  env_args+=(--env "ASK_MATH_ORACLE_REASONING_EFFORT=${ASK_MATH_ORACLE_REASONING_EFFORT}")
fi
if [[ -n "${ASK_MATH_ORACLE_DEBUG_MCP:-}" ]]; then
  env_args+=(--env "ASK_MATH_ORACLE_DEBUG_MCP=${ASK_MATH_ORACLE_DEBUG_MCP}")
fi

claude mcp remove "$MCP_NAME" --scope "$CLAUDE_SCOPE" >/dev/null 2>&1 || claude mcp remove "$MCP_NAME" >/dev/null 2>&1 || true
claude mcp add "$MCP_NAME" --scope "$CLAUDE_SCOPE" "${env_args[@]}" -- python3 "$SERVER_PY"

echo
echo "Installed Claude Code MCP server: $MCP_NAME"
echo "Scope: $CLAUDE_SCOPE"
claude mcp list
