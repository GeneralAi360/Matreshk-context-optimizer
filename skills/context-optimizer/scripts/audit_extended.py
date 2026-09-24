#!/usr/bin/env python3
"""Сводный read-only аудит Gate 3–6 без mutation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from audit_common import renumber
from audit_instructions import audit_instruction_hygiene
from audit_mcp import audit_mcp
from audit_skills import audit_skills
from audit_static_context import audit as audit_static


def finding_key(item: dict[str, Any]) -> tuple[str, str]:
    category = str(item.get("category") or "")
    locator = ""
    evidence = item.get("evidence")
    if isinstance(evidence, list) and evidence:
        first = evidence[0]
        if isinstance(first, dict):
            locator = str(first.get("locator") or first.get("detail") or "")[:300]
    return category, locator


def audit_extended(root: Path, include_global: bool = False) -> dict[str, Any]:
    report = audit_static(root, include_global=include_global)
    measurements = list(report.get("measurements") or [])
    findings = list(report.get("findings") or [])

    instruction_measurements, instruction_findings = audit_instruction_hygiene(root)
    skill_measurements, skill_findings = audit_skills(root, include_global=include_global)
    mcp_measurements, mcp_findings, mcp_inventory = audit_mcp(root, include_global=include_global)

    measurements.extend(instruction_measurements)
    measurements.extend(skill_measurements)
    measurements.extend(mcp_measurements)

    seen = {finding_key(item) for item in findings}
    for item in instruction_findings + skill_findings + mcp_findings:
        key = finding_key(item)
        if key in seen:
            continue
        seen.add(key)
        findings.append(item)

    renumber(findings, start=1)

    environment = dict(report.get("environment") or {})
    environment["mcp_inventory"] = mcp_inventory

    summary = dict(report.get("summary") or {})
    summary["finding_count"] = len(findings)
    summary["static_risk"] = "WARNING" if findings else "OK"
    summary["runtime_measurement_state"] = "UNKNOWN"
    summary["context_health"] = "UNKNOWN"

    report["environment"] = environment
    unique = {}
    for metric in measurements:
        key = json.dumps(metric, sort_keys=True, ensure_ascii=False)
        unique[key] = metric
    report["measurements"] = list(unique.values())
    report["findings"] = findings
    report["summary"] = summary
    report["audit_layers"] = [
        "STATIC_CONTEXT",
        "INSTRUCTION_HYGIENE",
        "SKILLS",
        "MCP_CONFIG",
    ]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Сводный read-only аудит контекста проекта")
    parser.add_argument("--project", default=".", help="Корень проекта")
    parser.add_argument("--include-global", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    root = Path(args.project).expanduser().resolve()
    result = audit_extended(root, include_global=args.include_global)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).expanduser().resolve().write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
