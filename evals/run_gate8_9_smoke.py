#!/usr/bin/env python3
"""Smoke tests Gate 8–9: dry-run/apply/rollback/ledger."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import change_executor as ce
import optimization_ledger as ledger


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # 1) Exact text replace.
        target = root / "AGENTS.md"
        target.write_text(
            "# Rules\nKeep this rule.\nDuplicate line.\nDuplicate line.\n",
            encoding="utf-8",
        )
        before_hash = ce.hash_path(target)

        change = {
            "change_id": "CHG-001",
            "operation": "REPLACE_EXACT_TEXT",
            "target": "AGENTS.md",
            "expected_before_sha256": before_hash,
            "source_finding_ids": ["CTX-001"],
            "approval_required": True,
            "quality_risk": "MEDIUM",
            "params": {
                "old": "Duplicate line.\nDuplicate line.\n",
                "new": "Duplicate line.\n",
                "expected_occurrences": 1,
            },
            "validation": {
                "must_contain": ["Keep this rule.", "Duplicate line."],
            },
        }

        dry = ce.dry_run(root, change, allow_global=False)
        assert dry["mutation"] is False
        assert not (root / ".context-optimizer").exists()

        try:
            ce.apply_change(root, change, approval="WRONG", allow_global=False)
        except ce.ChangeError:
            pass
        else:
            raise AssertionError("Apply without exact approval must fail")

        applied = ce.apply_change(
            root,
            change,
            approval="CHG-001",
            allow_global=False,
        )
        assert applied["status"] == "APPLIED"
        assert target.read_text(encoding="utf-8").count("Duplicate line.") == 1
        assert Path(applied["backup"]).exists()

        events = ledger.events_for_change(root, "CHG-001")
        assert events[-1]["status"] == "APPLIED"

        verification = ledger.append_event(
            root,
            ledger.verification_event(
                "CHG-001",
                finding_ids=["CTX-001"],
                status="KEEP",
                metrics={
                    "before": {"bytes": len("# Rules\nKeep this rule.\nDuplicate line.\nDuplicate line.\n".encode("utf-8"))},
                    "after": {"bytes": target.stat().st_size},
                },
                quality={"task_success": "PASS", "information_loss": "NO_DETECTED"},
                notes="Synthetic smoke verification",
            ),
        )
        assert verification["status"] == "KEEP"

        rolled = ce.rollback_change(
            root,
            "CHG-001",
            approval="CHG-001:ROLLBACK",
            allow_global=False,
        )
        assert rolled["status"] == "ROLLED_BACK"
        assert ce.hash_path(target) == before_hash
        assert ledger.events_for_change(root, "CHG-001")[-1]["status"] == "ROLLED_BACK"

        # 2) JSON_SET preserves reversibility.
        settings = root / "settings.json"
        settings.write_text(
            json.dumps({"tools": {"lazy": False}}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        json_before = ce.hash_path(settings)
        change_json = {
            "change_id": "CHG-002",
            "operation": "JSON_SET",
            "target": "settings.json",
            "expected_before_sha256": json_before,
            "source_finding_ids": ["CTX-002"],
            "approval_required": True,
            "quality_risk": "LOW",
            "params": {
                "path": ["tools", "lazy"],
                "value": True,
            },
            "validation": {},
        }
        ce.apply_change(root, change_json, approval="CHG-002", allow_global=False)
        assert json.loads(settings.read_text(encoding="utf-8"))["tools"]["lazy"] is True
        ce.rollback_change(
            root,
            "CHG-002",
            approval="CHG-002:ROLLBACK",
            allow_global=False,
        )
        assert ce.hash_path(settings) == json_before

        # 3) MOVE_PATH.
        source_dir = root / ".agents" / "skills" / "demo"
        source_dir.mkdir(parents=True)
        (source_dir / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
        move_before = ce.hash_path(source_dir)
        change_move = {
            "change_id": "CHG-003",
            "operation": "MOVE_PATH",
            "target": ".agents/skills/demo",
            "expected_before_sha256": move_before,
            "source_finding_ids": ["CTX-003"],
            "approval_required": True,
            "quality_risk": "MEDIUM",
            "params": {
                "destination": "project-skills/demo",
            },
            "validation": {},
        }
        ce.apply_change(root, change_move, approval="CHG-003", allow_global=False)
        assert not source_dir.exists()
        assert (root / "project-skills" / "demo" / "SKILL.md").exists()
        ce.rollback_change(
            root,
            "CHG-003",
            approval="CHG-003:ROLLBACK",
            allow_global=False,
        )
        assert source_dir.exists()
        assert ce.hash_path(source_dir) == move_before

        summary = ledger.summary(root)
        assert summary["change_count"] == 3
        assert summary["event_count"] >= 7

    print("PASS: gate 8-9 smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
