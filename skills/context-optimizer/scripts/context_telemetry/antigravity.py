from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .common import basename_project, canonical_json, fingerprint, number
from .protobuf_wire import (
    all_fields,
    decode_packed_varints,
    field_bytes,
    field_text,
    first,
    parse_fields,
    positive_int,
    timestamp_to_iso,
)

ROOTS = (
    (".gemini/antigravity/conversations", "antigravity", {".pb", ".db"}),
    (".gemini/antigravity-cli/conversations", "antigravity-cli", {".pb", ".db"}),
    (".gemini/antigravity-cli/implicit", "antigravity-cli", {".pb"}),
    (".gemini/antigravity-ide/conversations", "antigravity-ide", {".pb", ".db"}),
    (".gemini/antigravity-ide/implicit", "antigravity-ide", {".pb"}),
)


def discover_sources(home: Path | None = None) -> list[dict[str, Any]]:
    base = (home or Path.home()).expanduser().resolve()
    result: list[dict[str, Any]] = []
    for rel, project, extensions in ROOTS:
        root = base / rel
        if not root.exists():
            continue
        try:
            files = sorted(root.iterdir())
        except OSError:
            continue
        for path in files:
            if not path.is_file() or path.suffix.lower() not in extensions:
                continue
            fp = fingerprint(path)
            result.append({
                "provider": "antigravity",
                "path": str(path.resolve()),
                "session_id": path.stem,
                "project": project,
                "format": path.suffix.lower().removeprefix("."),
                "mtime_ns": fp["mtime_ns"],
                "size_bytes": fp["size_bytes"],
                "telemetry_state": "DISCOVERED_STATIC_ONLY",
                "note": "Native v0.2 does not probe live language servers or perform RPC.",
            })
    result.sort(key=lambda item: int(item.get("mtime_ns") or 0), reverse=True)
    return result


def _usage(raw: dict[str, Any]) -> dict[str, int]:
    input_tokens = number(raw.get("inputTokens"))
    if input_tokens is None:
        input_tokens = number(raw.get("input_tokens"))
    output_tokens = number(raw.get("outputTokens"))
    if output_tokens is None:
        output_tokens = number(raw.get("output_tokens"))
    cache_create = number(raw.get("cacheCreationInputTokens"))
    if cache_create is None:
        cache_create = number(raw.get("cache_creation_input_tokens"))
    cache_read = number(raw.get("cacheReadInputTokens"))
    if cache_read is None:
        cache_read = number(raw.get("cache_read_input_tokens"))
    values = {
        "input_tokens": max(0, input_tokens or 0),
        "cached_input_tokens": 0,
        "cache_creation_input_tokens": max(0, cache_create or 0),
        "cache_read_input_tokens": max(0, cache_read or 0),
        "output_tokens": max(0, output_tokens or 0),
        "reasoning_output_tokens": 0,
    }
    values["total_tokens"] = (
        values["input_tokens"]
        + values["cache_creation_input_tokens"]
        + values["cache_read_input_tokens"]
        + values["output_tokens"]
    )
    return values


def _monotonic(current: dict[str, int], previous: dict[str, int]) -> bool:
    keys = (
        "input_tokens", "cache_creation_input_tokens",
        "cache_read_input_tokens", "output_tokens",
    )
    return all(current[key] >= previous[key] for key in keys)


def _delta(current: dict[str, int], previous: dict[str, int]) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, value in current.items():
        prior = previous.get(key, 0)
        result[key] = value - prior if value >= prior else value
    # Recompute total from the component deltas.
    result["total_tokens"] = (
        result["input_tokens"]
        + result["cache_creation_input_tokens"]
        + result["cache_read_input_tokens"]
        + result["output_tokens"]
    )
    return result



SKILL_MD_PATTERN = re.compile(r"(?:^|[\\/])([^\\/]+)[\\/]SKILL\.md$", re.IGNORECASE)
FILE_URL_PATTERN = re.compile(rb"file:///[^\x00-\x1f\x7f\"'\s]+", re.IGNORECASE)


def _blob(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, str):
        return value.encode("utf-8")
    return b""


def _sqlite_uri(path: Path) -> str:
    # mode=ro prevents writes while still allowing SQLite to read a WAL-backed
    # database. We intentionally do not use immutable=1 because an active
    # Antigravity DB may have committed rows in its WAL.
    return "file:" + quote(str(path.resolve()), safe="/:\\") + "?mode=ro"


