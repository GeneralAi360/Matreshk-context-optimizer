#!/usr/bin/env python3
"""Minimal no-dependency smoke test for the read-only static auditor."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "skills" / "context-optimizer" / "scripts" / "audit_static_context.py"

    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / "module").mkdir()
        (project / "AGENTS.md").write_text(
            "# Root\nВсегда запускай тесты перед завершением задачи.\n",
            encoding="utf-8",
        )
        (project / "module" / "AGENTS.md").write_text(
            "# Module\nВсегда запускай тесты перед завершением задачи.\n",
            encoding="utf-8",
        )

        proc = subprocess.run(
            [sys.executable, str(script), "--project", str(project)],
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(proc.stdout)

    assert report["mode"] == "READ_ONLY"
    assert report["summary"]["context_health"] == "UNKNOWN"
    assert any(x["category"] == "INSTRUCTION_DUPLICATION" for x in report["findings"])
    assert all(
        x["measurement_type"] != "HEURISTIC_ESTIMATE"
        for x in report["measurements"]
    )
    print("PASS: static audit smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
