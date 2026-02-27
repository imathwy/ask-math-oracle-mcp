#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_PY="$ROOT_DIR/ask_math_oracle_mcp/server.py"
MCP_NAME="${1:-ask-math-oracle}"
MCP_STARTUP_TIMEOUT_SEC="${MCP_STARTUP_TIMEOUT_SEC:-60}"

if [[ "${MCP_STARTUP_TIMEOUT_SEC}" =~ ^[0-9]+$ ]]; then
  if [[ "${MCP_STARTUP_TIMEOUT_SEC}" -lt 1 ]]; then
    echo "ERROR: MCP_STARTUP_TIMEOUT_SEC must be >= 1." >&2
    exit 1
  fi
else
  echo "ERROR: MCP_STARTUP_TIMEOUT_SEC must be a positive integer." >&2
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

codex mcp remove "$MCP_NAME" >/dev/null 2>&1 || true
codex mcp add "$MCP_NAME" "${env_args[@]}" -- python3 "$SERVER_PY"

# Ensure startup timeout is present in the active CODEX_HOME config.
CONF_HOME="${CODEX_HOME:-${HOME}/.codex}"
CONF_FILE="$CONF_HOME/config.toml"
python3 - "$CONF_FILE" "$MCP_NAME" "$MCP_STARTUP_TIMEOUT_SEC" <<'PY'
import pathlib
import re
import sys

cfg_path = pathlib.Path(sys.argv[1])
name = sys.argv[2]
timeout = sys.argv[3]

if not cfg_path.exists():
    sys.exit(0)

text = cfg_path.read_text(encoding="utf-8")
header = f"[mcp_servers.{name}]"
pat = re.compile(
    rf"(?ms)^(?P<header>\[mcp_servers\.{re.escape(name)}\]\n)(?P<body>.*?)(?=^\[|\Z)"
)
m = pat.search(text)
if not m:
    sys.exit(0)

body = m.group("body")
if re.search(r"(?m)^\s*startup_timeout_sec\s*=", body):
    body2 = re.sub(
        r"(?m)^\s*startup_timeout_sec\s*=.*$",
        f"startup_timeout_sec = {timeout}",
        body,
    )
else:
    body2 = f"startup_timeout_sec = {timeout}\n" + body

new_block = m.group("header") + body2
new_text = text[: m.start()] + new_block + text[m.end() :]

if new_text != text:
    cfg_path.write_text(new_text, encoding="utf-8")
PY

codex mcp get "$MCP_NAME"
