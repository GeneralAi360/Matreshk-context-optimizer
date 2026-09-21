#!/usr/bin/env python3
"""Evaluate comparable before/after Context Optimizer runs without fake precision."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


_configure_utf8_stdio()

MEASURED_TYPES = {"PROVIDER_MEASURED", "TOOL_MEASURED"}


class BenchmarkError(RuntimeError):
    pass


def load_run(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"Не удалось прочитать {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BenchmarkError(f"{path} должен содержать JSON object")
    return value


def evaluate(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    comparable = True

    for key in ("task_id", "task_class", "provider", "model"):
        if before.get(key) != after.get(key):
            comparable = False
            reasons.append(f"Несопоставимое поле {key}: {before.get(key)!r} != {after.get(key)!r}")

    bt = before.get("tokens") if isinstance(before.get("tokens"), dict) else {}
    at = after.get("tokens") if isinstance(after.get("tokens"), dict) else {}

    for key in ("metric", "measurement_type", "source"):
        if bt.get(key) != at.get(key):
            comparable = False
            reasons.append(f"Token measurement {key} различается: {bt.get(key)!r} != {at.get(key)!r}")

    btype = bt.get("measurement_type")
    atype = at.get("measurement_type")
    if btype not in MEASURED_TYPES or atype not in MEASURED_TYPES:
        comparable = False
        reasons.append("Acceptance требует сопоставимых PROVIDER_MEASURED или TOOL_MEASURED runtime metrics")

    bvalue = bt.get("value")
    avalue = at.get("value")
    if not isinstance(bvalue, (int, float)) or not isinstance(avalue, (int, float)):
        comparable = False
        reasons.append("До/после отсутствует числовая runtime token metric")

    token_absolute = None
    token_percent = None
    if isinstance(bvalue, (int, float)) and isinstance(avalue, (int, float)):
        token_absolute = avalue - bvalue
        if bvalue > 0:
            token_percent = (avalue - bvalue) / bvalue * 100

    bq = before.get("quality") if isinstance(before.get("quality"), dict) else {}
    aq = after.get("quality") if isinstance(after.get("quality"), dict) else {}

    task_success_preserved = (
        bq.get("task_success") is True and aq.get("task_success") is True
        if "task_success" in bq and "task_success" in aq
        else None
    )

    def non_increasing(key: str) -> bool | None:
        left, right = bq.get(key), aq.get(key)
        if isinstance(left, int) and isinstance(right, int):
            return right <= left
        return None

    retries_ok = non_increasing("retries")
    errors_ok = non_increasing("errors")
    wrong_reads_ok = non_increasing("wrong_file_reads")
    info_loss_absent = aq.get("information_loss") == "NO" if "information_loss" in aq else None

    quality_values = [
        task_success_preserved,
        retries_ok,
        errors_ok,
        wrong_reads_ok,
        info_loss_absent,
    ]
    if any(value is None for value in quality_values):
        comparable = False
        reasons.append("Не хватает обязательной quality evidence")

    if not comparable:
        verdict = "UNVERIFIED"
    else:
        token_improved = avalue < bvalue
        quality_pass = all(value is True for value in quality_values)
        verdict = "PASS" if token_improved and quality_pass else "FAIL"

        if not token_improved:
            reasons.append("Runtime token/context cost не снизился")
        if task_success_preserved is not True:
            reasons.append("Task success не сохранён")
        if retries_ok is not True:
            reasons.append("Retries выросли")
        if errors_ok is not True:
            reasons.append("Errors выросли")
        if wrong_reads_ok is not True:
            reasons.append("Wrong-file reads выросли")
        if info_loss_absent is not True:
            reasons.append("Information loss не подтверждён как отсутствующий")

    if verdict == "PASS":
        reasons.append("Measured cost снизился без зафиксированной quality regression")

    return {
        "schema_version": "0.1",
        "verdict": verdict,
        "comparable": comparable,
        "reasons": reasons,
        "token_delta": {
            "before": bvalue if isinstance(bvalue, (int, float)) else None,
            "after": avalue if isinstance(avalue, (int, float)) else None,
            "absolute": token_absolute,
            "percent": round(token_percent, 4) if token_percent is not None else None,
        },
        "quality": {
            "task_success_preserved": task_success_preserved,
            "retries_non_increasing": retries_ok,
            "errors_non_increasing": errors_ok,
            "wrong_file_reads_non_increasing": wrong_reads_ok,
            "information_loss_absent": info_loss_absent,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate before/after optimization runs")
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        result = evaluate(
            load_run(Path(args.before).expanduser().resolve()),
            load_run(Path(args.after).expanduser().resolve()),
        )
    except BenchmarkError as exc:
        print(json.dumps({"verdict": "UNVERIFIED", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).expanduser().resolve().write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
