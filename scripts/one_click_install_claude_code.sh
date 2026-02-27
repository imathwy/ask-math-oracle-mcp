#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${ASK_MATH_ORACLE_REPO_URL:-https://github.com/imathwy/ask-math-oracle-mcp.git}"
TARGET_DIR="${ASK_MATH_ORACLE_TARGET_DIR:-$(mktemp -d)/ask-math-oracle-mcp}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/one_click_install_claude_code.sh [options] [-- quickstart-options]

Options:
  --repo-url <URL>        Git repository URL
  --target-dir <DIR>      Clone destination directory
  -h, --help              Show this help

Examples:
  ./scripts/one_click_install_claude_code.sh --google-key "$GOOGLE_API_KEY"
  ./scripts/one_click_install_claude_code.sh --scope user --anthropic-key "$ANTHROPIC_API_KEY"
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

quickstart_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-url)
      require_value "$@"
      REPO_URL="${2:-}"
      shift 2
      ;;
    --target-dir)
      require_value "$@"
      TARGET_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        quickstart_args+=("$1")
        shift
      done
      ;;
    *)
      quickstart_args+=("$1")
      shift
      ;;
  esac
done

echo "Cloning: ${REPO_URL}"
git clone --depth 1 "${REPO_URL}" "${TARGET_DIR}"

cd "${TARGET_DIR}"
chmod +x scripts/quickstart_claude_code.sh scripts/register_claude_code_mcp.sh
./scripts/quickstart_claude_code.sh "${quickstart_args[@]}"

echo
echo "Install source: ${TARGET_DIR}"
echo "If install succeeded, restart Claude Code session to reload MCP processes."
