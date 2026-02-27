from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SERVER_NAME = "ask-math-oracle"
SERVER_VERSION = "0.1.0"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2024-11-05", "2024-10-07")
NO_ID = object()

TOOL_NAME = "ask_math_oracle"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_ANTHROPIC_API_VERSION = "2023-06-01"
DEFAULT_OPENAI_MODEL = "gpt-5-pro"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-1"
DEFAULT_GEMINI_MODEL = "gemini-2.5-pro"
DEFAULT_TIMEOUT_SEC = 180.0
FRAME_CONTENT_LENGTH = "content-length"
FRAME_JSONL = "jsonl"


TOOL_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "problem": {
            "type": "string",
            "description": "The exact math blocker/question that needs help.",
        },
        "context": {
            "type": "string",
            "description": "Optional background context (code, theorem state, constraints).",
        },
        "goal": {
            "type": "string",
            "description": "Optional target outcome expected from the oracle answer.",
        },
        "attempted": {
            "type": "string",
            "description": "Optional summary of attempts that already failed.",
        },
        "provider": {
            "type": "string",
            "enum": ["auto", "openai", "anthropic", "gemini", "both", "all"],
            "description": (
                "Model provider selection. "
                "`auto` chooses based on available keys. "
                "`both` calls OpenAI+Gemini. `all` calls OpenAI+Anthropic+Gemini."
            ),
            "default": "auto",
        },
        "openai_model": {
            "type": "string",
            "description": "Override OpenAI model name. Default: gpt-5-pro.",
        },
        "anthropic_model": {
            "type": "string",
            "description": "Override Anthropic model name. Default: claude-opus-4-1.",
        },
        "gemini_model": {
            "type": "string",
            "description": "Override Gemini model name. Default: gemini-2.5-pro.",
        },
        "style": {
            "type": "string",
            "enum": ["direct", "detailed", "proof-sketch", "lean-friendly"],
            "description": "Response style for the oracle.",
            "default": "lean-friendly",
        },
        "max_output_tokens": {
            "type": "integer",
            "description": "Maximum output tokens for model generation.",
            "minimum": 128,
            "maximum": 32000,
            "default": 1200,
        },
        "temperature": {
            "type": "number",
            "description": "Sampling temperature (0.0 - 2.0).",
            "minimum": 0.0,
            "maximum": 2.0,
            "default": 0.2,
        },
        "reasoning_effort": {
            "type": "string",
            "enum": ["minimal", "low", "medium", "high", "xhigh"],
            "description": "Optional OpenAI reasoning effort hint.",
        },
        "allow_fallback": {
            "type": "boolean",
            "description": "When `provider=auto`, fallback to the other provider on failure.",
            "default": True,
        },
        "include_prompt_preview": {
            "type": "boolean",
            "description": "Include the final system/user prompts in structured output.",
            "default": False,
        },
        "dry_run": {
            "type": "boolean",
            "description": "Do not call external APIs; return provider plan and prompt preview only.",
            "default": False,
        },
    },
    "required": ["problem"],
}


class JsonRpcError(Exception):
    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def _log(message: str) -> None:
    print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)


