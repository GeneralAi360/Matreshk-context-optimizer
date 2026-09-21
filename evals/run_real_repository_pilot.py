#!/usr/bin/env python3
"""Real-repository read-only pilot for Context Optimizer."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import audit_extended
import matreshka_bridge
import project_map


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
    pmap = project_map.build_project_map(root)
    bridge = matreshka_bridge.build_bridge(audit, project_map=pmap)

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
        "native_project_map_ready": bridge["projectMap"]["state"] == "READY",
        "optimizer_state_not_created": not (root / ".context-optimizer").exists(),
    }

    return {
        "schema_version": "0.2",
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
            "project_files": pmap.get("file_count"),
            "project_areas": pmap.get("area_count"),
            "navigation_pressure": pmap.get("navigation_pressure"),
        },
        "runtime_savings_verdict": "UNVERIFIED",
        "runtime_savings_reason": "Пилот проверяет read-only интеграцию; для runtime savings нужны сопоставимые provider-measured before/after сессии.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only пилот Context Optimizer на реальном репозитории")
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

    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
