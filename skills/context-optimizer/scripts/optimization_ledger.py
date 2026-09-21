#!/usr/bin/env python3
"""Append-only Optimization Ledger для Context Optimizer."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


_configure_utf8_stdio()

SCHEMA_VERSION = "0.1"
LEDGER_RELATIVE = Path(".context-optimizer") / "optimization-ledger.jsonl"


class LedgerError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ledger_path(project_root: Path) -> Path:
    return project_root / LEDGER_RELATIVE


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(event.get("event_id") or uuid.uuid4()),
        "timestamp": str(event.get("timestamp") or now_iso()),
        "event_type": event.get("event_type"),
        "change_id": event.get("change_id"),
        "status": event.get("status"),
        "finding_ids": list(event.get("finding_ids") or []),
        "target": event.get("target"),
        "operation": event.get("operation"),
        "before": event.get("before"),
        "after": event.get("after"),
        "metrics": event.get("metrics"),
        "quality": event.get("quality"),
        "notes": event.get("notes"),
    }

    if not isinstance(result["event_type"], str) or not result["event_type"]:
        raise LedgerError("event_type обязателен")
    if not isinstance(result["change_id"], str) or not result["change_id"].startswith("CHG-"):
        raise LedgerError("change_id должен иметь формат CHG-...")
    if not isinstance(result["status"], str) or not result["status"]:
        raise LedgerError("status обязателен")
    return result


def append_event(project_root: Path, event: dict[str, Any]) -> dict[str, Any]:
    project_root = project_root.resolve()
    path = ledger_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    normalized = normalize_event(event)
    line = json.dumps(normalized, ensure_ascii=False, sort_keys=True)

    # Append-only write. fsync keeps the event durable before returning.
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line + "\n")
        stream.flush()
        os.fsync(stream.fileno())

    return normalized


def read_events(project_root: Path) -> list[dict[str, Any]]:
    path = ledger_path(project_root.resolve())
    if not path.exists():
        return []

    events: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"Повреждён ledger line {index}: {exc}") from exc
        if not isinstance(value, dict):
            raise LedgerError(f"Ledger line {index} не является JSON object")
        events.append(value)
    return events


def events_for_change(project_root: Path, change_id: str) -> list[dict[str, Any]]:
    return [
        event
        for event in read_events(project_root)
        if event.get("change_id") == change_id
    ]


def latest_event_for_change(project_root: Path, change_id: str) -> dict[str, Any] | None:
    events = events_for_change(project_root, change_id)
    return events[-1] if events else None


def verification_event(
    change_id: str,
    *,
    finding_ids: list[str],
    status: str,
    metrics: dict[str, Any] | None,
    quality: dict[str, Any] | None,
    notes: str | None = None,
) -> dict[str, Any]:
    if status not in {"KEEP", "ROLLBACK", "UNVERIFIED", "NEEDS_MORE_DATA"}:
        raise LedgerError("Verification status должен быть KEEP/ROLLBACK/UNVERIFIED/NEEDS_MORE_DATA")
    return {
        "event_type": "VERIFICATION",
        "change_id": change_id,
        "status": status,
        "finding_ids": finding_ids,
        "metrics": metrics,
        "quality": quality,
        "notes": notes,
    }


def load_json_object(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerError(f"Не удалось прочитать JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LedgerError(f"{path} должен содержать JSON object")
    return value


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def summary(project_root: Path) -> dict[str, Any]:
    events = read_events(project_root)
    by_change: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        change_id = str(event.get("change_id") or "")
        if not change_id:
            continue
        by_change.setdefault(change_id, []).append(event)

    rows = []
    for change_id, change_events in sorted(by_change.items()):
        latest = change_events[-1]
        rows.append(
            {
                "change_id": change_id,
                "events": len(change_events),
                "latest_event_type": latest.get("event_type"),
                "latest_status": latest.get("status"),
                "target": next(
                    (event.get("target") for event in reversed(change_events) if event.get("target")),
                    None,
                ),
                "finding_ids": sorted(
                    {
                        finding
                        for event in change_events
                        for finding in (event.get("finding_ids") or [])
                    }
                ),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "project_root": str(project_root.resolve()),
        "ledger_path": str(ledger_path(project_root.resolve())),
        "event_count": len(events),
        "change_count": len(rows),
        "changes": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimization Ledger")
    parser.add_argument("--project", default=".", help="Корень проекта")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")

    show = sub.add_parser("show")
    show.add_argument("--change-id", required=True)

    verify = sub.add_parser("record-verification")
    verify.add_argument("--change-id", required=True)
    verify.add_argument(
        "--status",
        required=True,
        choices=["KEEP", "ROLLBACK", "UNVERIFIED", "NEEDS_MORE_DATA"],
    )
    verify.add_argument("--finding-id", action="append", default=[])
    verify.add_argument("--metrics-json")
    verify.add_argument("--quality-json")
    verify.add_argument("--notes")

    args = parser.parse_args()
    root = Path(args.project).expanduser().resolve()

    try:
        if args.command == "list":
            result = summary(root)
        elif args.command == "show":
            result = {
                "change_id": args.change_id,
                "events": events_for_change(root, args.change_id),
            }
        else:
            metrics = load_json_object(
                Path(args.metrics_json).expanduser().resolve()
                if args.metrics_json
                else None
            )
            quality = load_json_object(
                Path(args.quality_json).expanduser().resolve()
                if args.quality_json
                else None
            )
            result = append_event(
                root,
                verification_event(
                    args.change_id,
                    finding_ids=args.finding_id,
                    status=args.status,
                    metrics=metrics,
                    quality=quality,
                    notes=args.notes,
                ),
            )
    except LedgerError as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
