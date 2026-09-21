#!/usr/bin/env python3
"""Read-only анализ CodeBurn context tree с честным provenance метрик."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from audit_common import finding, measurement


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Ожидался JSON object")
    return data


def unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("raw")
    if isinstance(raw, dict) and payload.get("adapter") == "codeburn":
        return raw
    return payload


def num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def analyze_context_tree(
    payload: dict[str, Any],
    *,
    tool_result_ratio: float = 0.35,
    tool_result_tokens: int = 4000,
) -> dict[str, Any]:
    tree = unwrap(payload)
    measurements: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    reported = tree.get("reported")
    if isinstance(reported, dict):
        exact_context = num(reported.get("context"))
        if exact_context is not None:
            measurements.append(
                measurement(
                    int(exact_context),
                    "tokens",
                    "PROVIDER_MEASURED",
                    "codeburn-context",
                    "HIGH",
                    method="CodeBurn reported.context from provider usage",
                    tool="codeburn",
                    notes="Точное reported context значение; не смешивать с оценочными block tokens.",
                )
            )

    effective = tree.get("effective")
    if not isinstance(effective, dict):
        return {
            "mode": "READ_ONLY",
            "measurements": measurements,
            "findings": findings,
            "status": "PARTIAL",
            "warning": "В payload отсутствует effective context snapshot.",
        }

    effective_tokens = num(effective.get("tokens"))
    if effective_tokens is not None:
        measurements.append(
            measurement(
                int(effective_tokens),
                "tokens",
                "HEURISTIC_ESTIMATE",
                "codeburn-context",
                "LOW",
                method="CodeBurn context-tree block estimate; upstream uses character-based estimation for blocks",
                tool="codeburn",
                notes="Это НЕ provider-measured context size.",
            )
        )

    tool_result = effective.get("toolResult")
    tool_result_value = None
    if isinstance(tool_result, dict):
        tool_result_value = num(tool_result.get("tokens"))

    if tool_result_value is not None:
        measurements.append(
            measurement(
                int(tool_result_value),
                "tokens",
                "HEURISTIC_ESTIMATE",
                "codeburn-context",
                "LOW",
                method="CodeBurn block estimate for toolResult",
                tool="codeburn",
            )
        )

    if (
        tool_result_value is not None
        and effective_tokens is not None
        and effective_tokens > 0
    ):
        ratio = tool_result_value / effective_tokens
        measurements.append(
            measurement(
                round(ratio, 4),
                "ratio",
                "TOOL_MEASURED",
                "context-ingress-audit",
                "HIGH",
                method="toolResult estimated tokens / effective estimated tokens",
                notes="Ratio детерминирован, но основан на двух estimated block counts.",
            )
        )

        if tool_result_value >= tool_result_tokens and ratio >= tool_result_ratio:
            findings.append(
                finding(
                    "TOOL_RESULT_DOMINANCE",
                    "SESSION",
                    "Результаты инструментов занимают большую долю оценочного effective context",
                    (
                        f"CodeBurn оценивает tool results примерно в {int(tool_result_value)} токенов "
                        f"из {int(effective_tokens)} ({ratio:.1%}). Block counts upstream являются оценочными."
                    ),
                    [
                        {
                            "source": "codeburn-context",
                            "detail": json.dumps(
                                {
                                    "toolResultTokensEstimated": tool_result_value,
                                    "effectiveTokensEstimated": effective_tokens,
                                    "ratio": ratio,
                                },
                                ensure_ascii=False,
                            ),
                            "locator": None,
                            "observed_at": None,
                        }
                    ],
                    measurement(
                        int(tool_result_value),
                        "tokens",
                        "HEURISTIC_ESTIMATE",
                        "codeburn-context",
                        "LOW",
                        method="CodeBurn toolResult block estimate",
                        tool="codeburn",
                    ),
                    direction="REDUCE_CONTEXT",
                    effect="Фильтрация или recoverable-компрессия крупных tool results может уменьшить context ingress.",
                    confidence="MEDIUM",
                    quality_risk="HIGH",
                    action="REVIEW_TOOL_RESULT_INGRESS",
                    proposal="Сначала определить конкретные крупные tool outputs; не обрезать данные без механизма восстановления.",
                )
            )

    return {
        "mode": "READ_ONLY",
        "measurements": measurements,
        "findings": findings,
        "status": "OK",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only анализ CodeBurn context tree")
    parser.add_argument("--input", required=True, help="JSON от codeburn context или Context Optimizer adapter")
    parser.add_argument("--tool-result-ratio", type=float, default=0.35)
    parser.add_argument("--tool-result-tokens", type=int, default=4000)
    args = parser.parse_args()

    result = analyze_context_tree(
        load_json(Path(args.input).expanduser().resolve()),
        tool_result_ratio=args.tool_result_ratio,
        tool_result_tokens=args.tool_result_tokens,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
