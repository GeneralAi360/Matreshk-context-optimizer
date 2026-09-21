#!/usr/bin/env python3
"""Real-repository read-only pilot for Context Optimizer.

Designed to run against a checked-out real project (currently Matreshka Agent)
and prove that the audit/Graphify status/bridge path leaves the target untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import audit_extended
import graphify_adapter
import matreshka_bridge


SKIP_NAMES = {".git", ".context-optimizer", "__pycache__"}


def file_snapshot(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_NAMES for part in path.relative_to(root).parts):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result[path.relative_to(root).as_posix()] = digest
    return result


def run_pilot(root: Path) -> dict:
    before = file_snapshot(root)

    audit = audit_extended.audit_extended(root, include_global=False)
    graph = graphify_adapter.build_status(root, platform="codex")
    bridge = matreshka_bridge.build_bridge(audit, graphify=graph)

    after = file_snapshot(root)
    unchanged = before == after

    skills = audit.get("environment", {}).get("skills", [])
    runtime = bridge["runtimeMeasurement"]

    checks = {
        "target_unchanged": unchanged,
        "read_only_mode": audit.get("mode") == "READ_ONLY",
        "project_skills_discovered": isinstance(skills, list) and len(skills) > 0,
        "runtime_not_fabricated": runtime.get("value") is None and runtime.get("type") == "UNKNOWN",
        "static_context_unit_is_bytes": bridge["staticContext"]["unit"] == "bytes",
        "graphify_status_is_non_mutating": graph.get("adapter_mode") == "READ_ONLY",
        "optimizer_state_not_created": not (root / ".context-optimizer").exists(),
    }

    return {
        "schema_version": "0.1",
        "pilot": "REAL_REPOSITORY_READ_ONLY",
        "project_root": str(root.resolve()),
        "checks": checks,
        "pass": all(checks.values()),
        "observations": {
            "files_snapshotted": len(before),
            "skills_discovered": len(skills) if isinstance(skills, list) else 0,
            "findings": audit.get("summary", {}).get("finding_count"),
            "static_risk": audit.get("summary", {}).get("static_risk"),
            "runtime_measurement_state": bridge["runtimeMeasurement"]["status"],
            "graphify_recommendation": graph.get("recommendation", {}).get("action"),
            "graphify_evidence_basis": graph.get("recommendation", {}).get("basis"),
        },
        "runtime_savings_verdict": "UNVERIFIED",
        "runtime_savings_reason": "Пилот проверяет реальный repository read-only path, но не имеет сопоставимых provider-measured before/after agent sessions.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real-repository read-only Context Optimizer pilot")
    parser.add_argument("--project", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    root = Path(args.project).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Project root отсутствует: {root}")

    result = run_pilot(root)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    if not result["pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