def _metadata_attributes(chat_fields: list[Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for field in all_fields(chat_fields, 20):
        raw = field_bytes(field)
        if not raw:
            continue
        pair = parse_fields(raw)
        key = field_text(first(pair, 1))
        value = field_text(first(pair, 2))
        if key and value:
            result[key] = value
    return result


def _sqlite_model(chat_fields: list[Any]) -> str:
    attributes = _metadata_attributes(chat_fields)
    display = field_text(first(chat_fields, 21))
    raw = (
        field_text(first(chat_fields, 19))
        or attributes.get("model_enum")
        or display
        or "unknown"
    )
    return raw.strip() or "unknown"


def _created_at(chat_fields: list[Any]) -> str | None:
    metadata = field_bytes(first(chat_fields, 9))
    if not metadata:
        return None
    return timestamp_to_iso(first(parse_fields(metadata), 4))


def _tool_from_step(
    metadata: bytes,
    events: dict[str, list[str]],
) -> None:
    fields = parse_fields(metadata)
    for field in all_fields(fields, 4):
        raw_tool = field_bytes(field)
        if not raw_tool:
            continue
        tool_fields = parse_fields(raw_tool)
        tool_name = field_text(first(tool_fields, 2))
        if not tool_name or tool_name == "send_message":
            continue

        raw_args = field_text(first(tool_fields, 3))
        args: dict[str, Any] = {}
        if raw_args:
            try:
                parsed = json.loads(raw_args)
                if isinstance(parsed, dict):
                    args = parsed
            except json.JSONDecodeError:
                pass

        if tool_name == "call_mcp_tool":
            server = args.get("ServerName")
            tool = args.get("ToolName")
            if isinstance(server, str) and isinstance(tool, str) and server.strip() and tool.strip():
                events["mcp_tools"].append(f"mcp__{server.strip()}__{tool.strip()}")
                events["tools"].append("call_mcp_tool")
            else:
                events["tools"].append("call_mcp_tool")
            continue

        events["tools"].append(tool_name)

        if tool_name == "view_file":
            path = args.get("AbsolutePath")
            if not isinstance(path, str):
                path = args.get("file_path")
            if isinstance(path, str) and path:
                events["file_reads"].append(path)
                match = SKILL_MD_PATTERN.search(path.replace("\\", "/"))
                if match:
                    events["skills"].append(match.group(1))


def _workspace_path(connection: sqlite3.Connection) -> str | None:
    try:
        rows = connection.execute("SELECT data FROM trajectory_metadata_blob").fetchall()
    except sqlite3.Error:
        return None
    for row in rows:
        raw = _blob(row[0] if row else None)
        match = FILE_URL_PATTERN.search(raw)
        if not match:
            continue
        try:
            value = match.group(0).decode("utf-8")
        except UnicodeDecodeError:
            continue
        # Conservative file:/// decoder. We do not need to access the path.
        value = value.removeprefix("file:///")
        if value:
            return value.replace("%20", " ")
    return None


def parse_sqlite_file(path: Path, *, project_hint: str | None = None) -> dict[str, Any]:
    """Decode Antigravity gen_metadata using Python's built-in SQLite in RO mode.

    No process scan, RPC, TLS override, hook, provider write, or database write
    is performed. A transient SQLite lock/error is surfaced to the caller.
    """
    path = path.expanduser().resolve()
    if path.suffix.lower() != ".db":
        raise ValueError("Antigravity SQLite decoder accepts only .db files")

    try:
        connection = sqlite3.connect(
            _sqlite_uri(path),
            uri=True,
            timeout=0.25,
            check_same_thread=False,
        )
    except sqlite3.Error as exc:
        raise RuntimeError(f"Не удалось открыть Antigravity DB read-only: {exc}") from exc

    try:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute(
            "SELECT idx, data FROM gen_metadata ORDER BY idx"
        ).fetchall()
        try:
            step_rows = connection.execute(
                "SELECT idx, metadata FROM steps ORDER BY idx"
            ).fetchall()
        except sqlite3.Error:
            step_rows = []
        workspace_path = _workspace_path(connection)
    except sqlite3.Error as exc:
        raise RuntimeError(f"Не удалось прочитать Antigravity DB: {exc}") from exc
    finally:
        connection.close()

    step_map = {
        int(row[0]): _blob(row[1])
        for row in step_rows
        if len(row) >= 2 and isinstance(row[0], int)
    }

    events: dict[str, list[str]] = {
        "tools": [],
        "file_reads": [],
        "skills": [],
        "mcp_tools": [],
    }
    calls: list[dict[str, Any]] = []
    seen_response_ids: set[str] = set()

    for row in rows:
        if len(row) < 2:
            continue
        idx = int(row[0]) if isinstance(row[0], int) else len(calls)
        raw = _blob(row[1])
        if not raw:
            continue
        root_fields = parse_fields(raw)

        step_indices: list[int] = []
        for field in all_fields(root_fields, 2):
            packed = field_bytes(field)
            if packed:
                step_indices.extend(decode_packed_varints(packed))

        call_events = {
            "tools": [],
            "file_reads": [],
            "skills": [],
            "mcp_tools": [],
        }
        for step_idx in step_indices:
            metadata = step_map.get(step_idx)
            if metadata:
                _tool_from_step(metadata, call_events)

        chat_raw = field_bytes(first(root_fields, 1))
        if not chat_raw:
            continue
        chat_fields = parse_fields(chat_raw)
        usage_raw = field_bytes(first(chat_fields, 4))
        if not usage_raw:
            continue
        usage_fields = parse_fields(usage_raw)

        input_tokens = positive_int(first(usage_fields, 2)) or positive_int(first(usage_fields, 1))
        total_output = positive_int(first(usage_fields, 3))
        response_tokens = positive_int(first(usage_fields, 9))
        thinking_tokens = positive_int(first(usage_fields, 10))

        if response_tokens == 0 and thinking_tokens == 0:
            response_tokens = total_output
        elif total_output > 0 and response_tokens + thinking_tokens != total_output:
            adjusted = total_output - thinking_tokens
            if adjusted >= 0:
                response_tokens = adjusted

        if input_tokens == 0 and total_output == 0:
            continue

        response_id = field_text(first(usage_fields, 11)) or str(idx)
        if not response_id.strip() or any(ch.isspace() for ch in response_id):
            response_id = str(idx)
        if response_id in seen_response_ids:
            continue
        seen_response_ids.add(response_id)

        model = _sqlite_model(chat_fields)
        created_at = _created_at(chat_fields)
        call = {
            "response_id": response_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": response_tokens,
            "reasoning_output_tokens": thinking_tokens,
            "total_tokens": input_tokens + response_tokens + thinking_tokens,
            "timestamp": created_at,
            "step_indices": step_indices,
            "events": call_events,
        }
        calls.append(call)
        for key in events:
            events[key].extend(call_events[key])

    model_counts = Counter(
        str(call["model"]) for call in calls if call.get("model") and call.get("model") != "unknown"
    )
    model = model_counts.most_common(1)[0][0] if model_counts else "unknown"
    started = next((call["timestamp"] for call in calls if call.get("timestamp")), None)
    updated = next((call["timestamp"] for call in reversed(calls) if call.get("timestamp")), None)

    totals = {
        "input_tokens": sum(int(call["input_tokens"]) for call in calls),
        "cached_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "output_tokens": sum(int(call["output_tokens"]) for call in calls),
        "reasoning_output_tokens": sum(int(call["reasoning_output_tokens"]) for call in calls),
        "total_tokens": sum(int(call["total_tokens"]) for call in calls),
    }

    last_input = int(calls[-1]["input_tokens"]) if calls else None
    project = basename_project(workspace_path) if workspace_path else (project_hint or "antigravity")
    return {
        "provider": "antigravity",
        "session_id": path.stem,
        "conversation_id": path.stem,
        "path": str(path),
        "archived": False,
        "cwd": workspace_path,
        "project": project,
        "model": model,
        "started_at": started,
        "updated_at": updated,
        "fingerprint": fingerprint(path),
        "usage": {
            **totals,
            "measurement_type": "PROVIDER_MEASURED" if calls else "UNKNOWN",
            "source": "Antigravity SQLite gen_metadata protobuf",
            "measured_calls": len(calls),
            "reasoning_semantics": "reasoning_output_tokens is included once alongside response output",
        },
        "context": {
            "reported_context_tokens": last_input,
            "reported_context_measurement_type": "PROVIDER_MEASURED" if last_input is not None else "UNKNOWN",
            "reported_context_semantics": "LAST_GENERATION_INPUT",
            "context_window_tokens": None,
            "breakdown_unit": "bytes",
            "breakdown_bytes_full": {},
            "breakdown_bytes_effective": {},
            "compactions": 0,
        },
        "events": events,
        "calls": calls,
        "safety": {
            "sqlite_mode": "READ_ONLY",
            "network": False,
            "live_process_probe": False,
            "rpc": False,
            "hook_install": False,
            "database_write": False,
        },
    }



def parse_statusline_file(path: Path) -> dict[str, Any]:
    """Parse an existing statusline JSONL file without installing a hook.

    The accepted line format is intentionally tiny: timestamp, conversation id,
    model and current usage. The engine never launches ps/lsof, never connects
    to Antigravity RPC, and never writes statusline events itself.
    """
    path = path.expanduser().resolve()
    by_conversation: dict[str, list[dict[str, Any]]] = defaultdict(list)

    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(value, dict):
                continue

            conversation_id = value.get("conversationId")
            if not isinstance(conversation_id, str):
                conversation_id = value.get("conversation_id")
            model = value.get("model")
            if isinstance(model, dict):
                model = model.get("id") or model.get("display_name")
            at = value.get("at") or value.get("timestamp")

            raw_usage = value.get("usage")
            if not isinstance(raw_usage, dict):
                context = value.get("context_window")
                raw_usage = context.get("current_usage") if isinstance(context, dict) else None
            if not isinstance(conversation_id, str) or not conversation_id:
                continue
            if not isinstance(model, str) or not model:
                continue
            if not isinstance(raw_usage, dict):
                continue

            usage = _usage(raw_usage)
            if usage["total_tokens"] <= 0:
                continue
            by_conversation[conversation_id].append({
                "at": at if isinstance(at, str) else None,
                "session_id": value.get("sessionId") or value.get("session_id"),
                "model": model,
                "usage": usage,
                "signature": canonical_json(usage),
            })

    sessions: list[dict[str, Any]] = []
    for conversation_id, snapshots in by_conversation.items():
        runs: list[dict[str, Any]] = []
        for snapshot in snapshots:
            if runs and runs[-1]["signature"] == snapshot["signature"]:
                runs[-1]["count"] += 1
                runs[-1]["snapshot"] = snapshot
            else:
                runs.append({"signature": snapshot["signature"], "count": 1, "snapshot": snapshot})

        totals = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
            "total_tokens": 0,
        }
        previous_snapshot: dict[str, int] | None = None
        measured_calls = 0
        accepted: list[dict[str, Any]] = []

        for index, run in enumerate(runs):
            is_last = index == len(runs) - 1
            if run["count"] == 1 and not is_last:
                continue
            snapshot = run["snapshot"]
            usage = snapshot["usage"]
            call = (
                _delta(usage, previous_snapshot)
                if previous_snapshot is not None and _monotonic(usage, previous_snapshot)
                else usage
            )
            previous_snapshot = usage
            for key, value in call.items():
                totals[key] += value
            measured_calls += 1
            accepted.append(snapshot)

        if not accepted:
            continue
        last = accepted[-1]
        sessions.append({
            "provider": "antigravity",
            "session_id": (
                last.get("session_id")
                if isinstance(last.get("session_id"), str)
                else conversation_id
            ),
            "conversation_id": conversation_id,
            "path": str(path),
            "archived": False,
            "cwd": None,
            "project": "antigravity",
            "model": last["model"],
            "started_at": accepted[0].get("at"),
            "updated_at": last.get("at"),
            "fingerprint": fingerprint(path),
            "usage": {
                **totals,
                "measurement_type": "PROVIDER_MEASURED",
                "source": "existing Antigravity statusline current_usage snapshots",
                "measured_calls": measured_calls,
            },
            "context": {
                "reported_context_tokens": last["usage"]["total_tokens"],
                "reported_context_measurement_type": "PROVIDER_MEASURED",
                "reported_context_semantics": "STATUSLINE_CURRENT_USAGE",
                "context_window_tokens": None,
                "breakdown_unit": "bytes",
                "breakdown_bytes_full": {},
                "breakdown_bytes_effective": {},
                "compactions": 0,
            },
            "events": {"tools": [], "file_reads": [], "skills": [], "mcp_tools": []},
            "safety": {
                "live_process_probe": False,
                "rpc": False,
                "hook_install": False,
            },
        })

    return {
        "provider": "antigravity",
        "mode": "READ_ONLY_EXISTING_STATUSLINE",
        "path": str(path),
        "sessions": sessions,
    }