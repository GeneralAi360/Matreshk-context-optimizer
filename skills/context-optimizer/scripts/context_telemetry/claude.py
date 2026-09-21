from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .common import (
    aggregate_usage,
    basename_project,
    fingerprint,
    new_breakdown,
    number,
    safe_tool_args,
    skill_from_path,
    stringify_payload,
    utf8_bytes,
    walk_files,
)


def default_claude_projects_root() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        base = Path(override).expanduser().resolve()
        projects = base / "projects"
        return projects if projects.exists() else base
    return (Path.home() / ".claude" / "projects").resolve()


def discover_sessions(projects_root: Path | None = None) -> list[dict[str, Any]]:
    root = (projects_root or default_claude_projects_root()).expanduser().resolve()
    result: list[dict[str, Any]] = []
    for path in walk_files(root, ".jsonl"):
        fp = fingerprint(path)
        result.append({
            "provider": "claude",
            "path": str(path.resolve()),
            "session_id": path.stem,
            "project": path.parent.name,
            "mtime_ns": fp["mtime_ns"],
            "size_bytes": fp["size_bytes"],
        })
    result.sort(key=lambda item: int(item.get("mtime_ns") or 0), reverse=True)
    return result


def _usage(raw: dict[str, Any]) -> dict[str, int]:
    input_tokens = number(raw.get("input_tokens")) or 0
    output_tokens = number(raw.get("output_tokens")) or 0
    cache_create = number(raw.get("cache_creation_input_tokens")) or 0
    cache_read = number(raw.get("cache_read_input_tokens")) or 0
    return {
        "input_tokens": max(0, input_tokens),
        "cached_input_tokens": 0,
        "cache_creation_input_tokens": max(0, cache_create),
        "cache_read_input_tokens": max(0, cache_read),
        "output_tokens": max(0, output_tokens),
        "reasoning_output_tokens": 0,
        "total_tokens": max(0, input_tokens + cache_create + cache_read + output_tokens),
    }


def _add_tool_use(
    block: dict[str, Any],
    breakdown: dict[str, int],
    events: dict[str, list[str]],
) -> None:
    name = block.get("name")
    if not isinstance(name, str):
        name = "unknown"
    value = block.get("input")
    breakdown["tool_call_bytes"] += utf8_bytes(stringify_payload(value))
    events["tools"].append(name)
    if name == "Skill" and isinstance(value, dict):
        skill = value.get("skill") or value.get("name")
        if isinstance(skill, str) and skill:
            events["skills"].append(skill)
    if name.startswith("mcp__"):
        events["mcp_tools"].append(name)

    if name in {"Read", "read_file", "read"} and isinstance(value, dict):
        for key in ("file_path", "path", "filename"):
            path = value.get(key)
            if isinstance(path, str) and path:
                events["file_reads"].append(path)
                maybe_skill = skill_from_path(path)
                if maybe_skill:
                    events["skills"].append(maybe_skill)


def _content_bytes(
    content: Any,
    role: str,
    breakdown: dict[str, int],
    events: dict[str, list[str]],
) -> None:
    if isinstance(content, str):
        key = "user_text_bytes" if role == "user" else "assistant_text_bytes"
        breakdown[key] += utf8_bytes(content)
        return
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "")
        if block_type in {"text", "input_text", "output_text"}:
            text = block.get("text")
            if isinstance(text, str):
                key = "user_text_bytes" if role == "user" else "assistant_text_bytes"
                breakdown[key] += utf8_bytes(text)
        elif block_type == "tool_use":
            _add_tool_use(block, breakdown, events)
        elif block_type == "tool_result":
            breakdown["tool_result_bytes"] += utf8_bytes(stringify_payload(block.get("content")))


def parse_session(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    breakdown = new_breakdown()
    events: dict[str, list[str]] = {
        "tools": [],
        "file_reads": [],
        "skills": [],
        "mcp_tools": [],
    }
    seen_message_ids: set[str] = set()

    session_id = path.stem
    cwd: str | None = None
    project = path.parent.name
    model: str | None = None
    started_at: str | None = None
    updated_at: str | None = None
    current_input_context: int | None = None

    totals = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
    }
    measured_calls = 0

    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue

            entry_session = entry.get("sessionId")
            if isinstance(entry_session, str) and entry_session:
                session_id = entry_session
            if isinstance(entry.get("cwd"), str) and entry["cwd"]:
                cwd = entry["cwd"]
                project = basename_project(cwd)
            timestamp = entry.get("timestamp")
            if isinstance(timestamp, str):
                if started_at is None:
                    started_at = timestamp
                updated_at = timestamp

            entry_type = str(entry.get("type") or "")
            message = entry.get("message")
            if not isinstance(message, dict):
                continue

            role = str(message.get("role") or "")
            if entry_type == "user" or role == "user":
                _content_bytes(message.get("content"), "user", breakdown, events)
                continue

            if entry_type != "assistant" and role != "assistant":
                continue

            message_id = message.get("id")
            if isinstance(message_id, str) and message_id:
                if message_id in seen_message_ids:
                    continue
                seen_message_ids.add(message_id)

            if isinstance(message.get("model"), str) and message["model"]:
                model = message["model"]

            _content_bytes(message.get("content"), "assistant", breakdown, events)

            raw_usage = message.get("usage")
            if isinstance(raw_usage, dict):
                call = _usage(raw_usage)
                for key, value in call.items():
                    totals[key] += value
                measured_calls += 1
                # Anthropic request input may be split across normal/cache buckets.
                current_input_context = (
                    call["input_tokens"]
                    + call["cache_creation_input_tokens"]
                    + call["cache_read_input_tokens"]
                )

    fp = fingerprint(path)
    return {
        "provider": "claude",
        "session_id": session_id,
        "path": str(path),
        "archived": False,
        "cwd": cwd,
        "project": project,
        "model": model,
        "started_at": started_at,
        "updated_at": updated_at,
        "fingerprint": fp,
        "usage": {
            **totals,
            "measurement_type": "PROVIDER_MEASURED" if measured_calls else "UNKNOWN",
            "source": "Claude JSONL message.usage",
            "measured_calls": measured_calls,
        },
        "context": {
            "reported_context_tokens": current_input_context,
            "reported_context_measurement_type": "PROVIDER_MEASURED" if current_input_context is not None else "UNKNOWN",
            "reported_context_semantics": "LAST_REQUEST_INPUT",
            "context_window_tokens": None,
            "breakdown_unit": "bytes",
            "breakdown_bytes_full": breakdown,
            "breakdown_bytes_effective": breakdown,
            "compactions": 0,
        },
        "events": events,
    }
