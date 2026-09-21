#!/usr/bin/env python3
"""Smoke test нормализации CodeBurn optimize JSON без установки CodeBurn."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SAMPLE = {
    "period": {"label": "Test", "start": None, "end": None},
    "summary": {
        "healthScore": 72,
        "healthGrade": "C",
        "findingCount": 2,
        "periodCostUSD": 10.0,
        "sessions": 4,
        "calls": 20,
        "potentialSavingsTokens": 5000,
        "potentialSavingsCostUSD": 1.2,
        "potentialSavingsPercent": 12.0,
        "costRateUSD": 0.0002,
        "measuredSavingsUSD": 0.8,
        "byClass": {},
    },
    "findings": [
        {
            "id": "redundant-rereads",
            "title": "Repeated reads",
            "explanation": "Same file was read repeatedly.",
            "severity": "high",
            "trend": "active",
            "tokensSaved": 4200,
            "estimatedSavingsUSD": 0.8,
            "class": "nudge",
            "basis": "measured",
            "fix": {
                "type": "paste",
                "label": "Use one summary",
                "text": "Reuse prior context",
                "destination": "prompt",
            },
        },
        {
            "id": "unused-mcp",
            "title": "Unused MCP",
            "explanation": "Configured but not invoked.",
            "severity": "medium",
            "trend": None,
            "tokensSaved": 800,
            "estimatedSavingsUSD": 0.4,
            "class": "fix",
            "basis": "estimated",
            "fix": {
                "type": "command",
                "label": "Review MCP",
                "text": "manual review only",
            },
        },
    ],
}


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    adapter = repo_root / "skills" / "context-optimizer" / "scripts" / "codeburn_adapter.py"

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "optimize.json"
        source.write_text(json.dumps(SAMPLE), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(adapter), "--input", str(source)],
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(proc.stdout)

    assert report["adapter_mode"] == "READ_ONLY"
    assert len(report["findings"]) == 2

    measured = report["findings"][0]["measurement"]
    estimated = report["findings"][1]["measurement"]

    assert measured["measurement_type"] == "PROVIDER_MEASURED"
    assert measured["value"] == 4200
    assert estimated["measurement_type"] == "HEURISTIC_ESTIMATE"
    assert estimated["value"] == 800
    assert all(x["approval_required"] is True for x in report["findings"])

    print("PASS: codeburn adapter smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
