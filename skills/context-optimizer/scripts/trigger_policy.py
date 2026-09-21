#!/usr/bin/env python3
"""Детерминированная политика автозапуска Context Optimizer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def decide(signal: dict[str, Any]) -> dict[str, Any]:
    scenario = str(signal.get("scenario") or "UNKNOWN")
    baseline_exists = bool(signal.get("baseline_exists"))
    resumed = bool(signal.get("resumed"))
    context_too_broad = bool(signal.get("context_too_broad"))
    repeated_reads = int(signal.get("repeated_file_reads") or 0)
    compactions = int(signal.get("compactions") or 0)
    tool_ratio = float(signal.get("tool_result_ratio") or 0.0)
    tool_bytes = int(signal.get("tool_result_bytes") or 0)
    instruction_growth = int(signal.get("instruction_growth_bytes") or 0)
    skills_changed = bool(signal.get("skills_changed"))
    mcp_changed = bool(signal.get("mcp_changed"))
    project_files_delta = int(signal.get("project_files_delta") or 0)
    stale_hours = float(signal.get("hours_since_last_audit") or 0.0)
    manual = bool(signal.get("manual"))

    if manual:
        return {
            "run": True,
            "command": "check",
            "mode": "MANUAL",
            "reason": "Пользователь запросил проверку контекста.",
            "automatic": False,
        }

    if not baseline_exists and scenario == "NEW_PROJECT":
        return {
            "run": True,
            "command": "start",
            "mode": "NEW_PROJECT_BASELINE",
            "reason": "Новый проект: нужен базовый снимок до масштабной реализации.",
            "automatic": True,
        }

    if not baseline_exists and scenario == "EXISTING_PROJECT":
        return {
            "run": True,
            "command": "adopt",
            "mode": "EXISTING_PROJECT_ADOPTION",
            "reason": "Готовый проект подключается к Matreshka: нужен первичный аудит до изменения архитектуры.",
            "automatic": True,
        }

    if resumed and (not baseline_exists or stale_hours >= 24):
        return {
            "run": True,
            "command": "resume",
            "mode": "RESUME_RECONCILIATION",
            "reason": "Работа возобновлена после паузы: нужно сверить актуальность карты и контекста.",
            "automatic": True,
        }

    pressure_reasons: list[str] = []
    if context_too_broad:
        pressure_reasons.append("контекст помечен как слишком широкий")
    if repeated_reads >= 3:
        pressure_reasons.append(f"повторные чтения файлов: {repeated_reads}")
    if compactions >= 2:
        pressure_reasons.append(f"частые compaction: {compactions}")
    if tool_ratio >= 0.35 and tool_bytes >= 65536:
        pressure_reasons.append("результаты инструментов занимают заметную долю входного контекста")
    if instruction_growth >= 16384:
        pressure_reasons.append(f"инструкции выросли на {instruction_growth} байт")
    if skills_changed:
        pressure_reasons.append("изменился набор skills")
    if mcp_changed:
        pressure_reasons.append("изменилась конфигурация инструментов/MCP")
    if abs(project_files_delta) >= 100:
        pressure_reasons.append(f"структура проекта изменилась на {project_files_delta} файлов")

    if pressure_reasons:
        return {
            "run": True,
            "command": "check",
            "mode": "PRESSURE_EVENT",
            "reason": "; ".join(pressure_reasons[:5]),
            "automatic": True,
        }

    return {
        "run": False,
        "command": None,
        "mode": "NO_TRIGGER",
        "reason": "Нет подтверждённого сигнала, который оправдывает дополнительный аудит.",
        "automatic": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Политика автозапуска Context Optimizer")
    parser.add_argument("--signal-json", required=True)
    args = parser.parse_args()

    path = Path(args.signal_json).expanduser().resolve()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("signal-json должен содержать JSON object")
    print(json.dumps(decide(value), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
