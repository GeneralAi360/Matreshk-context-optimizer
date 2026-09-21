#!/usr/bin/env python3
"""Smoke test Gate 5–6: инструкции, skills, MCP и context ingress."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run_json(script: Path, *args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        check=True,
        capture_output=True,
        text=True,
            encoding="utf-8",
    )
    return json.loads(proc.stdout)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    scripts = repo_root / "skills" / "context-optimizer" / "scripts"

    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / ".agents" / "skills" / "alpha").mkdir(parents=True)
        (project / ".agents" / "skills" / "beta").mkdir(parents=True)
        (project / ".claude").mkdir(parents=True)

        (project / "AGENTS.md").write_text(
            "# Правила\n"
            "Всегда запускай тесты перед завершением задачи.\n"
            "# История изменений\n"
            "Временно сохраняем старый маршрут до миграции.\n",
            encoding="utf-8",
        )

        shared = (
            "Use when analyzing project context tokens skills mcp tools instructions "
            "routing optimization audit performance context usage project workflow"
        )
        (project / ".agents" / "skills" / "alpha" / "SKILL.md").write_text(
            f"---\nname: alpha\ndescription: {shared} alpha\n---\n# Alpha\n",
            encoding="utf-8",
        )
        (project / ".agents" / "skills" / "beta" / "SKILL.md").write_text(
            f"---\nname: beta\ndescription: {shared} beta\n---\n# Beta\n",
            encoding="utf-8",
        )

        missing_command = "ctx-opt-command-that-does-not-exist-987654"
        (project / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "duplicate-server": {"command": missing_command},
                    }
                }
            ),
            encoding="utf-8",
        )
        (project / ".claude" / "settings.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "duplicate-server": {"command": missing_command},
                    }
                }
            ),
            encoding="utf-8",
        )

        extended = run_json(
            scripts / "audit_extended.py",
            "--project",
            str(project),
        )
        categories = {item["category"] for item in extended["findings"]}
        assert "INSTRUCTION_HISTORY_CANDIDATE" in categories
        assert "INSTRUCTION_TEMPORARY_MARKERS" in categories
        assert "SKILL_DESCRIPTION_OVERLAP" in categories
        assert "MCP_DUPLICATE_REGISTRATION" in categories
        assert "MCP_COMMAND_NOT_FOUND" in categories
        assert extended["summary"]["runtime_measurement_state"] == "UNKNOWN"

        payload_path = project / "tool-output.log"
        payload_path.write_text(("same diagnostic line\n" * 30) + "unique line\n", encoding="utf-8")
        payload_report = run_json(
            scripts / "analyze_payload.py",
            "--input",
            str(payload_path),
            "--large-bytes",
            "100",
            "--repetition-ratio",
            "0.30",
        )
        payload_categories = {item["category"] for item in payload_report["findings"]}
        assert "INGRESS_LARGE_PAYLOAD" in payload_categories
        assert "INGRESS_HIGH_REPETITION" in payload_categories

        context_path = project / "context.json"
        context_path.write_text(
            json.dumps(
                {
                    "reported": {"context": 12000, "window": 200000},
                    "effective": {
                        "tokens": 10000,
                        "toolResult": {"count": 12, "tokens": 6000},
                    },
                }
            ),
            encoding="utf-8",
        )
        context_report = run_json(
            scripts / "analyze_context_tree.py",
            "--input",
            str(context_path),
        )
        exact = [
            item
            for item in context_report["measurements"]
            if item["measurement_type"] == "PROVIDER_MEASURED"
        ]
        estimated = [
            item
            for item in context_report["measurements"]
            if item["measurement_type"] == "HEURISTIC_ESTIMATE"
        ]
        assert exact and exact[0]["value"] == 12000
        assert estimated
        assert any(
            item["category"] == "TOOL_RESULT_DOMINANCE"
            for item in context_report["findings"]
        )

    print("PASS: gate 5-6 smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())