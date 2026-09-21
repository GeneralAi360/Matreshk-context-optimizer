#!/usr/bin/env python3
"""Smoke coverage for Gate 11 before/after evaluator."""

from __future__ import annotations

import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))

import evaluate_before_after as ev


def run(tokens_before, tokens_after, *, measurement_type="PROVIDER_MEASURED", retries_after=1, errors_after=0, wrong_reads_after=0, information_loss="NO"):
    base = {
        "schema_version": "0.1",
        "run_id": "before",
        "task_id": "T-001",
        "task_class": "coding",
        "provider": "codex",
        "model": "same-model",
        "tokens": {
            "value": tokens_before,
            "metric": "TOTAL_RUN_TOKENS",
            "measurement_type": measurement_type,
            "source": "codeburn",
        },
        "quality": {
            "task_success": True,
            "retries": 1,
            "errors": 0,
            "wrong_file_reads": 0,
            "information_loss": "NO",
        },
        "source": "fixture",
    }
    after = {
        **base,
        "run_id": "after",
        "tokens": {
            **base["tokens"],
            "value": tokens_after,
        },
        "quality": {
            "task_success": True,
            "retries": retries_after,
            "errors": errors_after,
            "wrong_file_reads": wrong_reads_after,
            "information_loss": information_loss,
        },
    }
    return ev.evaluate(base, after)


def main() -> int:
    passed = run(100_000, 70_000)
    assert passed["verdict"] == "PASS"
    assert passed["token_delta"]["percent"] == -30.0

    no_saving = run(100_000, 100_000)
    assert no_saving["verdict"] == "FAIL"

    regression = run(100_000, 60_000, errors_after=1)
    assert regression["verdict"] == "FAIL"

    heuristic = run(100_000, 50_000, measurement_type="HEURISTIC_ESTIMATE")
    assert heuristic["verdict"] == "UNVERIFIED"

    unknown_loss = run(100_000, 50_000, information_loss="UNKNOWN")
    assert unknown_loss["verdict"] == "FAIL"

    print("PASS: benchmark evaluator smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
