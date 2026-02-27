#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def frame(message: dict[str, Any]) -> bytes:
    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
    return f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8") + payload


def frame_jsonl(message: dict[str, Any]) -> bytes:
    return (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")


def parse_frames(raw: bytes) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    pos = 0
    while pos < len(raw):
        sep = raw.find(b"\r\n\r\n", pos)
        if sep == -1:
            break
        header_blob = raw[pos:sep].decode("utf-8", errors="replace")
        pos = sep + 4

        length = 0
        for line in header_blob.split("\r\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key.strip().lower() == "content-length":
                length = int(value.strip())
                break
        if length <= 0:
            break
        body = raw[pos : pos + length]
        if len(body) != length:
            break
        pos += length
        out.append(json.loads(body.decode("utf-8")))
    return out


def parse_jsonl(raw: bytes) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    cmd = [sys.executable, "-m", "ask_math_oracle_mcp"]

    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "smoke-test", "version": "0.0.1"},
                "capabilities": {},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 10, "method": "resources/templates/list", "params": {}},
        {"jsonrpc": "2.0", "id": 11, "method": "resources/list", "params": {}},
        {"jsonrpc": "2.0", "id": 12, "method": "prompts/list", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "ask_math_oracle",
                "arguments": {
                    "problem": "Prove n + m = m + n for naturals.",
                    "provider": "both",
                    "dry_run": True,
                    "include_prompt_preview": True,
                },
            },
        },
    ]
    def run_one(payload: bytes, parser) -> tuple[bool, dict[str, Any], str, list[dict[str, Any]]]:
        proc = subprocess.run(
            cmd,
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(root),
            timeout=15,
        )
        responses = parser(proc.stdout)
        by_id = {resp.get("id"): resp for resp in responses if isinstance(resp, dict) and "id" in resp}
        ok = all(k in by_id for k in [1, 2, 3, 10, 11, 12])
        return ok, by_id, proc.stderr.decode("utf-8", errors="replace"), responses

    ok_a, by_id_a, err_a, responses_a = run_one(b"".join(frame(msg) for msg in requests), parse_frames)
    ok_b, by_id_b, err_b, responses_b = run_one(b"".join(frame_jsonl(msg) for msg in requests), parse_jsonl)
    # JSONL requests should receive JSONL responses.

    if ok_a and ok_b:
        print("smoke_test: PASS")
        print(json.dumps(by_id_a[3]["result"], ensure_ascii=False, indent=2))
        return 0

    print("content-length mode ok:", ok_a, file=sys.stderr)
    print("jsonl mode ok:", ok_b, file=sys.stderr)
    print("stderr (content-length):", file=sys.stderr)
    print(err_a, file=sys.stderr)
    print("stderr (jsonl):", file=sys.stderr)
    print(err_b, file=sys.stderr)
    print("parsed responses (content-length):", file=sys.stderr)
    print(json.dumps(responses_a, ensure_ascii=False, indent=2), file=sys.stderr)
    print("parsed responses (jsonl):", file=sys.stderr)
    print(json.dumps(responses_b, ensure_ascii=False, indent=2), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
