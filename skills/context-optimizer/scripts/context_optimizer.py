#!/usr/bin/env python3
"""Единая команда Context Optimizer для пользователя и Matreshka Agent."""

from __future__ import annotations

import argparse
import json
import os
import sys
sys.dont_write_bytecode = True
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import audit_extended
import matreshka_bridge
import project_map
import trigger_policy
import runtime_audit
from optimization_ledger import summary as ledger_summary


def detect_provider() -> str | None:
    candidates = []
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    if (codex_home / "sessions").exists() or (codex_home / "archived_sessions").exists():
        candidates.append("codex")

    claude_home = Path(
        os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")
    )
    if (claude_home / "projects").exists():
        candidates.append("claude")

    gemini = Path.home() / ".gemini"
    if any(
        (gemini / name).exists()
        for name in ("antigravity", "antigravity-cli", "antigravity-ide")
    ):
        candidates.append("antigravity")
    return candidates[0] if len(candidates) == 1 else None


def collect_runtime(
    provider: str | None,
    project: Path,
    telemetry_root: str | None,
) -> dict[str, Any] | None:
    if provider is None:
        return None

    return runtime_audit.collect(provider, project, telemetry_root)


def command_message(
    command: str,
    bridge: dict[str, Any],
) -> str:
    findings = len(bridge.get("topFindings") or [])
    health = bridge.get("health") or "UNKNOWN"
    health_ru = {
        "OK": "норма",
        "WARNING": "требует внимания",
        "CRITICAL": "критично",
        "UNKNOWN": "неизвестно",
    }.get(str(health), "неизвестно")

    mapping = {
        "start": (
            "Контроль контекста подключён к новому проекту. "
            "Сформирован базовый снимок до масштабной реализации."
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
        "finish": "Сессия завершена. Сохраните итог и проверьте сопоставимость измерений.",
        "optimize": (
            "Подготовлен план оптимизации. "
            "Никакие изменения не применялись автоматически."
        ),
    }
    base = mapping.get(command, "Проверка контекста завершена.")
    return (
        f"{base} Состояние: {health_ru}. "
        f"Замечаний в компактном отчёте: {findings}."
    )


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
    audit = audit_extended.audit_extended(
        project,
        include_global=include_global,
    )
    pmap = project_map.build_project_map(project)
    warnings = []
    try:
        runtime = collect_runtime(provider, project, telemetry_root)
    except (OSError, ValueError, RuntimeError):
        runtime = None
        warnings.append("Телеметрия недоступна. Статический аудит выполнен; расход токенов неизвестен.")
    runtime_audit.merge(audit, runtime)

    try:
        ledger = ledger_summary(project)
    except (OSError, ValueError, RuntimeError):
        ledger = None
        warnings.append("Журнал изменений не удалось прочитать. Нельзя считать, что изменений не было.")

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
        "schema_version": "0.3",
        "command": command,
        "project_root": str(project.resolve()),
        "provider": provider,
        "message_ru": command_message(command, bridge),
        "bridge": bridge,
        "audit": audit,
        "runtime": runtime,
        "warnings": warnings + ((runtime or {}).get("warnings", [])),
    }

    if command in {"start", "adopt", "resume"}:
        result["baseline_candidate"] = {
            "snapshot_id": bridge.get("snapshotId"),
            "captured_at": bridge.get("capturedAt"),
            "mode": trigger_mode,
            "persist_by_controller": True,
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


def parse_signal(raw: str | None) -> dict[str, Any]:
    if raw is None:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Некорректный JSON сигнала: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Сигнал должен быть JSON object")
    return value


def run_auto(
    project: Path,
    *,
    signal: dict[str, Any],
    provider: str | None,
    include_global: bool,
    telemetry_root: str | None,
) -> dict[str, Any]:
    decision = trigger_policy.decide(signal)

    if not decision.get("run"):
        return {
            "schema_version": "0.3",
            "command": "auto",
            "status": "SKIPPED",
            "project_root": str(project.resolve()),
            "decision": decision,
            "message_ru": (
                "Дополнительная проверка контекста сейчас не нужна. "
                "Новых подтверждённых сигналов перегрузки нет."
            ),
        }

    command = str(decision.get("command") or "check")
    result = run_command(
        command,
        project,
        provider=provider,
        include_global=include_global,
        telemetry_root=telemetry_root,
        trigger_mode=str(decision.get("mode") or "PRESSURE_EVENT"),
        trigger_reason=str(decision.get("reason") or "") or None,
        trigger_automatic=bool(decision.get("automatic") is True),
    )
    result["requested_command"] = "auto"
    result["decision"] = decision
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Context Optimizer — единая команда"
    )
    parser.add_argument("--project", default=".")
    parser.add_argument(
        "--provider",
        choices=["auto", "codex", "claude", "antigravity", "none"],
        default="auto",
    )
    parser.add_argument("--telemetry-root")
    parser.add_argument("--include-global", action="store_true")
    parser.add_argument("--trigger-mode", default="MANUAL")
    parser.add_argument("--trigger-reason")
    parser.add_argument("--automatic", action="store_true")
    parser.add_argument(
        "--signal",
        help=(
            "JSON object для внутренней команды auto. "
            "Используется Matreshka Agent без временного файла."
        ),
    )
    parser.add_argument("--output")
    parser.add_argument("--full", action="store_true", help="Вывести полный аудит (по умолчанию только компактный bridge)")

    sub = parser.add_subparsers(dest="command", required=True)
    for name in (
        "start",
        "adopt",
        "resume",
        "check",
        "status",
        "optimize",
        "auto",
    ):
        sub.add_parser(name)

    args = parser.parse_args()
    project = Path(args.project).expanduser().resolve()
    if not project.exists() or not project.is_dir():
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "error": f"Проект не найден: {project}",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    provider = (
        detect_provider()
        if args.provider == "auto"
        else (None if args.provider == "none" else args.provider)
    )

    try:
        if args.command == "auto":
            result = run_auto(
                project,
                signal=parse_signal(args.signal),
                provider=provider,
                include_global=args.include_global,
                telemetry_root=args.telemetry_root,
            )
        else:
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
    except ValueError as exc:
        print(
            json.dumps(
                {"status": "ERROR", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    if not args.full:
        result = {k: v for k, v in result.items() if k not in {"audit", "runtime"}}
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
