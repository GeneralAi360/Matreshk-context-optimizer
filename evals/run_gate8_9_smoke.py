#!/usr/bin/env python3
"""Smoke tests Gate 8–9: content-bound approval, backup, verify, rollback, ledger."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import change_executor as ce
import optimization_ledger as ledger


def apply_with_preview(root: Path, change: dict):
    dry = ce.dry_run(root, change, allow_global=False)
    return ce.apply_change(
        root,
        change,
        approval=dry["approval_token_required_for_apply"],
        allow_global=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        target = root / "AGENTS.md"
        target.write_bytes(
            b"# Rules\r\nKeep this rule.\r\nDuplicate line.\r\nDuplicate line.\r\n"
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
                "old": "Duplicate line.\r\nDuplicate line.\r\n",
                "new": "Duplicate line.\r\n",
                "expected_occurrences": 1,
            },
            "validation": {"must_contain": ["Keep this rule.", "Duplicate line."]},
        }

        dry = ce.dry_run(root, change, allow_global=False)
        assert dry["mutation"] is False
        assert dry["approval_token_required_for_apply"].startswith("APPLY-")
        assert not (root / ".context-optimizer").exists()

        try:
            ce.apply_change(root, change, approval="CHG-001", allow_global=False)
        except ce.ChangeError:
            pass
        else:
            raise AssertionError("Legacy approval must fail")

        applied = ce.apply_change(
            root,
            change,
            approval=dry["approval_token_required_for_apply"],
            allow_global=False,
        )
        assert applied["status"] == "APPLIED"
        assert b"\r\n" in target.read_bytes()
        assert Path(applied["backup"]).exists()
        assert ce.hash_path(Path(applied["backup"])) == before_hash
        assert applied["rollback_approval_token"].startswith("ROLLBACK-")

        status = ce.status_change(root, "CHG-001")
        assert status["integrity"]["backup_integrity"] is True
        assert status["integrity"]["current_after_integrity"] is True

        rolled = ce.rollback_change(
            root,
            "CHG-001",
            approval=status["rollback_approval_token"],
            allow_global=False,
        )
        assert rolled["status"] == "ROLLED_BACK"
        assert ce.hash_path(target) == before_hash

        settings = root / "settings.json"
        settings.write_text(
            json.dumps({"tools": {"lazy": False}}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        change_json = {
            "change_id": "CHG-002",
            "operation": "JSON_SET",
            "target": "settings.json",
            "expected_before_sha256": ce.hash_path(settings),
            "source_finding_ids": ["CTX-002"],
            "approval_required": True,
            "quality_risk": "LOW",
            "params": {"path": ["tools", "lazy"], "value": True},
            "validation": {},
        }
        applied_json = apply_with_preview(root, change_json)
        assert json.loads(settings.read_text(encoding="utf-8"))["tools"]["lazy"] is True
        ce.rollback_change(
            root,
            "CHG-002",
            approval=applied_json["rollback_approval_token"],
            allow_global=False,
        )

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
            "params": {"destination": "project-skills/demo"},
            "validation": {},
        }
        applied_move = apply_with_preview(root, change_move)
        assert not source_dir.exists()
        assert (root / "project-skills" / "demo" / "SKILL.md").exists()
        ce.rollback_change(
            root,
            "CHG-003",
            approval=applied_move["rollback_approval_token"],
            allow_global=False,
        )
        assert ce.hash_path(source_dir) == move_before

        summary = ledger.summary(root)
        assert summary["change_count"] == 3
        assert summary["event_count"] >= 6

    print("PASS: gate 8-9 smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
