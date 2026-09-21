#!/usr/bin/env python3
"""Единая команда Context Optimizer для пользователя и Matreshka Agent."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import audit_extended
import matreshka_bridge
import native_telemetry
import project_map
from context_telemetry.common import aggregate_usage
from optimization_ledger import summary as ledger_summary


def detect_provider() -> str | None:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    if (codex_home / "sessions").exists() or (codex_home / "archived_sessions").exists():
        return "codex"

    claude_home = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    if (claude_home / "projects").exists():
        return "claude"

    gemini = Path.home() / ".gemini"
    if any((gemini / name).exists() for name in ("antigravity", "antigravity-cli", "antigravity-ide")):
        return "antigravity"
    return None


def _same_project(cwd: str | None, project: Path) -> bool:
    if not cwd:
        return False
    try:
        return Path(cwd).expanduser().resolve() == project.resolve()
    except OSError:
        return False


def _filter_runtime(report: dict[str, Any], project: Path) -> dict[str, Any]:
    sessions = report.get("sessions")
    if not isinstance(sessions, list):
        return report

    matched = [
        session for session in sessions
        if isinstance(session, dict) and _same_project(
            session.get("cwd") if isinstance(session.get("cwd"), str) else None,
            project,
        )
    ]
    filtered = dict(report)
    filtered["sessions"] = matched
    filtered["usage"] = aggregate_usage(matched)
    filtered["project_filter"] = str(project.resolve())
    filtered["project_sessions"] = len(matched)
    return filtered


def collect_runtime(provider: str | None, project: Path, telemetry_root: str | None) -> dict[str, Any] | None:
    if provider is None:
        return None

    ns = SimpleNamespace(
        provider=provider,
        root=telemetry_root,
        session_prefix=None,
        limit=25,
        use_cache=False,
        cache_dir=None,
        statusline=None,
        output=None,
    )
    if provider == "codex":
        report = native_telemetry.collect_codex(ns)
    elif provider == "claude":
        report = native_telemetry.collect_claude(ns)
    else:
        report = native_telemetry.collect_antigravity(ns)

    return _filter_runtime(report, project)


def command_message(command: str, bridge: dict[str, Any]) -> str:
    findings = len(bridge.get("topFindings") or [])
    health = bridge.get("health") or "UNKNOWN"
    mapping = {
        "start": (
            "Контроль контекста подключён к новому проекту. "
            "Снят базовый снимок до масштабной реализации."
        ),
        "adopt": (
            "Существующий проект подключён к контролю контекста. "
            "Первичный аудит выполнен до изменения архитектуры."
        ),
        "resume": (
            "Контекст проекта перепроверен после возобновления работы. "
            "Карта проекта и текущие риски обновлены."
        ),
        "check": "Проверка контекста выполнена по текущему состоянию проекта.",
        "status": "Текущее состояние контекста обновлено.",
        "optimize": (
            "Подготовлен план оптимизации. Никакие изменения не применялись автоматически."
        ),
    }
    base = mapping.get(command, "Проверка контекста завершена.")
    return f"{base} Состояние: {health}. Найдено замечаний: {findings}."


def run_command(
    command: str,
    project: Path,
    *,
    provider: str | None,
    include_global: bool,
    telemetry_root: str | None,
    trigger_mode: str,
    trigger_reason: str | None,
    trigger_automatic: bool,
) -> dict[str, Any]:
    audit = audit_extended.audit_extended(project, include_global=include_global)
    pmap = project_map.build_project_map(project)
    runtime = collect_runtime(provider, project, telemetry_root)

    try:
        ledger = ledger_summary(project)
    except Exception:
        ledger = None

    bridge = matreshka_bridge.build_bridge(
        audit,
        runtime=runtime,
        project_map=pmap,
        ledger=ledger,
        trigger={
            "mode": trigger_mode,
            "reason": trigger_reason,
            "automatic": trigger_automatic,
        },
    )

    result: dict[str, Any] = {
        "schema_version": "0.1",
        "command": command,
        "project_root": str(project.resolve()),
        "provider": provider,
        "message_ru": command_message(command, bridge),
        "bridge": bridge,
    }

    if command == "optimize":
        result["proposals"] = [
            {
                "finding_id": item.get("id"),
                "title": item.get("title"),
                "action": item.get("action"),
                "requires_approval": True,
            }
            for item in bridge.get("topFindings", [])
        ]
        result["mutation"] = "NOT_APPLIED"

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Context Optimizer — единая команда")
    parser.add_argument("--project", default=".")
    parser.add_argument("--provider", choices=["auto", "codex", "claude", "antigravity", "none"], default="auto")
    parser.add_argument("--telemetry-root")
    parser.add_argument("--include-global", action="store_true")
    parser.add_argument("--trigger-mode", default="MANUAL")
    parser.add_argument("--trigger-reason")
    parser.add_argument("--automatic", action="store_true")
    parser.add_argument("--output")

    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "adopt", "resume", "check", "status", "optimize"):
        sub.add_parser(name)

    args = parser.parse_args()
    project = Path(args.project).expanduser().resolve()
    if not project.exists() or not project.is_dir():
        print(json.dumps({"status": "ERROR", "error": f"Проект не найден: {project}"}, ensure_ascii=False, indent=2))
        return 2

    provider = detect_provider() if args.provider == "auto" else (None if args.provider == "none" else args.provider)

    result = run_command(
        args.command,
        project,
        provider=provider,
        include_global=args.include_global,
        telemetry_root=args.telemetry_root,
        trigger_mode=args.trigger_mode,
        trigger_reason=args.trigger_reason,
        trigger_automatic=args.automatic,
    )

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
