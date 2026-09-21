#!/usr/bin/env python3
"""Smoke test for optional CodeBurn parity oracle comparator."""

from __future__ import annotations

import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))

import compare_codeburn_context_oracle as oracle


def main() -> int:
    native = {
        "engine": "Matreshka Context Telemetry",
        "provider": "codex",
        "sessions": [
            {
                "session_id": "sess-123",
                "context": {
                    "reported_context_tokens": 18432,
                    "reported_context_measurement_type": "PROVIDER_MEASURED",
                    "reported_context_semantics": "CURRENT_CONTEXT",
                },
            }
        ],
    }
    codeburn = {"reported": {"context": 18432, "window": 200000}}

    exact = oracle.compare(native, codeburn, "sess-")
    assert exact["verdict"] == "PASS"
    assert exact["delta"] == 0

    mismatch = oracle.compare(native, {"reported": {"context": 18000}}, "sess-")
    assert mismatch["verdict"] == "MISMATCH"
    assert mismatch["delta"] == 432

    unverifiable = oracle.compare(
        {
            "engine": "Matreshka Context Telemetry",
            "provider": "codex",
            "sessions": [
                {
                    "session_id": "sess-123",
                    "context": {
                        "reported_context_tokens": None,
                        "reported_context_measurement_type": "UNKNOWN",
                    },
                }
            ],
        },
        codeburn,
        "sess-",
    )
    assert unverifiable["verdict"] == "UNVERIFIED"

    print("PASS: CodeBurn oracle comparator smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
