#!/usr/bin/env python3
"""Matreshka Native Context Telemetry.

Independent implementation for local, read-only telemetry. Provider data is read from local session files without external optimizer dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from context_telemetry import ENGINE_VERSION
from context_telemetry import antigravity, claude, codex
from context_telemetry.cache import (
    cache_hit,
    cache_put,
    default_cache_dir,
    load_cache,
    save_cache,
)
from context_telemetry.common import (
    ENGINE_NAME,
    SCHEMA_VERSION,
    aggregate_usage,
    configure_utf8_stdio,
    fingerprint,
)
from context_telemetry.detectors import aggregate_findings

configure_utf8_stdio()


class TelemetryError(RuntimeError):
    pass


def _select_sources(
    sources: list[dict[str, Any]],
    *,
    session_prefix: str | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    selected = sources
    if session_prefix:
        selected = [
            source for source in selected
            if str(source.get("session_id") or "").startswith(session_prefix)
        ]
    if limit is not None:
        selected = selected[: max(0, limit)]
    return selected


def _parse_with_cache(
    provider: str,
    sources: list[dict[str, Any]],
    *,
    use_cache: bool,
    cache_dir: Path | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    cache_stats = {"hits": 0, "misses": 0, "writes": 0}
    sessions: list[dict[str, Any]] = []

    cache_file = None
    cache = None
    if use_cache:
        root = (cache_dir or default_cache_dir()).expanduser().resolve()
        cache_file = root / f"{provider}-native-v1.json"
        cache = load_cache(cache_file)

    for source in sources:
        path = Path(str(source["path"])).expanduser().resolve()
        fp = fingerprint(path)
        cached = cache_hit(cache, path, fp) if cache is not None else None
        if cached is not None:
            sessions.append(cached)
            cache_stats["hits"] += 1
            continue

        cache_stats["misses"] += 1
        if provider == "codex":
            parsed = codex.parse_session(path, archived=bool(source.get("archived")))
        elif provider == "claude":
            parsed = claude.parse_session(path)
        else:
            raise TelemetryError(f"Cache parser не поддерживает provider={provider}")
        sessions.append(parsed)

        if cache is not None:
            cache_put(cache, path, fp, parsed)
            cache_stats["writes"] += 1

    if cache is not None and cache_file is not None and cache_stats["writes"] > 0:
        save_cache(cache_file, cache)

    return sessions, cache_stats


def collect_codex(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve() if args.root else codex.default_codex_home()
    sources = codex.discover_sessions(root)
    selected = _select_sources(sources, session_prefix=args.session_prefix, limit=args.limit)
    sessions, cache_stats = _parse_with_cache(
        "codex",
        selected,
        use_cache=args.use_cache,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "mode": "READ_ONLY",
        "provider": "codex",
        "source_root": str(root),
        "discovered_sessions": len(sources),
        "parsed_sessions": len(sessions),
        "cache": {
            "enabled": bool(args.use_cache),
            **cache_stats,
            "location": str((Path(args.cache_dir).expanduser().resolve() if args.cache_dir else default_cache_dir())) if args.use_cache else None,
        },
        "usage": aggregate_usage(sessions),
        "sessions": sessions,
        "findings": aggregate_findings(sessions),
        "safety": {
            "network": False,
            "process_probe": False,
            "rpc": False,
            "session_files_written": False,
        },
    }


def collect_claude(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve() if args.root else claude.default_claude_projects_root()
    sources = claude.discover_sessions(root)
    selected = _select_sources(sources, session_prefix=args.session_prefix, limit=args.limit)
    sessions, cache_stats = _parse_with_cache(
        "claude",
        selected,
        use_cache=args.use_cache,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "mode": "READ_ONLY",
        "provider": "claude",
        "source_root": str(root),
        "discovered_sessions": len(sources),
        "parsed_sessions": len(sessions),
        "cache": {
            "enabled": bool(args.use_cache),
            **cache_stats,
            "location": str((Path(args.cache_dir).expanduser().resolve() if args.cache_dir else default_cache_dir())) if args.use_cache else None,
        },
        "usage": aggregate_usage(sessions),
        "sessions": sessions,
        "findings": aggregate_findings(sessions),
        "safety": {
            "network": False,
            "process_probe": False,
            "rpc": False,
            "session_files_written": False,
        },
    }


def collect_antigravity(args: argparse.Namespace) -> dict[str, Any]:
    home = Path(args.root).expanduser().resolve() if args.root else Path.home()
    discovered = antigravity.discover_sources(home)

    if args.statusline:
        parsed = antigravity.parse_statusline_file(Path(args.statusline))
        sessions = parsed["sessions"]
        return {
            "schema_version": SCHEMA_VERSION,
            "engine": ENGINE_NAME,
            "engine_version": ENGINE_VERSION,
            "mode": "READ_ONLY",
            "provider": "antigravity",
            "source_root": str(home),
            "discovered_sources": len(discovered),
            "static_sources": discovered,
            "statusline_path": str(Path(args.statusline).expanduser().resolve()),
            "usage": aggregate_usage(sessions),
            "sessions": sessions,
            "findings": aggregate_findings(sessions),
            "capability": "SAFE_STATUSLINE_ONLY",
            "safety": {
                "network": False,
                "process_probe": False,
                "rpc": False,
                "hook_install": False,
                "conversation_db_written": False,
            },
        }

    sessions: list[dict[str, Any]] = []
    sqlite_errors: list[dict[str, str]] = []
    pb_sources = 0
    for source in discovered:
        if source.get("format") == "db":
            try:
                sessions.append(
                    antigravity.parse_sqlite_file(
                        Path(str(source["path"])),
                        project_hint=str(source.get("project") or "antigravity"),
                    )
                )
            except (OSError, RuntimeError, ValueError) as exc:
                sqlite_errors.append({"path": str(source.get("path")), "error": str(exc)})
        elif source.get("format") == "pb":
            pb_sources += 1

    measured_sessions = [
        session for session in sessions
        if session.get("usage", {}).get("measurement_type") == "PROVIDER_MEASURED"
    ]
    capability = (
        "SAFE_SQLITE_NATIVE"
        if measured_sessions and pb_sources == 0 and not sqlite_errors
        else "SAFE_SQLITE_PARTIAL"
        if measured_sessions
        else "STATIC_DISCOVERY_ONLY"
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "mode": "READ_ONLY",
        "provider": "antigravity",
        "source_root": str(home),
        "discovered_sources": len(discovered),
        "static_sources": discovered,
        "usage": aggregate_usage(sessions),
        "sessions": sessions,
        "findings": aggregate_findings(sessions),
        "capability": capability,
        "sqlite_errors": sqlite_errors,
        "undecoded_pb_sources": pb_sources,
        "limitation": (
            None
            if capability == "SAFE_SQLITE_NATIVE"
            else "SQLite gen_metadata is decoded read-only. Older .pb sources remain "
                 "static-only; live process/RPC probing is intentionally disabled."
        ),
        "safety": {
            "network": False,
            "process_probe": False,
            "rpc": False,
            "hook_install": False,
            "conversation_db_written": False,
            "sqlite_mode": "READ_ONLY",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Matreshka Native Context Telemetry")
    parser.add_argument("--provider", required=True, choices=["codex", "claude", "antigravity"])
    parser.add_argument("--root", help="Provider root/home override")
    parser.add_argument("--session-prefix")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--use-cache", action="store_true", help="Enable external user cache; disabled by default")
    parser.add_argument("--cache-dir", help="Explicit cache dir; never written unless --use-cache is set")
    parser.add_argument("--statusline", help="Existing Antigravity statusline JSONL; no hook is installed")
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        if args.provider == "codex":
            result = collect_codex(args)
        elif args.provider == "claude":
            result = collect_claude(args)
        else:
            result = collect_antigravity(args)
    except (OSError, TelemetryError, RuntimeError) as exc:
        print(json.dumps({"status": "UNAVAILABLE", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())