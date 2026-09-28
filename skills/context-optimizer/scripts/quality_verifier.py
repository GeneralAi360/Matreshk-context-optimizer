#!/usr/bin/env python3
"""Проверка эффективности конкретного изменения без ложного PASS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from optimization_ledger import append_event


MEASURED_TYPES = {"PROVIDER_MEASURED", "TOOL_MEASURED"}


class VerificationError(RuntimeError):
    pass


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"Не удалось прочитать {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} должен содержать JSON object")
    return value


def evaluate_runs(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    comparable = True

    for key in ("task_id", "task_class", "provider", "model"):
        if before.get(key) != after.get(key):
            comparable = False
            reasons.append(
                f"Несопоставимое поле {key}: {before.get(key)!r} != {after.get(key)!r}"
            )

    bt = before.get("tokens") if isinstance(before.get("tokens"), dict) else {}
    at = after.get("tokens") if isinstance(after.get("tokens"), dict) else {}

    for key in ("metric", "measurement_type", "source"):
        if bt.get(key) != at.get(key):
            comparable = False
            reasons.append(
                f"Token measurement {key} различается: "
                f"{bt.get(key)!r} != {at.get(key)!r}"
            )

    if bt.get("measurement_type") not in MEASURED_TYPES or at.get("measurement_type") not in MEASURED_TYPES:
        comparable = False
        reasons.append(
            "Для полного PASS нужны сопоставимые provider/tool-measured runtime metrics."
        )

    bvalue = bt.get("value")
    avalue = at.get("value")
    if isinstance(bvalue, bool) or isinstance(avalue, bool):
        comparable = False
        reasons.append("Булево значение не является числовой token metric.")
        bvalue = None
        avalue = None
    if not isinstance(bvalue, (int, float)) or not isinstance(avalue, (int, float)):
        comparable = False
        reasons.append("До/после отсутствует числовая runtime token metric.")

    bq = before.get("quality") if isinstance(before.get("quality"), dict) else {}
    aq = after.get("quality") if isinstance(after.get("quality"), dict) else {}

    def non_increasing(key: str) -> bool | None:
        left, right = bq.get(key), aq.get(key)
        if isinstance(left, bool) or isinstance(right, bool):
            return None
        if isinstance(left, int) and isinstance(right, int):
            return right <= left
        return None

    task_success_preserved = (
        bq.get("task_success") is True and aq.get("task_success") is True
        if "task_success" in bq and "task_success" in aq
        else None
    )
    retries_ok = non_increasing("retries")
    errors_ok = non_increasing("errors")
    wrong_reads_ok = non_increasing("wrong_file_reads")
    information_loss_absent = (
        aq.get("information_loss") == "NO"
        if "information_loss" in aq
        else None
    )

    quality_values = [
        task_success_preserved,
        retries_ok,
        errors_ok,
        wrong_reads_ok,
        information_loss_absent,
    ]
    if any(value is None for value in quality_values):
        comparable = False
        reasons.append("Не хватает обязательной quality evidence.")

    absolute = None
    percent = None
    if isinstance(bvalue, (int, float)) and isinstance(avalue, (int, float)):
        absolute = avalue - bvalue
        if bvalue > 0:
            percent = (avalue - bvalue) / bvalue * 100

    if not comparable:
        verdict = "UNVERIFIED"
    else:
        token_improved = avalue < bvalue
        quality_pass = all(value is True for value in quality_values)
        verdict = "PASS" if token_improved and quality_pass else "FAIL"
        if not token_improved:
            reasons.append("Измеренный runtime context/token cost не снизился.")
        if task_success_preserved is not True:
            reasons.append("Task success не сохранён.")
        if retries_ok is not True:
            reasons.append("Retries выросли.")
        if errors_ok is not True:
            reasons.append("Errors выросли.")
        if wrong_reads_ok is not True:
            reasons.append("Wrong-file reads выросли.")
        if information_loss_absent is not True:
            reasons.append("Отсутствие потери информации не подтверждено.")

    if verdict == "PASS":
        reasons.append(
            "Измеренный cost снизился без зафиксированной quality regression."
        )

    return {
        "schema_version": "0.2",
        "verdict": verdict,
        "comparable": comparable,
        "reasons": reasons,
        "token_delta": {
            "before": bvalue if isinstance(bvalue, (int, float)) else None,
            "after": avalue if isinstance(avalue, (int, float)) else None,
            "absolute": absolute,
            "percent": round(percent, 4) if percent is not None else None,
        },
        "quality": {
            "task_success_preserved": task_success_preserved,
            "retries_non_increasing": retries_ok,
            "errors_non_increasing": errors_ok,
            "wrong_file_reads_non_increasing": wrong_reads_ok,
            "information_loss_absent": information_loss_absent,
        },
    }


def ledger_status(verdict: str) -> str:
    if verdict == "PASS":
        return "KEEP"
    if verdict == "FAIL":
        return "ROLLBACK"
    return "NEEDS_MORE_DATA"


def record_change_verification(
    project_root: Path,
    change_id: str,
    finding_ids: list[str],
    result: dict[str, Any],
) -> dict[str, Any]:
    status = ledger_status(str(result.get("verdict")))
    event = {
        "event_type": "VERIFICATION",
        "change_id": change_id,
        "status": status,
        "finding_ids": finding_ids,
        "metrics": result.get("token_delta"),
        "quality": result.get("quality"),
        "notes": "; ".join(str(x) for x in result.get("reasons") or []),
    }
    return append_event(project_root, event)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Сравнить before/after и записать решение по изменению."
    )
    parser.add_argument("--project", default=".")
    parser.add_argument("--change-id", required=True)
    parser.add_argument("--finding-id", action="append", default=[])
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()

    try:
        result = evaluate_runs(
            load_object(Path(args.before).expanduser().resolve()),
            load_object(Path(args.after).expanduser().resolve()),
        )
        if args.record:
            event = record_change_verification(
                Path(args.project).expanduser().resolve(),
                args.change_id,
                list(args.finding_id),
                result,
            )
            result["ledger_event"] = event
    except VerificationError as exc:
        print(
            json.dumps(
                {"verdict": "UNVERIFIED", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
