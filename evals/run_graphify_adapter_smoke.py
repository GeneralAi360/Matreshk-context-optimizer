#!/usr/bin/env python3
"""Smoke test Gate 7 Graphify Adapter без установки Graphify."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import graphify_adapter as ga


def touch(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Маленький проект без graph/evidence не должен автоматически рекомендовать Graphify.
        touch(root / "app.py", "print('ok')\n")
        status = ga.build_status(root, platform="codex", min_files=10, min_bytes=100000)
        assert status["recommendation"]["action"] == "NOT_NEEDED_BY_CURRENT_EVIDENCE"

        # Evidence повторных чтений должен усилить рекомендацию.
        evidence = {
            "findings": [
                {
                    "category": "CODEBURN_REDUNDANT_REREADS",
                    "problem": {"title": "Repeated reads", "description": "same files"},
                }
            ]
        }
        status_with_evidence = ga.build_status(
            root,
            platform="codex",
            evidence=evidence,
            min_files=1000,
            min_bytes=100000000,
        )
        assert status_with_evidence["evidence_hits"] == ["CODEBURN_REDUNDANT_REREADS"]
        assert status_with_evidence["recommendation"]["action"] in {
            "INSTALL_RECOMMENDED",
            "BUILD_RECOMMENDED",
        }

        # Проверяем platform-specific install plans.
        assert ga.project_install_command("codex") == [
            "graphify", "install", "--project", "--platform", "codex"
        ]
        assert ga.project_install_command("claude") == [
            "graphify", "install", "--project"
        ]
        assert ga.project_install_command("antigravity") == [
            "graphify", "install", "--project", "--platform", "antigravity"
        ]

        # Готовый graph должен включать fast path.
        graph = root / "graphify-out" / "graph.json"
        graph.parent.mkdir(parents=True, exist_ok=True)
        graph.write_text(
            json.dumps({"nodes": [{"id": "A"}], "edges": []}),
            encoding="utf-8",
        )

        # Сделаем graph новее source.
        source_mtime = (root / "app.py").stat().st_mtime
        os.utime(graph, (source_mtime + 10, source_mtime + 10))

        touch(root / ".agents" / "skills" / "graphify" / "SKILL.md", "# Graphify\n")
        ready = ga.build_status(root, platform="codex")
        assert ready["graph"]["exists"] is True
        assert ready["graph"]["nodes"] == 1
        assert ready["project_install"]["state"] == "INSTALLED"
        assert ready["recommendation"]["action"] == "USE_EXISTING_GRAPH"

        plan = ga.build_plan(ready)
        assert any(step["id"] == "USE_GRAPH_FIRST" for step in plan["steps"])
        assert all(
            step["approval_required"] is True
            for step in plan["steps"]
            if step.get("mutation")
        )

    print("PASS: graphify adapter smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
