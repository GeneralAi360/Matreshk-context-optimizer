#!/usr/bin/env python3
"""Smoke coverage for Matreshka Native Context Telemetry v0.2."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from context_telemetry import antigravity, claude, codex


def J(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def codex_fixture(root: Path) -> Path:
    path = root / "sessions" / "2026" / "09" / "21" / "rollout-native-001.jsonl"
    info1 = {
        "model": "gpt-test",
        "model_context_window": 200000,
        "last_token_usage": {
            "input_tokens": 100,
            "cached_input_tokens": 20,
            "output_tokens": 40,
            "reasoning_output_tokens": 10,
            "total_tokens": 140,
        },
        "total_token_usage": {
            "input_tokens": 100,
            "cached_input_tokens": 20,
            "output_tokens": 40,
            "reasoning_output_tokens": 10,
            "total_tokens": 140,
        },
    }
    info2 = {
        "model": "gpt-test",
        "total_token_usage": {
            "input_tokens": 250,
            "cached_input_tokens": 40,
            "output_tokens": 100,
            "reasoning_output_tokens": 20,
            "total_tokens": 350,
        },
    }
    lines = [
        J({
            "type": "session_meta",
            "timestamp": "2026-09-21T10:00:00Z",
            "payload": {
                "cwd": "/work/proj",
                "originator": "codex-cli",
                "session_id": "native-001",
                "model": "gpt-test",
                "base_instructions": {"text": "system rules"},
            },
        }),
        J({"type": "turn_context", "timestamp": "2026-09-21T10:00:01Z", "payload": {"model": "gpt-test"}}),
        J({
            "type": "response_item",
            "timestamp": "2026-09-21T10:00:02Z",
            "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "do task"}]},
        }),
        J({
            "type": "response_item",
            "timestamp": "2026-09-21T10:00:03Z",
            "payload": {"type": "function_call", "name": "read_file", "arguments": J({"path": "/work/proj/a.py"})},
        }),
        J({
            "type": "response_item",
            "timestamp": "2026-09-21T10:00:04Z",
            "payload": {"type": "function_call", "name": "read_file", "arguments": J({"path": "/work/proj/a.py"})},
        }),
        J({
            "type": "response_item",
            "timestamp": "2026-09-21T10:00:05Z",
            "payload": {"type": "function_call", "name": "read_file", "arguments": J({"path": "/work/proj/.agents/skills/demo/SKILL.md"})},
        }),
        J({
            "type": "response_item",
            "timestamp": "2026-09-21T10:00:06Z",
            "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done"}]},
        }),
        J({"type": "event_msg", "timestamp": "2026-09-21T10:00:07Z", "payload": {"type": "token_count", "info": info1}}),
        # Exact duplicate must not count twice.
        J({"type": "event_msg", "timestamp": "2026-09-21T10:00:08Z", "payload": {"type": "token_count", "info": info1}}),
        # Cumulative-only usage is exact spend but not exact live context.
        J({"type": "event_msg", "timestamp": "2026-09-21T10:00:09Z", "payload": {"type": "token_count", "info": info2}}),
        J({
            "type": "compacted",
            "timestamp": "2026-09-21T10:00:10Z",
            "payload": {
                "message": "compact summary",
                "replacement_history": [
                    {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "seed after compact"}]}
                ],
            },
        }),
    ]
    write_lines(path, lines)

    archived = root / "archived_sessions" / "rollout-native-archived.jsonl"
    write_lines(
        archived,
        [
            J({
                "type": "session_meta",
                "timestamp": "2026-09-20T10:00:00Z",
                "payload": {"cwd": "/work/old", "session_id": "native-archived"},
            })
        ],
    )

    # Wrong active layout must never be discovered.
    write_lines(
        root / "sessions" / "bad-year" / "09" / "21" / "rollout-bad.jsonl",
        [J({"type": "session_meta", "payload": {}})],
    )
    return path


def claude_fixture(root: Path) -> Path:
    path = root / "-work-proj" / "claude-001.jsonl"
    lines = [
        J({
            "type": "user",
            "sessionId": "claude-001",
            "timestamp": "2026-09-21T10:00:00Z",
            "cwd": "/work/proj",
            "message": {"role": "user", "content": "do task"},
        }),
        J({
            "type": "assistant",
            "sessionId": "claude-001",
            "timestamp": "2026-09-21T10:00:01Z",
            "cwd": "/work/proj",
            "message": {
                "id": "msg-1",
                "role": "assistant",
                "model": "claude-test",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 10,
                    "cache_read_input_tokens": 50,
                },
                "content": [
                    {"type": "text", "text": "checking"},
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/work/proj/a.py"}},
                ],
            },
        }),
        # Duplicate streaming message id must be ignored.
        J({
            "type": "assistant",
            "sessionId": "claude-001",
            "timestamp": "2026-09-21T10:00:02Z",
            "cwd": "/work/proj",
            "message": {
                "id": "msg-1",
                "role": "assistant",
                "model": "claude-test",
                "usage": {"input_tokens": 100, "output_tokens": 20},
                "content": [{"type": "text", "text": "duplicate"}],
            },
        }),
        J({
            "type": "assistant",
            "sessionId": "claude-001",
            "timestamp": "2026-09-21T10:00:03Z",
            "cwd": "/work/proj",
            "message": {
                "id": "msg-2",
                "role": "assistant",
                "model": "claude-test",
                "usage": {"input_tokens": 120, "output_tokens": 30},
                "content": [{"type": "text", "text": "done"}],
            },
        }),
    ]
    write_lines(path, lines)
    return path


def antigravity_fixture(path: Path) -> None:
    rows = []
    for at, inp, out in [
        ("2026-09-21T10:00:00Z", 100, 10),
        ("2026-09-21T10:00:01Z", 200, 20),
        ("2026-09-21T10:00:02Z", 200, 20),
        ("2026-09-21T10:00:03Z", 300, 30),
    ]:
        rows.append(J({
            "at": at,
            "conversationId": "ag-1",
            "sessionId": "ag-session",
            "model": "gemini-test",
            "usage": {
                "inputTokens": inp,
                "outputTokens": out,
                "cacheCreationInputTokens": 0,
                "cacheReadInputTokens": 0,
            },
        }))
    write_lines(path, rows)


def run_cli(script: Path, *args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(proc.stdout)


def main() -> int:
    wrapper = SCRIPT_DIR / "native_telemetry.py"

    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp)

        codex_home = temp / "codex"
        codex_path = codex_fixture(codex_home)
        discovered = codex.discover_sessions(codex_home)
        assert {x["session_id"] for x in discovered} == {"native-001", "native-archived"}
        parsed = codex.parse_session(codex_path)
        assert parsed["usage"]["measurement_type"] == "PROVIDER_MEASURED"
        assert parsed["usage"]["measured_calls"] == 2
        assert parsed["usage"]["input_tokens"] == 250
        assert parsed["usage"]["output_tokens"] == 100
        assert parsed["usage"]["total_tokens"] == 350
        assert parsed["usage"]["reasoning_output_tokens"] == 20
        # Later cumulative-only event invalidates the earlier live-context number.
        assert parsed["context"]["reported_context_tokens"] is None
        assert parsed["context"]["context_window_tokens"] == 200000
        assert parsed["context"]["compactions"] == 1
        assert parsed["events"]["file_reads"].count("/work/proj/a.py") == 2
        assert "demo" in parsed["events"]["skills"]

        codex_report = run_cli(
            wrapper,
            "--provider", "codex",
            "--root", str(codex_home),
        )
        assert codex_report["engine"] == "Matreshka Context Telemetry"
        assert codex_report["cache"]["enabled"] is False
        assert codex_report["usage"]["total_tokens"] == 350
        assert any(x["category"] == "NATIVE_REPEATED_FILE_READS" for x in codex_report["findings"])
        assert codex_report["safety"]["network"] is False
        assert not (codex_home / ".context-optimizer").exists()

        cache_dir = temp / "cache"
        first_cached = run_cli(
            wrapper,
            "--provider", "codex",
            "--root", str(codex_home),
            "--use-cache",
            "--cache-dir", str(cache_dir),
        )
        second_cached = run_cli(
            wrapper,
            "--provider", "codex",
            "--root", str(codex_home),
            "--use-cache",
            "--cache-dir", str(cache_dir),
        )
        assert first_cached["cache"]["writes"] >= 1
        assert second_cached["cache"]["hits"] == second_cached["parsed_sessions"]
        assert cache_dir.exists()

        claude_root = temp / "claude-projects"
        claude_path = claude_fixture(claude_root)
        claude_parsed = claude.parse_session(claude_path)
        assert claude_parsed["usage"]["measured_calls"] == 2
        assert claude_parsed["usage"]["input_tokens"] == 220
        assert claude_parsed["usage"]["output_tokens"] == 50
        assert claude_parsed["usage"]["total_tokens"] == 330
        assert claude_parsed["context"]["reported_context_tokens"] == 120
        assert claude_parsed["events"]["file_reads"] == ["/work/proj/a.py"]

        ag_status = temp / "antigravity-statusline.jsonl"
        antigravity_fixture(ag_status)
        ag = antigravity.parse_statusline_file(ag_status)
        assert len(ag["sessions"]) == 1
        ag_session = ag["sessions"][0]
        assert ag_session["usage"]["measured_calls"] == 2
        assert ag_session["usage"]["input_tokens"] == 300
        assert ag_session["usage"]["output_tokens"] == 30
        assert ag_session["usage"]["total_tokens"] == 330
        assert ag_session["context"]["reported_context_tokens"] == 330
        assert ag_session["safety"]["rpc"] is False

        ag_discovery = run_cli(
            wrapper,
            "--provider", "antigravity",
            "--root", str(temp / "no-ag-home"),
        )
        assert ag_discovery["capability"] == "STATIC_DISCOVERY_ONLY"
        assert ag_discovery["safety"]["process_probe"] is False
        assert ag_discovery["safety"]["rpc"] is False

    print("PASS: native telemetry smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
