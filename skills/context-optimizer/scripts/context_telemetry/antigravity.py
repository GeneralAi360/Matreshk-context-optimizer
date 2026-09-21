from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .common import basename_project, canonical_json, fingerprint, number

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
