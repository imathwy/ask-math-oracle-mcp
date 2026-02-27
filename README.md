# ask_math_oracle MCP

`ask_math_oracle MCP` 是一个轻量 `stdio MCP server`，提供工具：

- `ask_math_oracle`

用于在数学 blocker 时，向 OpenAI / Claude / Gemini 请求辅助推理。

## 远端仓库

- GitHub: `https://github.com/imathwy/ask-math-oracle-mcp`

## 一键配置（推荐）

前置依赖：`git`、`python3`、`codex`。

### 方案 A：真正一条命令（无需先 clone）

Gemini:

```bash
curl -fsSL https://raw.githubusercontent.com/imathwy/ask-math-oracle-mcp/main/scripts/one_click_install.sh | bash -s -- --google-key "$GOOGLE_API_KEY"
```

OpenAI:

```bash
curl -fsSL https://raw.githubusercontent.com/imathwy/ask-math-oracle-mcp/main/scripts/one_click_install.sh | bash -s -- --openai-key "$OPENAI_API_KEY"
```

Claude:

```bash
curl -fsSL https://raw.githubusercontent.com/imathwy/ask-math-oracle-mcp/main/scripts/one_click_install.sh | bash -s -- --anthropic-key "$ANTHROPIC_API_KEY"
```

多模型一起配置：

```bash
curl -fsSL https://raw.githubusercontent.com/imathwy/ask-math-oracle-mcp/main/scripts/one_click_install.sh | bash -s -- \
  --openai-key "$OPENAI_API_KEY" \
  --anthropic-key "$ANTHROPIC_API_KEY" \
  --google-key "$GOOGLE_API_KEY"
```

离线/内网场景可以先下载脚本，再指定仓库地址：

```bash
bash scripts/one_click_install.sh --repo-url /path/to/ask-math-oracle-mcp --google-key "$GOOGLE_API_KEY"
```

### 方案 B：clone 后一条命令

```bash
git clone https://github.com/imathwy/ask-math-oracle-mcp.git
cd ask-math-oracle-mcp
./scripts/quickstart.sh --google-key "$GOOGLE_API_KEY"
```

`quickstart.sh` 会自动：

1. 调用 `codex mcp add` 注册 `ask-math-oracle`
2. 写入 `startup_timeout_sec` 到当前 `CODEX_HOME/config.toml`
3. 回显最终注册结果

配置完成后请重启一次 Codex 会话（MCP 进程不会热更新）。

## 验证是否生效

```bash
codex mcp get ask-math-oracle
```

预期可见：

- `enabled: true`
- `command: python3 .../ask_math_oracle_mcp/server.py`
- 至少一个 `ASK_MATH_ORACLE_*_API_KEY`

## 工具调用示例

```json
{
  "problem": "I am stuck proving a monotonicity inequality.",
  "provider": "auto",
  "context": "current Lean goals ...",
  "attempted": "tried nlinarith and ring_nf",
  "style": "lean-friendly"
}
```

## 常见问题

`MCP startup failed: handshaking with MCP server failed: connection closed: initialize response`

- 确认使用本仓库最新版本（已兼容 JSONL / Content-Length 双向握手）
- 重启 Codex 会话再试

`provider=gemini` 但调用失败

- 先看 `codex mcp get ask-math-oracle` 是否存在 `ASK_MATH_ORACLE_GOOGLE_API_KEY`
- 若没有，重新执行：

```bash
./scripts/quickstart.sh --google-key "$GOOGLE_API_KEY"
```

## 本地开发自检

```bash
python3 scripts/smoke_test.py
python3 -m compileall ask_math_oracle_mcp
```
