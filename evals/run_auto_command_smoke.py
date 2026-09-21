#!/usr/bin/env python3
"""Smoke test unified commands, automatic trigger, and baseline snapshot."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import context_optimizer


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / "src").mkdir()
        (project / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
        (project / "AGENTS.md").write_text("Правила проекта\n", encoding="utf-8")

        started = context_optimizer.run_auto(
            project,
            signal={
                "scenario": "NEW_PROJECT",
                "baseline_exists": False,
            },
            provider=None,
            include_global=False,
            telemetry_root=None,
        )
        assert started["command"] == "start"
        assert started["requested_command"] == "auto"
        assert started["baseline_candidate"]["persist_by_controller"] is True
        assert started["bridge"]["snapshotId"].startswith("CTXSNAP-")
        assert started["bridge"]["trigger"]["mode"] == "NEW_PROJECT_BASELINE"
        assert started["bridge"]["trigger"]["automatic"] is True
        assert started["bridge"]["trigger"]["nextCheck"]
        assert started["bridge"]["projectMap"]["state"] == "READY"
        assert not (project / ".context-optimizer").exists()

        quiet = context_optimizer.run_auto(
            project,
            signal={
                "scenario": "CONTINUE_PROJECT",
                "baseline_exists": True,
            },
            provider=None,
            include_global=False,
            telemetry_root=None,
        )
        assert quiet["status"] == "SKIPPED"
        assert quiet["decision"]["mode"] == "NO_TRIGGER"

        pressure = context_optimizer.run_auto(
            project,
            signal={
                "scenario": "CONTINUE_PROJECT",
                "baseline_exists": True,
                "repeated_file_reads": 4,
            },
            provider=None,
            include_global=False,
            telemetry_root=None,
        )
        assert pressure["command"] == "check"
        assert pressure["bridge"]["trigger"]["mode"] == "PRESSURE_EVENT"
        assert "повторные чтения" in pressure["bridge"]["trigger"]["reason"]

        manual = context_optimizer.run_command(
            "status",
            project,
            provider=None,
            include_global=False,
            telemetry_root=None,
            trigger_mode="MANUAL",
            trigger_reason="Пользователь запросил статус",
            trigger_automatic=False,
        )
        assert "Текущее состояние контекста" in manual["message_ru"]
        assert manual["bridge"]["snapshotId"].startswith("CTXSNAP-")

    print("PASS: auto command and baseline snapshot smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
