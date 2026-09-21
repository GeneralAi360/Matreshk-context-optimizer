#!/usr/bin/env python3
"""Smoke test native project map + trigger policy."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import project_map
import trigger_policy


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src").mkdir()
        (root / "tests").mkdir()
        (root / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
        (root / "tests" / "test_app.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
        (root / "AGENTS.md").write_text("Правила проекта\n", encoding="utf-8")

        pmap = project_map.build_project_map(root)
        assert pmap["state"] == "READY"
        assert pmap["file_count"] == 3
        assert pmap["area_count"] >= 2
        assert pmap["navigation_pressure"] == "LOW"

        new_project = trigger_policy.decide({
            "scenario": "NEW_PROJECT",
            "baseline_exists": False,
        })
        assert new_project["run"] is True
        assert new_project["command"] == "start"
        assert new_project["automatic"] is True

        existing = trigger_policy.decide({
            "scenario": "EXISTING_PROJECT",
            "baseline_exists": False,
        })
        assert existing["command"] == "adopt"

        pressure = trigger_policy.decide({
            "scenario": "CONTINUE_PROJECT",
            "baseline_exists": True,
            "repeated_file_reads": 4,
        })
        assert pressure["command"] == "check"
        assert pressure["mode"] == "PRESSURE_EVENT"

        quiet = trigger_policy.decide({
            "scenario": "CONTINUE_PROJECT",
            "baseline_exists": True,
        })
        assert quiet["run"] is False
        assert quiet["mode"] == "NO_TRIGGER"

    print("PASS: project map and trigger policy smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
