#!/usr/bin/env python3
"""Read-only анализ потенциально дорогого context ingress payload."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from audit_common import finding, measurement


def detect_kind(text: str) -> tuple[str, dict[str, Any]]:
    stripped = text.lstrip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None

    if parsed is not None:
        if isinstance(parsed, list):
            return "json-array", {"items": len(parsed)}
        if isinstance(parsed, dict):
            return "json-object", {"keys": len(parsed)}
        return "json-scalar", {}

    lines = text.splitlines()
    diff_markers = sum(
        1
        for line in lines
        if line.startswith(("diff --git ", "@@ ", "+++ ", "--- ", "+", "-"))
    )
    if lines and diff_markers / max(len(lines), 1) >= 0.2:
        return "diff-like", {"diff_marker_lines": diff_markers}

    return "text-log", {}


def analyze_payload(
    text: str,
    *,
    large_bytes: int = 65_536,
    repetition_ratio: float = 0.35,
) -> dict[str, Any]:
    raw_bytes = len(text.encode("utf-8"))
    lines = text.splitlines()
    nonempty = [line.strip() for line in lines if line.strip()]
    counts = Counter(nonempty)
    repeated_copies = sum(max(0, count - 1) for count in counts.values())
    repeat_ratio = repeated_copies / len(nonempty) if nonempty else 0.0
    kind, details = detect_kind(text)

    measurements = [
        measurement(
            raw_bytes,
            "bytes",
            "BYTE_COUNT",
            "payload-audit",
            "HIGH",
            method="UTF-8 byte length",
            notes=f"kind={kind}",
        ),
        measurement(
            len(lines),
            "count",
            "TOOL_MEASURED",
            "payload-audit",
            "HIGH",
            method="line count",
        ),
    ]
    findings: list[dict[str, Any]] = []

    if raw_bytes >= large_bytes:
        findings.append(
            finding(
                "INGRESS_LARGE_PAYLOAD",
                "SESSION",
                "Payload достаточно крупный для проверки перед отправкой в контекст",
                (
                    f"Payload типа {kind} содержит {raw_bytes} байт. Порог {large_bytes} байт эвристический; "
                    "сам размер не доказывает, что данные лишние."
                ),
                [
                    {
                        "source": "payload-audit",
                        "detail": json.dumps(
                            {"kind": kind, "bytes": raw_bytes, "lines": len(lines), **details},
                            ensure_ascii=False,
                        ),
                        "locator": None,
                        "observed_at": None,
                    }
                ],
                measurement(
                    raw_bytes,
                    "bytes",
                    "BYTE_COUNT",
                    "payload-audit",
                    "HIGH",
                    method="UTF-8 byte length",
                ),
                direction="REDUCE_CONTEXT",
                effect="До передачи модели можно рассмотреть фильтрацию, выборку или recoverable-компрессию.",
                confidence="LOW",
                quality_risk="HIGH",
                action="REVIEW_INGRESS_PAYLOAD",
                proposal="Не обрезать payload автоматически; сначала определить, какие поля/строки нужны задаче и как восстановить оригинал.",
            )
        )

    if nonempty and repeat_ratio >= repetition_ratio and repeated_copies >= 10:
        top = [
            {"line": line[:300], "count": count}
            for line, count in counts.most_common(10)
            if count > 1
        ]
        findings.append(
            finding(
                "INGRESS_HIGH_REPETITION",
                "SESSION",
                "В payload много повторяющихся строк",
                (
                    f"Повторные копии составляют {repeat_ratio:.1%} непустых строк "
                    f"({repeated_copies} повторов)."
                ),
                [
                    {
                        "source": "payload-audit",
                        "detail": json.dumps(top, ensure_ascii=False),
                        "locator": None,
                        "observed_at": None,
                    }
                ],
                measurement(
                    round(repeat_ratio, 4),
                    "ratio",
                    "TOOL_MEASURED",
                    "payload-audit",
                    "HIGH",
                    method="duplicate non-empty line ratio",
                ),
                direction="REDUCE_CONTEXT",
                effect="Дедупликация повторяющихся диагностических строк может уменьшить ingress без потери уникальной информации.",
                confidence="HIGH",
                quality_risk="MEDIUM",
                action="REVIEW_DEDUPLICATION",
                proposal="Сохранять счётчики повторов и оригинал; не удалять уникальные строки.",
            )
        )

    return {
        "mode": "READ_ONLY",
        "kind": kind,
        "details": details,
        "measurements": measurements,
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only анализ входящего payload")
    parser.add_argument("--input", required=True, help="Текстовый/JSON/log/diff файл")
    parser.add_argument("--large-bytes", type=int, default=65_536)
    parser.add_argument("--repetition-ratio", type=float, default=0.35)
    args = parser.parse_args()

    path = Path(args.input).expanduser().resolve()
    text = path.read_text(encoding="utf-8", errors="replace")
    result = analyze_payload(
        text,
        large_bytes=args.large_bytes,
        repetition_ratio=args.repetition_ratio,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
