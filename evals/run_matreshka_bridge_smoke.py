#!/usr/bin/env python3
"""Smoke test compact Matreshka bridge."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import matreshka_bridge as mb


def main() -> int:
    audit = {
        "schema_version": "0.2",
        "mode": "READ_ONLY",
        "environment": {
            "instructions": [
                {"path": "AGENTS.md", "absolute_path": "/p/AGENTS.md", "bytes": 1200},
                {"path": "module/AGENTS.md", "absolute_path": "/p/module/AGENTS.md", "bytes": 800},
                {"path": "AGENTS.md", "absolute_path": "/p/AGENTS.md", "bytes": 1200},
            ]
        },
        "summary": {
            "context_health": "WARNING",
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
                "proposal": {"action": "REVIEW_DUPLICATE_SCOPE", "description": "Проверить scope."},
            }
        ],
    }

    project_map = {
        "state": "READY",
        "navigation_pressure": "MEDIUM",
        "file_count": 420,
        "area_count": 12,
        "reason": "Средний проект: использовать карту областей.",
    }

    static_bridge = mb.build_bridge(
        audit,
        project_map=project_map,
        trigger={"mode": "EXISTING_PROJECT_ADOPTION", "reason": "Первичное подключение", "automatic": True},
    )
    assert static_bridge["schemaVersion"] == "0.3"
    assert static_bridge["staticContext"]["value"] == 2000
    assert static_bridge["runtimeMeasurement"]["value"] is None
    assert static_bridge["runtimeMeasurement"]["type"] == "UNKNOWN"
    assert static_bridge["projectMap"]["pressure"] == "MEDIUM"
    assert static_bridge["trigger"]["automatic"] is True
    assert static_bridge["approvalRequired"] is True
    assert static_bridge["snapshotId"].startswith("CTXSNAP-")
    assert static_bridge["trigger"]["nextCheck"]

    runtime = {
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
        project_map=project_map,
        ledger=ledger,
    )
    assert bridge["runtimeMeasurement"]["value"] == 22222
    assert bridge["runtimeMeasurement"]["source"] == "native:codex"
    assert bridge["runtimeMeasurement"]["semantics"] == "CURRENT_CONTEXT"
    assert bridge["ledger"]["pendingVerification"] == 1

    unsafe = mb.build_bridge(audit, runtime={"usage": {"total_tokens": 999999}})
    assert unsafe["runtimeMeasurement"]["value"] is None
    assert unsafe["runtimeMeasurement"]["type"] == "UNKNOWN"

    print("PASS: matreshka bridge smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())