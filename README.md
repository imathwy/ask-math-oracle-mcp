# ask_math_oracle MCP

`ask_math_oracle MCP` 是一个轻量 `stdio MCP server`，对外暴露一个工具：

- `ask_math_oracle`

它用于在遇到数学 blocker 时，自动向更擅长数学自然语言推理的模型请求帮助（OpenAI/Claude/Gemini）。

## 1. 目录结构

```text
ask_math_oracle_mcp/
  ask_math_oracle_mcp/
    __init__.py
    __main__.py
    server.py
  scripts/
    register_codex_mcp.sh
    smoke_test.py
  pyproject.toml
```

## 2. 环境变量

- `ASK_MATH_ORACLE_OPENAI_API_KEY` 或 `OPENAI_API_KEY`
- `ASK_MATH_ORACLE_ANTHROPIC_API_KEY` 或 `ANTHROPIC_API_KEY`
- `ASK_MATH_ORACLE_GOOGLE_API_KEY` 或 `GOOGLE_API_KEY`
- `ASK_MATH_ORACLE_OPENAI_BASE_URL`（可选，默认 `https://api.openai.com/v1`）
- `ASK_MATH_ORACLE_OPENAI_MODEL`（可选，默认 `gpt-5-pro`）
- `ASK_MATH_ORACLE_ANTHROPIC_BASE_URL`（可选，默认 `https://api.anthropic.com`）
- `ASK_MATH_ORACLE_ANTHROPIC_MODEL`（可选，默认 `claude-opus-4-1`）
- `ASK_MATH_ORACLE_ANTHROPIC_VERSION`（可选，默认 `2023-06-01`）
- `ASK_MATH_ORACLE_GEMINI_MODEL`（可选，默认 `gemini-2.5-pro`）
- `ASK_MATH_ORACLE_TIMEOUT_SEC`（可选，默认 `180`）
- `ASK_MATH_ORACLE_REASONING_EFFORT`（可选，OpenAI only）
- `ASK_MATH_ORACLE_DEBUG_MCP`（可选，`1` 时输出启动/方法调试日志到 stderr）

## 3. 本地协议测试（不访问外网）

`dry_run=true` 下不调用外部 API，只验证 MCP 协议与工具结构是否正常：

```bash
cd /root/workspace/wzc/main_book_formalization/codex_agent_bookformalization/_worktrees/ask_math_oracle_mcp
python3 scripts/smoke_test.py
```

## 4. 注册到 Codex CLI

最简方案（推荐）：

```bash
cd /root/workspace/wzc/main_book_formalization/codex_agent_bookformalization/_worktrees/ask_math_oracle_mcp
./scripts/quickstart.sh --openai-key "$OPENAI_API_KEY"
```

也可交互输入（不带参数运行）：

```bash
./scripts/quickstart.sh
```

标准注册脚本：

```bash
cd /root/workspace/wzc/main_book_formalization/codex_agent_bookformalization/_worktrees/ask_math_oracle_mcp
chmod +x scripts/register_codex_mcp.sh
./scripts/register_codex_mcp.sh
```

默认注册名：`ask-math-oracle`。可传自定义名字：

```bash
./scripts/register_codex_mcp.sh ask-math-oracle-dev
```

可选：设置启动超时（默认 60 秒）：

```bash
MCP_STARTUP_TIMEOUT_SEC=90 ./scripts/quickstart.sh --openai-key "$OPENAI_API_KEY"
```

说明：`register_codex_mcp.sh` 会自动把 `startup_timeout_sec` 写入当前 `CODEX_HOME/config.toml` 中对应的 MCP 条目。

## 5. 故障排查

若看到：

```text
MCP startup failed: handshaking with MCP server failed: connection closed: initialize response
```

请确认两点：

1. 已更新到当前版本（支持 JSONL 与 Content-Length 双向握手）。
2. 重启 Codex 会话后再试（旧进程不会自动热更新）。

快速自检：

```bash
cd /root/workspace/wzc/main_book_formalization/codex_agent_bookformalization/_worktrees/ask_math_oracle_mcp
python3 scripts/smoke_test.py
```

## 6. 工具入参（核心）

- `problem` (required): 数学 blocker 原始问题
- `provider`: `auto | openai | anthropic | gemini | both | all`
- `context`: 上下文
- `goal`: 目标
- `attempted`: 已尝试方案
- `style`: `direct | detailed | proof-sketch | lean-friendly`
- `max_output_tokens`
- `temperature`
- `reasoning_effort` (OpenAI)
- `allow_fallback` (`provider=auto` 时失败是否切另一家)
- `include_prompt_preview`
- `dry_run`

## 7. 在代理中的调用建议

当你在 AGENTS 规则里定义“数学阻塞触发外援”时，可采用：

- 条件：同一证明目标连续 `N` 次无推进（例如 N=2）
- 动作：调用 `ask_math_oracle`，传入 `problem/context/attempted`
- 约束：优先 `provider=auto`，关键问题可设 `provider=all` 交叉参考