def _debug_enabled() -> bool:
    v = (os.getenv("ASK_MATH_ORACLE_DEBUG_MCP") or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def _debug(message: str) -> None:
    if _debug_enabled():
        _log(f"DEBUG {message}")


def _json_dumps(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _read_message() -> tuple[dict[str, Any], str] | None:
    # Support two common stdio framings:
    # 1) Content-Length headers (LSP-style)
    # 2) JSON object per line (JSONL / rmcp-style variants)
    first_line: bytes | None = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            continue
        first_line = line
        break

    stripped = first_line.strip()
    if stripped.startswith(b"{") or stripped.startswith(b"["):
        try:
            parsed = json.loads(stripped.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise JsonRpcError(-32700, f"Invalid JSON line: {exc}") from exc
        if not isinstance(parsed, dict):
            raise JsonRpcError(-32600, "JSON-RPC payload must be an object")
        _debug("received JSONL-framed message")
        return parsed, FRAME_JSONL

    headers: dict[str, str] = {}

    def add_header(raw_line: bytes) -> None:
        text = raw_line.decode("utf-8", errors="replace").strip()
        if not text or ":" not in text:
            return
        key, value = text.split(":", 1)
        headers[key.strip().lower()] = value.strip()

    add_header(first_line)
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        add_header(line)

    content_length_raw = headers.get("content-length")
    if content_length_raw is None:
        raise JsonRpcError(-32700, "Missing Content-Length header.")
    try:
        content_length = int(content_length_raw)
    except ValueError as exc:
        raise JsonRpcError(-32700, f"Invalid Content-Length header: {content_length_raw}") from exc
    if content_length < 0:
        raise JsonRpcError(-32700, "Negative Content-Length is invalid")

    body = sys.stdin.buffer.read(content_length)
    if len(body) != content_length:
        return None
    if not body:
        return {}, FRAME_CONTENT_LENGTH
    try:
        parsed = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise JsonRpcError(-32700, f"Invalid JSON body: {exc}") from exc
    if not isinstance(parsed, dict):
        raise JsonRpcError(-32600, "JSON-RPC payload must be an object")
    _debug("received Content-Length-framed message")
    return parsed, FRAME_CONTENT_LENGTH


def _write_message(payload: dict[str, Any], *, frame: str = FRAME_CONTENT_LENGTH) -> None:
    raw = _json_dumps(payload)
    if frame == FRAME_JSONL:
        sys.stdout.buffer.write(raw + b"\n")
        sys.stdout.buffer.flush()
        return
    header = f"Content-Length: {len(raw)}\r\n\r\n".encode("utf-8")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def _coerce_str(value: Any, *, default: str | None = None) -> str | None:
    if value is None:
        return default
    if isinstance(value, str):
        v = value.strip()
        return v if v else default
    return default


def _require_non_empty_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"`{field}` must be a non-empty string.")
    return value.strip()


def _coerce_float(value: Any, *, default: float, min_v: float, max_v: float) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        out = float(value)
    elif isinstance(value, str):
        out = float(value.strip())
    else:
        raise ValueError("temperature must be a number.")
    if out < min_v or out > max_v:
        raise ValueError(f"temperature must be in [{min_v}, {max_v}].")
    return out


def _coerce_int(value: Any, *, default: int, min_v: int, max_v: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError("max_output_tokens must be an integer.")
    if isinstance(value, int):
        out = value
    elif isinstance(value, str):
        out = int(value.strip())
    else:
        raise ValueError("max_output_tokens must be an integer.")
    if out < min_v or out > max_v:
        raise ValueError(f"max_output_tokens must be in [{min_v}, {max_v}].")
    return out


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "on"}:
            return True
        if v in {"0", "false", "no", "n", "off"}:
            return False
    raise ValueError("Expected a boolean value.")


def _http_post_json(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_sec: float,
) -> tuple[int, dict[str, Any]]:
    body = _json_dumps(payload)
    final_headers = {"content-type": "application/json", **headers}
    req = Request(url, data=body, headers=final_headers, method="POST")
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"raw": raw}
            return resp.status, parsed
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed
    except URLError as exc:
        return 599, {"error": str(exc)}


def _extract_error_message(payload: dict[str, Any]) -> str:
    err = payload.get("error")
    if isinstance(err, str):
        return err
    if isinstance(err, dict):
        message = err.get("message")
        if isinstance(message, str) and message:
            return message
    raw = payload.get("raw")
    if isinstance(raw, str) and raw:
        return raw
    return json.dumps(payload, ensure_ascii=False)


def _extract_openai_output_text(response: dict[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts: list[str] = []
    output = response.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for piece in content:
                if not isinstance(piece, dict):
                    continue
                if piece.get("type") in {"output_text", "text"}:
                    text = piece.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
    if parts:
        return "\n".join(parts).strip()

    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()

    raise RuntimeError("OpenAI response did not contain text output.")


def _extract_gemini_output_text(response: dict[str, Any]) -> str:
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("Gemini response missing candidates.")

    text_parts: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content")
        if not isinstance(content, dict):
            continue
        parts = content.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    text_parts.append(text.strip())

    if not text_parts:
        block_reason = ""
        prompt_feedback = response.get("promptFeedback")
        if isinstance(prompt_feedback, dict):
            reason = prompt_feedback.get("blockReason")
            if isinstance(reason, str) and reason:
                block_reason = f" (blockReason={reason})"
        finish_reasons: list[str] = []
        for candidate in candidates:
            if isinstance(candidate, dict):
                reason = candidate.get("finishReason")
                if isinstance(reason, str) and reason:
                    finish_reasons.append(reason)
        if finish_reasons:
            block_reason += f" (finishReason={','.join(finish_reasons)})"
        raise RuntimeError("Gemini response did not contain text output." + block_reason)
    return "\n".join(text_parts).strip()


def _extract_anthropic_output_text(response: dict[str, Any]) -> str:
    content = response.get("content")
    if not isinstance(content, list):
        raise RuntimeError("Anthropic response missing content blocks.")
    text_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            text_parts.append(text.strip())
    if not text_parts:
        raise RuntimeError("Anthropic response did not contain text output.")
    return "\n".join(text_parts).strip()


@dataclass
class OracleConfig:
    openai_api_key: str | None
    anthropic_api_key: str | None
    google_api_key: str | None
    openai_base_url: str
    anthropic_base_url: str
    anthropic_api_version: str
    timeout_sec: float

    @classmethod
    def from_env(cls) -> "OracleConfig":
        openai_api_key = _coerce_str(
            os.getenv("ASK_MATH_ORACLE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"),
            default=None,
        )
        anthropic_api_key = _coerce_str(
            os.getenv("ASK_MATH_ORACLE_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY"),
            default=None,
        )
        google_api_key = _coerce_str(
            os.getenv("ASK_MATH_ORACLE_GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY"),
            default=None,
        )
        openai_base_url = (
            _coerce_str(
                os.getenv("ASK_MATH_ORACLE_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
                default=DEFAULT_OPENAI_BASE_URL,
            )
            or DEFAULT_OPENAI_BASE_URL
        )
        anthropic_base_url = (
            _coerce_str(
                os.getenv("ASK_MATH_ORACLE_ANTHROPIC_BASE_URL"),
                default=DEFAULT_ANTHROPIC_BASE_URL,
            )
            or DEFAULT_ANTHROPIC_BASE_URL
        )
        anthropic_api_version = (
            _coerce_str(
                os.getenv("ASK_MATH_ORACLE_ANTHROPIC_VERSION")
                or os.getenv("ANTHROPIC_VERSION"),
                default=DEFAULT_ANTHROPIC_API_VERSION,
            )
            or DEFAULT_ANTHROPIC_API_VERSION
        )
        timeout_raw = _coerce_str(os.getenv("ASK_MATH_ORACLE_TIMEOUT_SEC"), default=None)
        timeout_sec = DEFAULT_TIMEOUT_SEC
        if timeout_raw is not None:
            timeout_sec = max(5.0, min(600.0, float(timeout_raw)))
        return cls(
            openai_api_key=openai_api_key,
            anthropic_api_key=anthropic_api_key,
            google_api_key=google_api_key,
            openai_base_url=openai_base_url,
            anthropic_base_url=anthropic_base_url,
            anthropic_api_version=anthropic_api_version,
            timeout_sec=timeout_sec,
        )


class MathOracle:
    def __init__(self, cfg: OracleConfig) -> None:
        self.cfg = cfg

    def ask(self, arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        problem = _require_non_empty_str(arguments.get("problem"), field="problem")
        context = _coerce_str(arguments.get("context"), default="")
        goal = _coerce_str(arguments.get("goal"), default="")
        attempted = _coerce_str(arguments.get("attempted"), default="")

        provider = (_coerce_str(arguments.get("provider"), default="auto") or "auto").lower()
        if provider not in {"auto", "openai", "anthropic", "gemini", "both", "all"}:
            raise ValueError("provider must be one of: auto, openai, anthropic, gemini, both, all.")

        style = (_coerce_str(arguments.get("style"), default="lean-friendly") or "lean-friendly").lower()
        if style not in {"direct", "detailed", "proof-sketch", "lean-friendly"}:
            raise ValueError("style must be one of: direct, detailed, proof-sketch, lean-friendly.")

        max_output_tokens = _coerce_int(
            arguments.get("max_output_tokens"),
            default=1200,
            min_v=128,
            max_v=32000,
        )
        temperature = _coerce_float(
            arguments.get("temperature"),
            default=0.2,
            min_v=0.0,
            max_v=2.0,
        )
        dry_run = _coerce_bool(arguments.get("dry_run"), default=False)
        allow_fallback = _coerce_bool(arguments.get("allow_fallback"), default=True)
        include_prompt_preview = _coerce_bool(arguments.get("include_prompt_preview"), default=False)

        openai_model = _coerce_str(
            arguments.get("openai_model") or os.getenv("ASK_MATH_ORACLE_OPENAI_MODEL"),
            default=DEFAULT_OPENAI_MODEL,
        )
        anthropic_model = _coerce_str(
            arguments.get("anthropic_model") or os.getenv("ASK_MATH_ORACLE_ANTHROPIC_MODEL"),
            default=DEFAULT_ANTHROPIC_MODEL,
        )
        gemini_model = _coerce_str(
            arguments.get("gemini_model") or os.getenv("ASK_MATH_ORACLE_GEMINI_MODEL"),
            default=DEFAULT_GEMINI_MODEL,
        )
        reasoning_effort = _coerce_str(
            arguments.get("reasoning_effort") or os.getenv("ASK_MATH_ORACLE_REASONING_EFFORT"),
            default=None,
        )

        system_prompt, user_prompt = _build_prompts(
            problem=problem,
            context=context or "",
            goal=goal or "",
            attempted=attempted or "",
            style=style,
        )

        if dry_run:
            plan = _dry_run_plan(provider)
            preview = {
                "provider_requested": provider,
                "provider_plan": plan,
                "dry_run": True,
                "model_defaults": {
                    "openai": openai_model,
                    "anthropic": anthropic_model,
                    "gemini": gemini_model,
                },
                "prompt_preview": {"system": system_prompt, "user": user_prompt},
                "key_presence": {
                    "openai": bool(self.cfg.openai_api_key),
                    "anthropic": bool(self.cfg.anthropic_api_key),
                    "gemini": bool(self.cfg.google_api_key),
                },
            }
            text = "\n".join(
                [
                    "DRY RUN: no external API call executed.",
                    f"provider_requested={provider}",
                    f"provider_plan={','.join(plan)}",
                    f"openai_key_present={bool(self.cfg.openai_api_key)}",
                    f"anthropic_key_present={bool(self.cfg.anthropic_api_key)}",
                    f"gemini_key_present={bool(self.cfg.google_api_key)}",
                ]
            )
            return text, preview

        call_order, preflight_warnings = self._resolve_call_order(
            provider=provider,
            allow_fallback=allow_fallback,
        )
        responses: list[dict[str, Any]] = []
        errors: list[str] = list(preflight_warnings)

        if provider in {"both", "all"}:
            for name in call_order:
                try:
                    responses.append(
                        self._call_provider(
                            provider=name,
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            openai_model=openai_model or DEFAULT_OPENAI_MODEL,
                            anthropic_model=anthropic_model or DEFAULT_ANTHROPIC_MODEL,
                            gemini_model=gemini_model or DEFAULT_GEMINI_MODEL,
                            max_output_tokens=max_output_tokens,
                            temperature=temperature,
                            reasoning_effort=reasoning_effort,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{name}: {exc}")
            if not responses:
                raise RuntimeError("all providers failed: " + " | ".join(errors))
        else:
            for name in call_order:
                try:
                    responses.append(
                        self._call_provider(
                            provider=name,
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            openai_model=openai_model or DEFAULT_OPENAI_MODEL,
                            anthropic_model=anthropic_model or DEFAULT_ANTHROPIC_MODEL,
                            gemini_model=gemini_model or DEFAULT_GEMINI_MODEL,
                            max_output_tokens=max_output_tokens,
                            temperature=temperature,
                            reasoning_effort=reasoning_effort,
                        )
                    )
                    break
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{name}: {exc}")
            if not responses:
                raise RuntimeError("provider call failed: " + " | ".join(errors))

        if provider in {"both", "all"} and len(responses) > 1:
            rendered = "\n\n".join(
                [f"## {item['provider']} ({item['model']})\n{item['text']}" for item in responses]
            )
            provider_used = provider
        else:
            rendered = responses[0]["text"]
            provider_used = responses[0]["provider"]

        if errors:
            rendered += "\n\n---\nWarnings:\n" + "\n".join(f"- {msg}" for msg in errors)

        structured: dict[str, Any] = {
            "provider_requested": provider,
            "provider_used": provider_used,
            "responses": [
                {
                    "provider": item["provider"],
                    "model": item["model"],
                    "text": item["text"],
                }
                for item in responses
            ],
            "warnings": errors,
            "dry_run": False,
        }
        if include_prompt_preview:
            structured["prompt_preview"] = {"system": system_prompt, "user": user_prompt}
        return rendered, structured

    def _resolve_call_order(self, *, provider: str, allow_fallback: bool) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        openai_ready = bool(self.cfg.openai_api_key)
        anthropic_ready = bool(self.cfg.anthropic_api_key)
        gemini_ready = bool(self.cfg.google_api_key)

        if provider == "openai":
            if not openai_ready:
                raise RuntimeError("Missing ASK_MATH_ORACLE_OPENAI_API_KEY (or OPENAI_API_KEY).")
            return ["openai"], warnings

        if provider == "anthropic":
            if not anthropic_ready:
                raise RuntimeError("Missing ASK_MATH_ORACLE_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY).")
            return ["anthropic"], warnings

        if provider == "gemini":
            if not gemini_ready:
                raise RuntimeError("Missing ASK_MATH_ORACLE_GOOGLE_API_KEY (or GOOGLE_API_KEY).")
            return ["gemini"], warnings

        if provider == "both":
            order: list[str] = []
            if openai_ready:
                order.append("openai")
            else:
                warnings.append("openai key missing")
            if gemini_ready:
                order.append("gemini")
            else:
                warnings.append("gemini key missing")
            if not order:
                raise RuntimeError("No provider API keys found for provider=both.")
            return order, warnings

        if provider == "all":
            order = []
            if openai_ready:
                order.append("openai")
            else:
                warnings.append("openai key missing")
            if anthropic_ready:
                order.append("anthropic")
            else:
                warnings.append("anthropic key missing")
            if gemini_ready:
                order.append("gemini")
            else:
                warnings.append("gemini key missing")
            if not order:
                raise RuntimeError("No provider API keys found for provider=all.")
            return order, warnings

        # provider == auto
        ordered_available = [p for p, ok in [("anthropic", anthropic_ready), ("openai", openai_ready), ("gemini", gemini_ready)] if ok]
        if len(ordered_available) >= 2:
            if allow_fallback:
                return ordered_available, warnings
            return [ordered_available[0]], warnings
        if len(ordered_available) == 1:
            return ordered_available, warnings
        raise RuntimeError(
            "No provider key available. Set ASK_MATH_ORACLE_OPENAI_API_KEY/OPENAI_API_KEY, "
            "ASK_MATH_ORACLE_ANTHROPIC_API_KEY/ANTHROPIC_API_KEY, or "
            "ASK_MATH_ORACLE_GOOGLE_API_KEY/GOOGLE_API_KEY."
        )

    def _call_provider(
        self,
        *,
        provider: str,
        system_prompt: str,
        user_prompt: str,
        openai_model: str,
        anthropic_model: str,
        gemini_model: str,
        max_output_tokens: int,
        temperature: float,
        reasoning_effort: str | None,
    ) -> dict[str, str]:
        if provider == "openai":
            text = self._call_openai(
                model=openai_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
            )
            return {"provider": "openai", "model": openai_model, "text": text}

        if provider == "anthropic":
            text = self._call_anthropic(
                model=anthropic_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
            )
            return {"provider": "anthropic", "model": anthropic_model, "text": text}

        if provider == "gemini":
            text = self._call_gemini(
                model=gemini_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
            )
            return {"provider": "gemini", "model": gemini_model, "text": text}

        raise RuntimeError(f"Unsupported provider: {provider}")

    def _call_openai(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float,
        reasoning_effort: str | None,
    ) -> str:
        key = self.cfg.openai_api_key
        if not key:
            raise RuntimeError("Missing OpenAI API key.")
        endpoint = self.cfg.openai_base_url.rstrip("/") + "/responses"
        payload: dict[str, Any] = {
            "model": model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
        }
        if reasoning_effort is not None:
            payload["reasoning"] = {"effort": reasoning_effort}

        status, response = self._openai_post(endpoint=endpoint, key=key, payload=payload)
        if status >= HTTPStatus.BAD_REQUEST and self._is_unsupported_temperature_error(response):
            payload.pop("temperature", None)
            status, response = self._openai_post(endpoint=endpoint, key=key, payload=payload)
        if status >= HTTPStatus.BAD_REQUEST:
            msg = _extract_error_message(response)
            raise RuntimeError(f"OpenAI API error {status}: {msg}")
        return _extract_openai_output_text(response)

    def _openai_post(self, *, endpoint: str, key: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _http_post_json(
            url=endpoint,
            headers={"authorization": f"Bearer {key}"},
            payload=payload,
            timeout_sec=self.cfg.timeout_sec,
        )

    def _is_unsupported_temperature_error(self, response: dict[str, Any]) -> bool:
        msg = _extract_error_message(response).lower()
        return "unsupported parameter" in msg and "temperature" in msg

    def _call_anthropic(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> str:
        key = self.cfg.anthropic_api_key
        if not key:
            raise RuntimeError("Missing Anthropic API key.")
        endpoint = self.cfg.anthropic_base_url.rstrip("/") + "/v1/messages"
        payload: dict[str, Any] = {
            "model": model,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_prompt}],
                }
            ],
            "max_tokens": max_output_tokens,
            "temperature": temperature,
        }
        status, response = _http_post_json(
            url=endpoint,
            headers={
                "x-api-key": key,
                "anthropic-version": self.cfg.anthropic_api_version,
            },
            payload=payload,
            timeout_sec=self.cfg.timeout_sec,
        )
        if status >= HTTPStatus.BAD_REQUEST:
            msg = _extract_error_message(response)
            raise RuntimeError(f"Anthropic API error {status}: {msg}")
        return _extract_anthropic_output_text(response)

    def _call_gemini(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> str:
        key = self.cfg.google_api_key
        if not key:
            raise RuntimeError("Missing Google API key.")
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        )
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_output_tokens,
                "temperature": temperature,
            },
        }
        status, response = _http_post_json(
            url=endpoint,
            headers={},
            payload=payload,
            timeout_sec=self.cfg.timeout_sec,
        )
        if status >= HTTPStatus.BAD_REQUEST:
            msg = _extract_error_message(response)
            raise RuntimeError(f"Gemini API error {status}: {msg}")
        try:
            return _extract_gemini_output_text(response)
        except RuntimeError as exc:
            # Gemini can occasionally consume the token budget without yielding text parts.
            # Retry once with a larger generation budget.
            if "finishReason=MAX_TOKENS" not in str(exc):
                raise
            retry_tokens = min(max(max_output_tokens * 4, 2048), 8192)
            if retry_tokens <= max_output_tokens:
                raise
            payload_retry = dict(payload)
            payload_retry["generationConfig"] = dict(payload["generationConfig"])
            payload_retry["generationConfig"]["maxOutputTokens"] = retry_tokens
            status2, response2 = _http_post_json(
                url=endpoint,
                headers={},
                payload=payload_retry,
                timeout_sec=self.cfg.timeout_sec,
            )
            if status2 >= HTTPStatus.BAD_REQUEST:
                msg = _extract_error_message(response2)
                raise RuntimeError(f"Gemini API error {status2}: {msg}") from exc
            return _extract_gemini_output_text(response2)


def _dry_run_plan(provider: str) -> list[str]:
    if provider == "openai":
        return ["openai"]
    if provider == "anthropic":
        return ["anthropic"]
    if provider == "gemini":
        return ["gemini"]
    if provider == "both":
        return ["openai", "gemini"]
    if provider == "all":
        return ["openai", "anthropic", "gemini"]
    return ["anthropic", "openai", "gemini"]


def _build_prompts(
    *,
    problem: str,
    context: str,
    goal: str,
    attempted: str,
    style: str,
) -> tuple[str, str]:
    style_instruction = {
        "direct": "Keep the answer concise and tactical.",
        "detailed": "Give a detailed reasoning path with clear assumptions.",
        "proof-sketch": "Focus on a mathematically rigorous proof sketch.",
        "lean-friendly": (
            "Prioritize Lean-friendly decomposition: identify lemmas, algebraic rewrites, "
            "and concrete tactic-level next steps."
        ),
    }[style]
    system_prompt = "\n".join(
        [
            "You are a senior mathematician helping unblock an engineering workflow.",
            "The user needs correctness and actionable next steps, not vague advice.",
            style_instruction,
            "If assumptions are missing, state them explicitly.",
            "If the statement seems false, provide a counterexample and a corrected statement.",
            "Output format: (1) Core insight (2) Next 3-7 steps (3) Pitfalls/checks.",
        ]
    )

    sections = [f"[Problem]\n{problem.strip()}"]
    if goal.strip():
        sections.append(f"[Goal]\n{goal.strip()}")
    if attempted.strip():
        sections.append(f"[Attempted]\n{attempted.strip()}")
    if context.strip():
        sections.append(f"[Context]\n{context.strip()}")
    user_prompt = "\n\n".join(sections).strip()
    return system_prompt, user_prompt


class AskMathOracleMcpServer:
    def __init__(self) -> None:
        self._initialized = False
        self._oracle = MathOracle(OracleConfig.from_env())

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        if request.get("jsonrpc") != "2.0":
            raise JsonRpcError(-32600, "jsonrpc must be '2.0'.")
        method = request.get("method")
        if not isinstance(method, str):
            raise JsonRpcError(-32600, "Missing method.")
        _debug(f"method={method}")

        request_id = request["id"] if "id" in request else NO_ID
        params = request.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise JsonRpcError(-32602, "params must be an object.")

        if method == "notifications/initialized":
            self._initialized = True
            return None

        if method == "initialize":
            result = self._on_initialize(params)
            return _success_response(request_id, result)

        if method == "ping":
            return _success_response(request_id, {})

        if method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": TOOL_NAME,
                        "description": (
                            "Ask external math-capable models (OpenAI/Anthropic/Gemini) for blocker resolution."
                        ),
                        "inputSchema": TOOL_INPUT_SCHEMA,
                    }
                ]
            }
            return _success_response(request_id, result)

        if method == "resources/list":
            return _success_response(request_id, {"resources": []})

        if method == "resources/templates/list":
            return _success_response(request_id, {"resourceTemplates": []})

        if method == "prompts/list":
            return _success_response(request_id, {"prompts": []})

        if method == "tools/call":
            result = self._on_tools_call(params)
            return _success_response(request_id, result)

        if request_id is NO_ID:
            return None
        raise JsonRpcError(-32601, f"Method not found: {method}")

    def _on_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        client_protocol = params.get("protocolVersion")
        if isinstance(client_protocol, str) and client_protocol.strip():
            protocol = client_protocol
        else:
            protocol = SUPPORTED_PROTOCOLS[0]
        return {
            "protocolVersion": protocol,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }

    def _on_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if name != TOOL_NAME:
            raise JsonRpcError(-32602, f"Unknown tool: {name}")
        arguments = params.get("arguments")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise JsonRpcError(-32602, "tools/call.arguments must be an object.")

        try:
            rendered, structured = self._oracle.ask(arguments)
            return {
                "content": [{"type": "text", "text": rendered}],
                "structuredContent": structured,
                "isError": False,
            }
        except Exception as exc:  # noqa: BLE001
            error_msg = f"{type(exc).__name__}: {exc}"
            return {
                "content": [{"type": "text", "text": error_msg}],
                "structuredContent": {"error": error_msg},
                "isError": True,
            }


