from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .common import (
    basename_project,
    canonical_json,
    extract_shell_read_paths,
    fingerprint,
    is_meta_user_text,
    new_breakdown,
    number,
    safe_json_loads,
    safe_tool_args,
    skill_from_path,
    stringify_payload,
    text_from_blocks,
    utf8_bytes,
)

FIRST_LINE_READ_CAP = 1024 * 1024
YEAR_RE = re.compile(r"^\d{4}$")
MONTH_DAY_RE = re.compile(r"^\d{2}$")
ROLLOUT_RE = re.compile(r"^rollout-.*\.jsonl$")


def default_codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser().resolve()


def _read_first_line(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("rb") as stream:
            raw = stream.readline(FIRST_LINE_READ_CAP + 1)
    except OSError:
        return None
    if not raw or len(raw) > FIRST_LINE_READ_CAP or b"\n" not in raw:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    payload = value.get("payload")
    if value.get("type") != "session_meta" or not isinstance(payload, dict):
        return None
    return value


def _strict_active_files(root: Path) -> list[Path]:
    sessions = root / "sessions"
    if not sessions.exists():
        return []
    result: list[Path] = []
    try:
        years = list(sessions.iterdir())
    except OSError:
        return []
    for year in years:
        if not year.is_dir() or not YEAR_RE.match(year.name):
            continue
        try:
            months = list(year.iterdir())
        except OSError:
            continue
        for month in months:
            if not month.is_dir() or not MONTH_DAY_RE.match(month.name):
                continue
            try:
                days = list(month.iterdir())
            except OSError:
                continue
            for day in days:
                if not day.is_dir() or not MONTH_DAY_RE.match(day.name):
                    continue
                try:
                    files = list(day.iterdir())
                except OSError:
                    continue
                result.extend(
                    path for path in files
                    if path.is_file() and ROLLOUT_RE.match(path.name)
                )
    return result


def _archived_files(root: Path) -> list[Path]:
    archived = root / "archived_sessions"
    if not archived.exists():
        return []
    try:
        return [
            path for path in archived.iterdir()
            if path.is_file() and ROLLOUT_RE.match(path.name)
        ]
    except OSError:
        return []


def discover_sessions(codex_home: Path | None = None) -> list[dict[str, Any]]:
    root = (codex_home or default_codex_home()).expanduser().resolve()
    active = [(path, False) for path in _strict_active_files(root)]
    archived = [(path, True) for path in _archived_files(root)]
    result: list[dict[str, Any]] = []

    for path, is_archived in active + archived:
        first = _read_first_line(path)
        if first is None:
            continue
        payload = first.get("payload") or {}
        cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
        session_id = payload.get("id") or payload.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            session_id = path.stem.removeprefix("rollout-")
        fp = fingerprint(path)
        result.append({
            "provider": "codex",
            "path": str(path.resolve()),
            "session_id": session_id,
            "cwd": cwd,
            "project": basename_project(cwd),
            "archived": is_archived,
            "originator": payload.get("originator") if isinstance(payload.get("originator"), str) else None,
            "model_provider": payload.get("model_provider") if isinstance(payload.get("model_provider"), str) else None,
            "mtime_ns": fp["mtime_ns"],
            "size_bytes": fp["size_bytes"],
        })

    result.sort(key=lambda item: int(item.get("mtime_ns") or 0), reverse=True)
    return result


def _usage_fields(raw: dict[str, Any]) -> dict[str, int]:
    input_tokens = number(raw.get("input_tokens")) or 0
    cached = number(raw.get("cached_input_tokens")) or 0
    output = number(raw.get("output_tokens")) or 0
    reasoning = number(raw.get("reasoning_output_tokens")) or 0
    cache_write = number(raw.get("cache_write_input_tokens")) or 0
    total = number(raw.get("total_tokens"))
    if total is None:
        # OpenAI reasoning is included in output_tokens, so never add it again.
        total = input_tokens + output
    return {
        "input_tokens": max(0, input_tokens),
        "cached_input_tokens": max(0, cached),
        "cache_creation_input_tokens": max(0, cache_write),
        "cache_read_input_tokens": 0,
        "output_tokens": max(0, output),
        "reasoning_output_tokens": max(0, reasoning),
        "total_tokens": max(0, total),
    }


def _delta_usage(current: dict[str, Any], previous: dict[str, int] | None) -> dict[str, int]:
    now = _usage_fields(current)
    if previous is None:
        return now
    result: dict[str, int] = {}
    for key, value in now.items():
        prior = previous.get(key, 0)
        # A reset/decrease is treated as a new baseline rather than a negative call.
        result[key] = value - prior if value >= prior else value
    return result


def _add_text_bytes(breakdown: dict[str, int], key: str, value: str) -> None:
    breakdown[key] += utf8_bytes(value)


def _command_text(args: Any) -> str:
    if isinstance(args, str):
        return args
    if isinstance(args, list):
        return " ".join(str(x) for x in args if isinstance(x, (str, int, float)))
    if isinstance(args, dict):
        for key in ("command", "cmd", "argv"):
            value = args.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                return " ".join(str(x) for x in value if isinstance(x, (str, int, float)))
    return ""


def _extract_read_path_from_args(args: Any) -> list[str]:
    if not isinstance(args, dict):
        return []
    result: list[str] = []
    for key in ("path", "file_path", "filepath", "filename"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            result.append(value.strip())
    return result


def _record_tool(
    payload: dict[str, Any],
    full: dict[str, int],
    effective: dict[str, int],
    events: dict[str, list[str]],
) -> None:
    item_type = str(payload.get("type") or "")
    name = str(payload.get("name") or "")
    if item_type == "local_shell_call" and not name:
        name = "shell"
    if item_type == "web_search_call" and not name:
        name = "web_search"
    args = safe_tool_args(payload)
    arg_text = stringify_payload(args)
    _add_text_bytes(full, "tool_call_bytes", arg_text)
    _add_text_bytes(effective, "tool_call_bytes", arg_text)
    if name:
        events["tools"].append(name)

    if name.startswith("mcp__"):
        events["mcp_tools"].append(name)

    read_paths: list[str] = []
    if name in {"read_file", "Read", "read"}:
        read_paths.extend(_extract_read_path_from_args(args))

    command = _command_text(args)
    if command:
        read_paths.extend(extract_shell_read_paths(command))

    for path in read_paths:
        events["file_reads"].append(path)
        skill = skill_from_path(path)
        if skill:
            events["skills"].append(skill)


def _add_message(
    payload: dict[str, Any],
    full: dict[str, int],
    effective: dict[str, int],
) -> None:
    role = str(payload.get("role") or "")
    if role == "user":
        for text in text_from_blocks(payload.get("content"), {"input_text", "text"}):
            key = "user_meta_bytes" if is_meta_user_text(text) else "user_text_bytes"
            _add_text_bytes(full, key, text)
            _add_text_bytes(effective, key, text)
    elif role == "assistant":
        for text in text_from_blocks(payload.get("content"), {"output_text", "text"}):
            _add_text_bytes(full, "assistant_text_bytes", text)
            _add_text_bytes(effective, "assistant_text_bytes", text)
    elif role == "developer":
        for text in text_from_blocks(payload.get("content"), {"input_text", "text"}):
            _add_text_bytes(full, "developer_bytes", text)
            _add_text_bytes(effective, "developer_bytes", text)


def _seed_replacement_history(items: Any, effective: dict[str, int], events: dict[str, list[str]]) -> None:
    if not isinstance(items, list):
        return
    dummy = new_breakdown()
    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type == "message":
            _add_message(item, dummy, effective)
        elif item_type in {"function_call", "custom_tool_call", "local_shell_call", "web_search_call"}:
            _record_tool(item, dummy, effective, events)
        elif item_type in {"function_call_output", "custom_tool_call_output"}:
            text = stringify_payload(item.get("output"))
            _add_text_bytes(effective, "tool_result_bytes", text)


def parse_session(path: Path, *, archived: bool = False) -> dict[str, Any]:
    path = path.expanduser().resolve()
    full = new_breakdown()
    effective = new_breakdown()
    events: dict[str, list[str]] = {
        "tools": [],
        "file_reads": [],
        "skills": [],
        "mcp_tools": [],
    }

    session_id = path.stem.removeprefix("rollout-")
    cwd: str | None = None
    project = "unknown"
    originator: str | None = None
    model_provider: str | None = None
    model: str | None = None
    started_at: str | None = None
    updated_at: str | None = None
    context_window: int | None = None
    current_context_tokens: int | None = None
    compactions = 0

    usage_totals = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": 0,
    }
    measured_calls = 0
    prev_info_identity: str | None = None
    prev_cumulative_total: int | None = None
    prev_cumulative_usage: dict[str, int] | None = None

    try:
        stream = path.open("r", encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RuntimeError(f"Не удалось открыть Codex session {path}: {exc}") from exc

    with stream:
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
            timestamp = entry.get("timestamp")
            if isinstance(timestamp, str):
                if started_at is None:
                    started_at = timestamp
                updated_at = timestamp

            payload = entry.get("payload")
            if not isinstance(payload, dict):
                continue
            entry_type = str(entry.get("type") or "")
            payload_type = str(payload.get("type") or "")

            if entry_type == "session_meta":
                if isinstance(payload.get("id") or payload.get("session_id"), str):
                    session_id = payload.get("id") or payload["session_id"]
                if isinstance(payload.get("cwd"), str):
                    cwd = payload["cwd"]
                    project = basename_project(cwd)
                if isinstance(payload.get("originator"), str):
                    originator = payload["originator"]
                if isinstance(payload.get("model_provider"), str):
                    model_provider = payload["model_provider"]
                if isinstance(payload.get("model"), str):
                    model = payload["model"]
                base = payload.get("base_instructions")
                if isinstance(base, dict) and isinstance(base.get("text"), str):
                    text = base["text"]
                    # A late session_meta replaces system instructions for the live
                    # context. Full keeps all observed bytes; effective keeps latest.
                    _add_text_bytes(full, "system_bytes", text)
                    effective["system_bytes"] = utf8_bytes(text)
                continue

            if entry_type == "turn_context":
                if isinstance(payload.get("model"), str) and payload["model"]:
                    model = payload["model"]
                continue

            if entry_type == "compacted":
                compactions += 1
                system_bytes = effective["system_bytes"]
                effective = new_breakdown()
                effective["system_bytes"] = system_bytes
                message = payload.get("message")
                if isinstance(message, str):
                    _add_text_bytes(effective, "compaction_bytes", message)
                    _add_text_bytes(full, "compaction_bytes", message)
                _seed_replacement_history(payload.get("replacement_history"), effective, events)
                continue

            if entry_type == "response_item":
                if payload_type == "message":
                    _add_message(payload, full, effective)
                elif payload_type in {"function_call", "custom_tool_call", "local_shell_call", "web_search_call"}:
                    _record_tool(payload, full, effective, events)
                elif payload_type in {"function_call_output", "custom_tool_call_output"}:
                    out = stringify_payload(payload.get("output"))
                    _add_text_bytes(full, "tool_result_bytes", out)
                    _add_text_bytes(effective, "tool_result_bytes", out)
                elif payload_type == "compaction":
                    compactions += 1
                continue

            if entry_type == "event_msg" and payload_type == "mcp_tool_call_end":
                invocation = payload.get("invocation")
                if isinstance(invocation, dict):
                    server = invocation.get("server")
                    tool = invocation.get("tool")
                    if isinstance(server, str) and isinstance(tool, str):
                        events["mcp_tools"].append(f"mcp__{server}__{tool}")
                continue

            if entry_type == "event_msg" and payload_type == "token_count":
                info = payload.get("info")
                if not isinstance(info, dict):
                    # Known Codex rate-limit ping shape: no usage claim, no estimate.
                    continue

                if isinstance(info.get("model"), str) and info["model"]:
                    model = info["model"]

                last_usage = info.get("last_token_usage")
                total_usage = info.get("total_token_usage")
                if isinstance(last_usage, dict):
                    last_fields = _usage_fields(last_usage)
                    context_value = last_fields["total_tokens"]
                    current_context_tokens = context_value if context_value > 0 else None
                elif isinstance(total_usage, dict):
                    # Cumulative usage is exact session spend but does not reveal
                    # the live context size of this later request.
                    current_context_tokens = None

                window = number(info.get("model_context_window"))
                if window is not None and window > 0:
                    context_window = window

                identity = canonical_json(info)
                if identity == prev_info_identity:
                    continue

                cumulative_total = None
                if isinstance(total_usage, dict):
                    cumulative_total = number(total_usage.get("total_tokens"))
                    if cumulative_total is not None and cumulative_total == prev_cumulative_total:
                        prev_info_identity = identity
                        continue

                call_usage: dict[str, int] | None = None
                if isinstance(last_usage, dict):
                    call_usage = _usage_fields(last_usage)
                elif isinstance(total_usage, dict):
                    call_usage = _delta_usage(total_usage, prev_cumulative_usage)

                if call_usage is not None:
                    for key, value in call_usage.items():
                        usage_totals[key] += value
                    measured_calls += 1

                if isinstance(total_usage, dict):
                    prev_cumulative_usage = _usage_fields(total_usage)
                    prev_cumulative_total = number(total_usage.get("total_tokens"))
                prev_info_identity = identity

    fp = fingerprint(path)
    measurement_type = "PROVIDER_MEASURED" if measured_calls > 0 else "UNKNOWN"
    return {
        "provider": "codex",
        "session_id": session_id,
        "path": str(path),
        "archived": archived,
        "cwd": cwd,
        "project": project,
        "originator": originator,
        "model_provider": model_provider,
        "model": model,
        "started_at": started_at,
        "updated_at": updated_at,
        "fingerprint": fp,
        "usage": {
            **usage_totals,
            "measurement_type": measurement_type,
            "source": "codex rollout token_count",
            "measured_calls": measured_calls,
            "reasoning_semantics": "reasoning_output_tokens is a subset of output_tokens and is not added to total_tokens",
        },
        "context": {
            "reported_context_tokens": current_context_tokens,
            "reported_context_measurement_type": "PROVIDER_MEASURED" if current_context_tokens is not None else "UNKNOWN",
            "reported_context_semantics": "LAST_REQUEST_TOTAL" if current_context_tokens is not None else "UNKNOWN",
            "context_window_tokens": context_window,
            "breakdown_unit": "bytes",
            "breakdown_bytes_full": full,
            "breakdown_bytes_effective": effective,
            "compactions": compactions,
        },
        "events": events,
    }