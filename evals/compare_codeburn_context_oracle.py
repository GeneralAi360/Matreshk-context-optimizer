#!/usr/bin/env python3
"""Optional parity oracle: compare native Codex current-context telemetry to CodeBurn.

CodeBurn is never installed or invoked here. The script only compares two
already-produced JSON files, so it remains an optional external oracle.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def native_context(payload: dict[str, Any], session_prefix: str | None) -> tuple[int | None, str | None]:
    sessions = payload.get("sessions")
    if not isinstance(sessions, list):
        return None, None
    for session in sessions:
        if not isinstance(session, dict):
            continue
        sid = str(session.get("session_id") or "")
        if session_prefix and not sid.startswith(session_prefix):
            continue
        context = session.get("context")
        if not isinstance(context, dict):
            continue
        value = context.get("reported_context_tokens")
        kind = context.get("reported_context_measurement_type")
        if isinstance(value, (int, float)) and kind == "PROVIDER_MEASURED":
            return int(value), sid
    return None, None


def codeburn_context(payload: dict[str, Any]) -> int | None:
    raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else payload
    reported = raw.get("reported") if isinstance(raw, dict) else None
    value = reported.get("context") if isinstance(reported, dict) else None
    return int(value) if isinstance(value, (int, float)) else None


def compare(native: dict[str, Any], codeburn: dict[str, Any], session_prefix: str | None = None) -> dict[str, Any]:
    ours, session_id = native_context(native, session_prefix)
    theirs = codeburn_context(codeburn)
    if ours is None or theirs is None:
        return {
            "verdict": "UNVERIFIED",
            "native_context_tokens": ours,
            "codeburn_context_tokens": theirs,
            "session_id": session_id,
            "reason": "Один из источников не содержит provider-measured current context.",
        }
    delta = ours - theirs
    return {
        "verdict": "PASS" if delta == 0 else "MISMATCH",
        "native_context_tokens": ours,
        "codeburn_context_tokens": theirs,
        "delta": delta,
        "session_id": session_id,
        "reason": "Exact parity" if delta == 0 else "Нужно разобрать различие парсеров/семантики.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare native Codex telemetry with CodeBurn context JSON")
    parser.add_argument("--native", required=True)
    parser.add_argument("--codeburn", required=True)
    parser.add_argument("--session-prefix")
    args = parser.parse_args()

    result = compare(
        load(Path(args.native).expanduser().resolve()),
        load(Path(args.codeburn).expanduser().resolve()),
        args.session_prefix,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["verdict"] == "MISMATCH" else 0


if __name__ == "__main__":
    raise SystemExit(main())
