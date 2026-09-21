#!/usr/bin/env python3
"""Read-only аудит skills: размер, frontmatter, scope и overlap описаний."""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path
from typing import Any

from audit_common import (
    finding,
    jaccard,
    line_count,
    measurement,
    parse_frontmatter,
    safe_read_text,
    semantic_terms,
    word_count,
)
from scan_environment import discover_skills


def audit_skills(
    root: Path,
    *,
    include_global: bool = False,
    review_lines: int = 400,
    review_words: int = 3000,
    description_chars: int = 500,
    overlap_threshold: float = 0.65,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = discover_skills(root, include_global=include_global)
    measurements: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    parsed: list[dict[str, Any]] = []

    for record in records:
        path = Path(record["absolute_path"])
        text = safe_read_text(path)
        if text is None:
            continue
        frontmatter, body = parse_frontmatter(text)
        description = frontmatter.get("description", "")
        lines = line_count(body)
        words = word_count(body)

        item = {
            **record,
            "description": description,
            "description_chars": len(description),
            "body_lines": lines,
            "body_words": words,
            "terms": semantic_terms(description),
        }
        parsed.append(item)

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

        if lines >= review_lines or words >= review_words:
            findings.append(
                finding(
                    "SKILL_BODY_REVIEW",
                    record["scope"],
                    "SKILL.md требует проверки на progressive disclosure",
                    (
                        f"{record['skill_name']}: body={lines} строк / {words} слов. "
                        "Размер — только сигнал для ревизии, а не доказательство плохого skill."
                    ),
                    [
                        {
                            "source": "skills-audit",
                            "detail": f"body_lines={lines}; body_words={words}",
                            "locator": record["path"],
                            "observed_at": None,
                        }
                    ],
                    measurement(
                        record["bytes"],
                        "bytes",
                        "BYTE_COUNT",
                        "filesystem",
                        "HIGH",
                        method="stat.st_size",
                    ),
                    direction="REDUCE_CONTEXT",
                    effect="Часть редких подробностей потенциально можно вынести в references и загружать по требованию.",
                    confidence="LOW",
                    quality_risk="HIGH",
                    action="REVIEW_SKILL_DISCLOSURE",
                    proposal="Проверить, какие инструкции нужны always-on, прежде чем делить skill.",
                    target=record["path"],
                )
            )

        if len(description) > description_chars:
            findings.append(
                finding(
                    "SKILL_DESCRIPTION_REVIEW",
                    record["scope"],
                    "Описание skill длиннее review-порога",
                    (
                        f"Описание {record['skill_name']} содержит {len(description)} символов. "
                        "Порог эвристический; сокращение допустимо только без ухудшения routing."
                    ),
                    [
                        {
                            "source": "skills-audit",
                            "detail": description[:1000],
                            "locator": record["path"],
                            "observed_at": None,
                        }
                    ],
                    measurement(
                        len(description.encode("utf-8")),
                        "bytes",
                        "BYTE_COUNT",
                        "skills-audit",
                        "HIGH",
                        method="UTF-8 byte length of frontmatter description",
                    ),
                    direction="REDUCE_CONTEXT",
                    effect="Более компактное описание может уменьшить skill-catalog overhead при сохранении точного trigger intent.",
                    confidence="LOW",
                    quality_risk="HIGH",
                    action="REVIEW_SKILL_DESCRIPTION",
                    proposal="Сокращать только после проверки, что trigger semantics сохраняются.",
                    target=record["path"],
                )
            )

    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in parsed:
        by_name.setdefault(item["skill_name"], []).append(item)

    for name, items in sorted(by_name.items()):
        scopes = {item["scope"] for item in items}
        if len(scopes) <= 1:
            continue
        findings.append(
            finding(
                "SKILL_SCOPE_COLLISION",
                "UNKNOWN",
                "Одинаковое имя skill найдено в нескольких scopes",
                f"Skill {name} присутствует в scopes: {', '.join(sorted(scopes))}. Это может быть намеренный override.",
                [
                    {
                        "source": "skills-audit",
                        "detail": json.dumps(
                            [{"scope": x["scope"], "path": x["path"], "host": x["host"]} for x in items],
                            ensure_ascii=False,
                        ),
                        "locator": None,
                        "observed_at": None,
                    }
                ],
                measurement(
                    len(items),
                    "count",
                    "TOOL_MEASURED",
                    "skills-audit",
                    "HIGH",
                    method="inventory by skill name",
                ),
                direction="IMPROVE_ROUTING",
                effect="Проверка может выявить ненужную глобальную регистрацию или подтвердить намеренный override.",
                confidence="MEDIUM",
                quality_risk="HIGH",
                action="REVIEW_SKILL_SCOPE",
                proposal="Не удалять копии автоматически; проверить usage и ожидаемый precedence.",
            )
        )

    for left, right in combinations(parsed, 2):
        if left["skill_name"] == right["skill_name"]:
            continue
        left_terms = left["terms"]
        right_terms = right["terms"]
        if len(left_terms) < 8 or len(right_terms) < 8:
            continue
        score = jaccard(left_terms, right_terms)
        if score < overlap_threshold:
            continue

        findings.append(
            finding(
                "SKILL_DESCRIPTION_OVERLAP",
                "UNKNOWN",
                "Описания двух skills сильно пересекаются",
                (
                    f"{left['skill_name']} и {right['skill_name']} имеют Jaccard={score:.2f} "
                    "по нормализованным терминам. Это детерминированный routing-сигнал, но не доказательство дублирования."
                ),
                [
                    {
                        "source": "skills-audit",
                        "detail": json.dumps(
                            {
                                "left": left["path"],
                                "right": right["path"],
                                "shared_terms": sorted(left_terms & right_terms),
                            },
                            ensure_ascii=False,
                        ),
                        "locator": f"{left['path']}; {right['path']}",
                        "observed_at": None,
                    }
                ],
                measurement(
                    round(score, 4),
                    "ratio",
                    "TOOL_MEASURED",
                    "skills-audit",
                    "HIGH",
                    method="Jaccard over normalized description terms",
                ),
                direction="IMPROVE_ROUTING",
                effect="Уточнение trigger descriptions может уменьшить routing ambiguity и случайную загрузку лишнего skill.",
                confidence="MEDIUM",
                quality_risk="MEDIUM",
                action="REVIEW_SKILL_ROUTING_OVERLAP",
                proposal="Сравнить реальное назначение skills и развести trigger intent, если пересечение не намеренное.",
            )
        )

    return measurements, findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only аудит skills")
    parser.add_argument("--project", default=".", help="Корень проекта")
    parser.add_argument("--include-global", action="store_true")
    parser.add_argument("--overlap-threshold", type=float, default=0.65)
    args = parser.parse_args()

    root = Path(args.project).expanduser().resolve()
    measurements, findings = audit_skills(
        root,
        include_global=args.include_global,
        overlap_threshold=args.overlap_threshold,
    )
    print(json.dumps({"mode": "READ_ONLY", "measurements": measurements, "findings": findings}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
