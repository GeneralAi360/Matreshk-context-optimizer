#!/usr/bin/env python3
"""Read-only static context audit. Never converts byte counts into token counts."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from scan_environment import build_report


def normalize_line(value: str) -> str:
    return " ".join(value.strip().lower().split())


def line_occurrences(path: Path) -> list[tuple[int, str, str]]:
    items: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return items

    for number, raw in enumerate(text.splitlines(), start=1):
        normalized = normalize_line(raw)
        if not normalized:
            continue
        if len(normalized) < 12:
            continue
        if normalized.startswith(chr(96) * 3):
            continue
        items.append((number, raw.strip(), normalized))
    return items


def measurement(
    value,
    unit: str,
    measurement_type: str,
    source: str,
    confidence: str,
    **extra,
) -> dict:
    data = {
        "value": value,
        "unit": unit,
        "measurement_type": measurement_type,
        "source": source,
        "confidence": confidence,
    }
    data.update({k: v for k, v in extra.items() if v is not None})
    return data


def make_finding(
    idx: int,
    category: str,
    scope: str,
    title: str,
    description: str,
    evidence: list[dict],
    measure: dict,
    direction: str,
    effect: str,
    confidence: str,
    risk: str,
    action: str,
    proposal: str,
    target: str | None = None,
) -> dict:
    return {
        "finding_id": f"CTX-{idx:03d}",
        "category": category,
        "platform": "generic",
        "scope": scope,
        "problem": {"title": title, "description": description},
        "evidence": evidence,
        "measurement": measure,
        "expected_effect": {
            "direction": direction,
            "description": effect,
            "estimated_saving": None,
        },
        "confidence": confidence,
        "quality_risk": risk,
        "proposal": {
            "action": action,
            "description": proposal,
            "target": target,
        },
        "approval_required": True,
        "status": "OBSERVED",
    }


def audit(root: Path, include_global: bool) -> dict:
    scan = build_report(root, include_global=include_global)
    findings: list[dict] = []
    measurements: list[dict] = []
    next_id = 1

    instruction_records = scan["environment"]["instructions"]
    occurrence_map: dict[str, list[dict]] = defaultdict(list)

    for record in instruction_records:
        path = Path(record["absolute_path"])
        measurements.append(
            measurement(
                record["bytes"],
                "bytes",
                "BYTE_COUNT",
                "filesystem",
                "HIGH",
                method="stat.st_size",
                notes=f"instruction:{record['path']}",
            )
        )
        for line_no, raw, normalized in line_occurrences(path):
            occurrence_map[normalized].append(
                {
                    "path": record["path"],
                    "line": line_no,
                    "raw": raw,
                }
            )

    duplicate_groups = []
    for normalized, occurrences in occurrence_map.items():
        distinct_files = {item["path"] for item in occurrences}
        if len(distinct_files) > 1:
            duplicate_groups.append((normalized, occurrences))

    if duplicate_groups:
        examples = []
        duplicated_bytes = 0
        for normalized, occurrences in duplicate_groups[:20]:
            duplicated_bytes += len(normalized.encode("utf-8")) * (len(occurrences) - 1)
            examples.append(
                {
                    "text": normalized[:180],
                    "locations": [f"{x['path']}:{x['line']}" for x in occurrences],
                }
            )

        findings.append(
            make_finding(
                next_id,
                "INSTRUCTION_DUPLICATION",
                "PROJECT",
                "Повторяющиеся инструкции",
                f"Найдено {len(duplicate_groups)} нормализованных строк, которые встречаются более чем в одном instruction file.",
                [
                    {
                        "source": "static-audit",
                        "detail": json.dumps(examples, ensure_ascii=False),
                        "locator": "; ".join(sorted({loc for e in examples for loc in e["locations"]})),
                        "observed_at": None,
                    }
                ],
                measurement(
                    duplicated_bytes,
                    "bytes",
                    "BYTE_COUNT",
                    "static-audit",
                    "HIGH",
                    method="exact UTF-8 bytes of normalized duplicate copies in sampled groups",
                ),
                "REDUCE_CONTEXT",
                "Удаление подтверждённых дубликатов может уменьшить статический объём инструкций. Runtime token saving пока не измерен.",
                "HIGH",
                "MEDIUM",
                "REVIEW_DUPLICATE_SCOPE",
                "Проверить scope каждого дубля и удалить только действительно избыточные копии после отдельного approval.",
            )
        )
        next_id += 1

    skill_records = scan["environment"]["skills"]
    by_name: dict[str, list[dict]] = defaultdict(list)
    for record in skill_records:
        by_name[record["skill_name"]].append(record)
        measurements.append(
            measurement(
                record["bytes"],
                "bytes",
                "BYTE_COUNT",
                "filesystem",
                "HIGH",
                method="stat.st_size",
                notes=f"skill:{record['scope']}:{record['path']}",
            )
        )

    collisions = {
        name: records
        for name, records in by_name.items()
        if len({r["scope"] for r in records}) > 1
    }
    if collisions:
        details = [
            {
                "skill": name,
                "copies": [
                    {"scope": r["scope"], "host": r["host"], "path": r["path"]}
                    for r in records
                ],
            }
            for name, records in sorted(collisions.items())
        ]
        findings.append(
            make_finding(
                next_id,
                "SKILL_SCOPE_COLLISION",
                "UNKNOWN",
                "Одинаковые skills найдены в нескольких scopes",
                "Совпадение имени skill в global и project scope может быть намеренным override, поэтому автоматически считать его мусором нельзя.",
                [
                    {
                        "source": "static-audit",
                        "detail": json.dumps(details, ensure_ascii=False),
                        "locator": None,
                        "observed_at": None,
                    }
                ],
                measurement(
                    None,
                    "unknown",
                    "UNKNOWN",
                    "static-audit",
                    "UNKNOWN",
                    method="inventory-only",
                ),
                "IMPROVE_ROUTING",
                "Проверка scope может убрать ненужную глобальную регистрацию или выявить намеренный override.",
                "MEDIUM",
                "HIGH",
                "REVIEW_SKILL_SCOPE",
                "Не удалять и не перемещать skill автоматически. Сначала проверить usage и routing.",
            )
        )
        next_id += 1

    graph_state = scan["environment"]["graphify"]
    if graph_state["graph_exists"]:
        measurements.append(
            measurement(
                1,
                "count",
                "TOOL_MEASURED",
                "filesystem",
                "HIGH",
                method="graphify-out/graph.json existence check",
                notes="Graphify graph detected; this does not prove freshness.",
            )
        )

    static_risk = "WARNING" if findings else "OK"

    return {
        "schema_version": "0.1",
        "mode": "READ_ONLY",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(root.resolve()),
        "environment": scan["environment"],
        "capabilities": scan["capabilities"],
        "measurements": measurements,
        "findings": findings,
        "summary": {
            "context_health": "UNKNOWN",
            "static_risk": static_risk,
            "finding_count": len(findings),
            "runtime_measurement_state": "UNKNOWN",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only static Context Optimizer audit")
    parser.add_argument("--project", default=".", help="Project root")
    parser.add_argument("--include-global", action="store_true")
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    root = Path(args.project).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Project root does not exist or is not a directory: {root}")

    report = audit(root, include_global=args.include_global)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)

    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
