from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "0.2"
ENGINE_NAME = "Matreshka Context Telemetry"


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def utf8_bytes(value: str) -> int:
    return len(value.encode("utf-8", errors="replace"))


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_json_loads(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def basename_project(cwd: str | None) -> str:
    if not cwd:
        return "unknown"
    value = cwd.replace("\\", "/").rstrip("/")
    return value.rsplit("/", 1)[-1] if value else "unknown"


def number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def text_from_blocks(content: Any, accepted_types: set[str]) -> list[str]:
    out: list[str] = []
    if isinstance(content, str):
        out.append(content)
        return out
    if not isinstance(content, list):
        return out
    for block in content:
        if not isinstance(block, dict):
            continue
        if str(block.get("type") or "") not in accepted_types:
            continue
        text = block.get("text")
        if isinstance(text, str):
            out.append(text)
    return out


def normalize_path_candidate(value: str) -> str:
    return value.strip().strip("'\"").replace("\\", "/")


READ_BINARIES = {
    "cat", "bat", "sed", "head", "tail", "less", "more", "type",
    "get-content", "gc", "read_file", "read-file",
}

# Deliberately conservative shell read detector. It only extracts path-like
# tokens following a known reader command; misses are preferable to inventing
# file reads from arbitrary shell text.
_SHELL_READ = re.compile(
    r"(?i)(?:^|[;&|]\s*|\s)(cat|bat|sed|head|tail|less|more|type|get-content|gc)\s+(?:-[^\s]+\s+)*([^;&|\n]+)"
)
_SKILL_PATH = re.compile(r"(?i)(?:^|[\\/])([^\\/]+)[\\/]SKILL\.md$")


def extract_shell_read_paths(command: str) -> list[str]:
    paths: list[str] = []
    for match in _SHELL_READ.finditer(command):
        tail = match.group(2).strip()
        # Keep only the final token(s) that look path-like. We avoid shell
        # expansion and never execute the command.
        for token in re.split(r"\s+", tail):
            token = normalize_path_candidate(token)
            if not token or token.startswith("-"):
                continue
            if "/" in token or "\\" in token or "." in Path(token).name:
                paths.append(token)
    return paths


def skill_from_path(path: str) -> str | None:
    match = _SKILL_PATH.search(normalize_path_candidate(path))
    return match.group(1) if match else None


def safe_tool_args(payload: dict[str, Any]) -> Any:
    for key in ("arguments", "input", "action"):
        if key in payload:
            value = payload.get(key)
            if isinstance(value, str):
                parsed = safe_json_loads(value)
                return parsed if parsed is not None else value
            return value
    return None


def stringify_payload(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return canonical_json(value)
    except (TypeError, ValueError):
        return ""


def new_breakdown() -> dict[str, int]:
    return {
        "system_bytes": 0,
        "user_text_bytes": 0,
        "user_meta_bytes": 0,
        "developer_bytes": 0,
        "assistant_text_bytes": 0,
        "tool_call_bytes": 0,
        "tool_result_bytes": 0,
        "compaction_bytes": 0,
    }


def is_meta_user_text(text: str) -> bool:
    value = text.lstrip()
    if value.startswith("<") and not value.startswith("<image"):
        return True
    return value.startswith("# AGENTS.md") or value.startswith("# Files mentioned")


def fingerprint(path: Path) -> dict[str, int | str]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "mtime_ns": int(stat.st_mtime_ns),
        "size_bytes": int(stat.st_size),
    }


def aggregate_usage(sessions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    keys = [
        "input_tokens", "cached_input_tokens", "cache_creation_input_tokens",
        "cache_read_input_tokens", "output_tokens", "reasoning_output_tokens",
        "total_tokens",
    ]
    totals = {key: 0 for key in keys}
    measured_sessions = 0
    unknown_sessions = 0
    for session in sessions:
        usage = session.get("usage") if isinstance(session, dict) else None
        if not isinstance(usage, dict):
            unknown_sessions += 1
            continue
        if usage.get("measurement_type") == "PROVIDER_MEASURED":
            measured_sessions += 1
        else:
            unknown_sessions += 1
        for key in keys:
            value = number(usage.get(key))
            if value is not None:
                totals[key] += value
    totals.update({
        "measurement_type": "PROVIDER_MEASURED" if measured_sessions and not unknown_sessions else ("PARTIAL" if measured_sessions else "UNKNOWN"),
        "measured_sessions": measured_sessions,
        "unknown_sessions": unknown_sessions,
    })
    return totals


def walk_files(root: Path, suffix: str) -> Iterable[Path]:
    if not root.exists():
        return []
    result: list[Path] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__"}]
        base = Path(current)
        for name in files:
            if name.endswith(suffix):
                result.append(base / name)
    return result