def _success_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any] | None:
    if request_id is NO_ID:
        return None
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error_response(request_id: Any, error: JsonRpcError) -> dict[str, Any] | None:
    if request_id is NO_ID:
        request_id = None
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": error.code,
            "message": error.message,
        },
    }
    if error.data is not None:
        payload["error"]["data"] = error.data
    return payload


def main() -> None:
    server = AskMathOracleMcpServer()
    response_frame = FRAME_CONTENT_LENGTH
    _log(f"starting {SERVER_NAME} v{SERVER_VERSION}")
    while True:
        try:
            incoming = _read_message()
            if incoming is None:
                _log("stdin closed, exiting")
                return
            request, response_frame = incoming

            try:
                response = server.handle(request)
            except JsonRpcError as exc:
                req_id = request["id"] if isinstance(request, dict) and "id" in request else NO_ID
                response = _error_response(req_id, exc)
            except Exception as exc:  # noqa: BLE001
                req_id = request["id"] if isinstance(request, dict) and "id" in request else NO_ID
                _log(f"unhandled error: {exc}\n{traceback.format_exc()}")
                response = _error_response(
                    req_id,
                    JsonRpcError(-32603, "Internal error", data={"detail": str(exc)}),
                )

            if response is not None:
                _write_message(response, frame=response_frame)
        except JsonRpcError as exc:
            resp = _error_response(NO_ID, exc)
            if resp is not None:
                _write_message(resp, frame=response_frame)
        except Exception as exc:  # noqa: BLE001
            _log(f"fatal error: {exc}\n{traceback.format_exc()}")
            return


if __name__ == "__main__":
    main()
