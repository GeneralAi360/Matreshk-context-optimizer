#!/usr/bin/env python3
"""Read-only аудит гигиены project instruction files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from audit_common import finding, line_count, measurement, safe_read_text
from scan_environment import discover_instruction_files

HISTORY_HEADING_RE = re.compile(
    r"(?im)^#{1,6}\s*(история|история изменений|журнал|progress|прогресс|changelog|что сделано|выполнено)\b"
)

TEMPORARY_RE = re.compile(
    r"(?i)\b(todo|fixme|temporary|temporarily|временно|временное|потом удалить|удалить позже)\b"
)


def audit_instruction_hygiene(
    root: Path,
    *,
    review_bytes: int = 24_000,
    review_lines: int = 400,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    measurements: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    for record in discover_instruction_files(root):
        path = Path(record["absolute_path"])
        text = safe_read_text(path)
        if text is None:
            continue

        lines = line_count(text)
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

        if record["bytes"] >= review_bytes or lines >= review_lines:
            findings.append(
                finding(
                    "INSTRUCTION_SIZE_REVIEW",
                    "PROJECT",
                    "Instruction file требует проверки на progressive disclosure",
                    (
                        f"{record['path']} содержит {record['bytes']} байт и {lines} строк. "
                        "Сам размер не доказывает лишний контекст, поэтому это review-кандидат, а не автоматический дефект."
                    ),
                    [
                        {
                            "source": "instruction-audit",
                            "detail": f"bytes={record['bytes']}; lines={lines}",
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
                    effect="Проверка может выявить материал, который лучше вынести в references и загружать по требованию.",
                    confidence="LOW",
                    quality_risk="HIGH",
                    action="REVIEW_PROGRESSIVE_DISCLOSURE",
                    proposal="Разделять файл только после проверки того, какие правила обязаны быть always-on.",
                    target=record["path"],
                )
            )

        history_matches = list(HISTORY_HEADING_RE.finditer(text))
        if history_matches:
            findings.append(
                finding(
                    "INSTRUCTION_HISTORY_CANDIDATE",
                    "PROJECT",
                    "В instruction file обнаружен раздел, похожий на историю/прогресс",
                    (
                        "История исполнения часто относится к recovery/ledger, а не к always-on инструкции. "
                        "Совпадение заголовка не доказывает ошибку и требует ручной проверки."
                    ),
                    [
                        {
                            "source": "instruction-audit",
                            "detail": match.group(0).strip(),
                            "locator": f"{record['path']}:{text[:match.start()].count(chr(10)) + 1}",
                            "observed_at": None,
                        }
                        for match in history_matches[:5]
                    ],
                    measurement(
                        len(history_matches),
                        "count",
                        "TOOL_MEASURED",
                        "instruction-audit",
                        "HIGH",
                        method="regex heading match",
                    ),
                    direction="REDUCE_CONTEXT",
                    effect="Если раздел действительно является историей выполнения, его можно вынести из always-on контекста.",
                    confidence="LOW",
                    quality_risk="HIGH",
                    action="REVIEW_HISTORY_SCOPE",
                    proposal="Проверить, является ли раздел текущим контрактом или устаревающей историей.",
                    target=record["path"],
                )
            )

        temporary_matches = list(TEMPORARY_RE.finditer(text))
        if temporary_matches:
            findings.append(
                finding(
                    "INSTRUCTION_TEMPORARY_MARKERS",
                    "PROJECT",
                    "В instruction file обнаружены временные маркеры",
                    (
                        "TODO/FIXME/«временно» в always-on инструкции могут со временем устаревать. "
                        "Наличие маркера само по себе не означает, что правило нужно удалить."
                    ),
                    [
                        {
                            "source": "instruction-audit",
                            "detail": match.group(0),
                            "locator": f"{record['path']}:{text[:match.start()].count(chr(10)) + 1}",
                            "observed_at": None,
                        }
                        for match in temporary_matches[:10]
                    ],
                    measurement(
                        len(temporary_matches),
                        "count",
                        "TOOL_MEASURED",
                        "instruction-audit",
                        "HIGH",
                        method="temporary-marker regex",
                    ),
                    direction="REDUCE_CONTEXT",
                    effect="Ревизия временных правил может убрать устаревший always-on контекст.",
                    confidence="LOW",
                    quality_risk="MEDIUM",
                    action="REVIEW_TEMPORARY_RULES",
                    proposal="Проверить актуальность каждого временного правила; ничего не удалять автоматически.",
                    target=record["path"],
                )
            )

    return measurements, findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only аудит project instruction files")
    parser.add_argument("--project", default=".", help="Корень проекта")
    parser.add_argument("--review-bytes", type=int, default=24_000)
    parser.add_argument("--review-lines", type=int, default=400)
    args = parser.parse_args()

    root = Path(args.project).expanduser().resolve()
    measurements, findings = audit_instruction_hygiene(
        root,
        review_bytes=args.review_bytes,
        review_lines=args.review_lines,
    )
    print(
        json.dumps(
            {"mode": "READ_ONLY", "measurements": measurements, "findings": findings},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
