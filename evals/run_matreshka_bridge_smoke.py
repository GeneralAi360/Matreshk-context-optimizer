#!/usr/bin/env python3
"""Smoke test Gate 10 compact Matreshka bridge."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import matreshka_bridge as mb


def main() -> int:
    audit = {
        "schema_version": "0.1",
        "mode": "READ_ONLY",
        "environment": {
            "instructions": [
                {"path": "AGENTS.md", "absolute_path": "/p/AGENTS.md", "bytes": 1200},
                {"path": "module/AGENTS.md", "absolute_path": "/p/module/AGENTS.md", "bytes": 800},
                # duplicate inventory record must not double count
                {"path": "AGENTS.md", "absolute_path": "/p/AGENTS.md", "bytes": 1200},
            ]
        },
        "summary": {
            "context_health": "UNKNOWN",
            "static_risk": "WARNING",
            "runtime_measurement_state": "UNKNOWN",
        },
        "findings": [
            {
                "finding_id": "CTX-001",
                "category": "INSTRUCTION_DUPLICATION",
                "confidence": "HIGH",
                "quality_risk": "MEDIUM",
                "approval_required": True,
                "problem": {"title": "Повторяющиеся инструкции"},
                "proposal": {
                    "action": "REVIEW_DUPLICATE_SCOPE",
                    "description": "Проверить scope.",
                },
            }
        ],
    }

    static_bridge = mb.build_bridge(audit)
    assert static_bridge["staticContext"]["value"] == 2000
    assert static_bridge["runtimeMeasurement"]["value"] is None
    assert static_bridge["runtimeMeasurement"]["type"] == "UNKNOWN"
    assert static_bridge["health"] == "UNKNOWN"
    assert static_bridge["healthBasis"] == "STATIC_ONLY"
    assert static_bridge["approvalRequired"] is True

    runtime = {
        "mode": "READ_ONLY",
        "measurements": [
            {
                "value": 18432,
                "unit": "tokens",
                "measurement_type": "PROVIDER_MEASURED",
                "source": "codeburn-context",
                "method": "CodeBurn reported.context from provider usage",
            },
            {
                "value": 9000,
                "unit": "tokens",
                "measurement_type": "HEURISTIC_ESTIMATE",
                "source": "codeburn-context",
                "method": "block estimate",
            },
        ],
    }
    graphify = {
        "recommendation": {
            "action": "USE_EXISTING_GRAPH",
            "reasons": ["graphify-out/graph.json уже существует"],
        },
        "graph": {"exists": True},
        "project_install": {"state": "INSTALLED"},
    }
    ledger = {
        "change_count": 2,
        "changes": [
            {"change_id": "CHG-001", "latest_status": "KEEP"},
            {"change_id": "CHG-002", "latest_status": "APPLIED"},
        ],
    }

    bridge = mb.build_bridge(
        audit,
        runtime=runtime,
        graphify=graphify,
        ledger=ledger,
    )
    assert bridge["runtimeMeasurement"]["value"] == 18432
    assert bridge["runtimeMeasurement"]["type"] == "PROVIDER_MEASURED"
    assert bridge["runtimeMeasurement"]["semantics"] == "CURRENT_CONTEXT"
    assert bridge["graphify"]["state"] == "READY"
    assert bridge["ledger"]["pendingVerification"] == 1
    assert bridge["approvalRequired"] is True

    native_runtime = {
        "engine": "Matreshka Context Telemetry",
        "provider": "codex",
        "sessions": [
            {
                "session_id": "native-1",
                "context": {
                    "reported_context_tokens": 22222,
                    "reported_context_measurement_type": "PROVIDER_MEASURED",
                    "reported_context_semantics": "CURRENT_CONTEXT",
                },
            }
        ],
    }
    native_bridge = mb.build_bridge(audit, runtime=native_runtime)
    assert native_bridge["runtimeMeasurement"]["value"] == 22222
    assert native_bridge["runtimeMeasurement"]["source"] == "matreshka-native:codex"
    assert native_bridge["runtimeMeasurement"]["semantics"] == "CURRENT_CONTEXT"

    # CodeBurn optimize token savings must NOT be accepted as current runtime context.
    optimize_like = {
        "findings": [
            {
                "measurement": {
                    "value": 5000,
                    "unit": "tokens",
                    "measurement_type": "PROVIDER_MEASURED",
                    "source": "codeburn",
                    "method": "CodeBurn finding basis=measured",
                }
            }
        ]
    }
    unsafe = mb.build_bridge(audit, runtime=optimize_like)
    assert unsafe["runtimeMeasurement"]["value"] is None
    assert unsafe["runtimeMeasurement"]["type"] == "UNKNOWN"

    print("PASS: matreshka bridge smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())