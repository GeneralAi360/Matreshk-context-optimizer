"""v0.4 change executor security and quality verification regression."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/context-optimizer/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True

import change_executor as ce


def run_record(value: int, *, errors: int = 0, info_loss: str = "NO"):
    return {
        "schema_version": "0.1",
        "run_id": "run",
        "task_id": "T-1",
        "task_class": "coding",
        "provider": "codex",
        "model": "same-model",
        "tokens": {
            "value": value,
            "metric": "TOTAL_RUN_TOKENS",
            "measurement_type": "PROVIDER_MEASURED",
            "source": "native-telemetry",
        },
        "quality": {
            "task_success": True,
            "retries": 0,
            "errors": errors,
            "wrong_file_reads": 0,
            "information_loss": info_loss,
        },
        "source": "fixture",
    }


class ChangeExecutor(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.target = self.root / "AGENTS.md"
        self.target.write_bytes(b"A\nB\n")

    def tearDown(self):
        self.temp.cleanup()

    def change(self, cid="CHG-101"):
        return {
            "change_id": cid,
            "operation": "REPLACE_EXACT_TEXT",
            "target": "AGENTS.md",
            "expected_before_sha256": ce.hash_path(self.target),
            "source_finding_ids": ["CTX-101"],
            "approval_required": True,
            "quality_risk": "LOW",
            "params": {"old": "B\n", "new": "C\n", "expected_occurrences": 1},
            "validation": {"must_contain": ["A\n", "C\n"]},
        }

    def apply(self, change=None):
        change = change or self.change()
        dry = ce.dry_run(self.root, change, allow_global=False)
        return ce.apply_change(
            self.root,
            change,
            approval=dry["approval_token_required_for_apply"],
            allow_global=False,
        )

    def test_approval_is_bound_to_exact_change(self):
        change = self.change()
        dry = ce.dry_run(self.root, change, allow_global=False)
        change["params"]["new"] = "D\n"
        with self.assertRaises(ce.ChangeError):
            ce.apply_change(
                self.root,
                change,
                approval=dry["approval_token_required_for_apply"],
                allow_global=False,
            )
        self.assertEqual(self.target.read_text(encoding="utf-8"), "A\nB\n")

    def test_target_change_invalidates_preview(self):
        change = self.change()
        dry = ce.dry_run(self.root, change, allow_global=False)
        self.target.write_bytes(b"A\nB\nUSER\n")
        with self.assertRaises(ce.ChangeError):
            ce.apply_change(
                self.root,
                change,
                approval=dry["approval_token_required_for_apply"],
                allow_global=False,
            )

    def test_reserved_state_and_git_are_blocked(self):
        for target in (".context-optimizer/x.txt", ".git/config"):
            path = self.root / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x", encoding="utf-8")
            change = self.change("CHG-102")
            change["target"] = target
            change["expected_before_sha256"] = ce.hash_path(path)
            with self.assertRaises(ce.ChangeError):
                ce.dry_run(self.root, change, allow_global=False)

    def test_bad_ids_and_extra_params_fail_closed(self):
        change = self.change()
        change["change_id"] = "oops"
        with self.assertRaises(ce.ChangeError):
            ce.validate_change(change)
        change = self.change()
        change["params"]["surprise"] = True
        with self.assertRaises(ce.ChangeError):
            ce.validate_change(change)

    def test_backup_corruption_blocks_rollback(self):
        applied = self.apply()
        backup = Path(applied["backup"])
        backup.write_bytes(b"corrupt")
        with self.assertRaises(ce.ChangeError):
            ce.rollback_change(
                self.root,
                "CHG-101",
                approval=applied["rollback_approval_token"],
                allow_global=False,
            )
        self.assertEqual(self.target.read_text(encoding="utf-8"), "A\nC\n")

    def test_post_apply_user_edit_blocks_rollback(self):
        applied = self.apply()
        self.target.write_bytes(b"A\nC\nUSER\n")
        with self.assertRaises(ce.ChangeError):
            ce.rollback_change(
                self.root,
                "CHG-101",
                approval=applied["rollback_approval_token"],
                allow_global=False,
            )
        self.assertIn("USER", self.target.read_text(encoding="utf-8"))

    def test_quality_pass_marks_keep(self):
        self.apply()
        before = self.root / "before.json"
        after = self.root / "after.json"
        before.write_text(json.dumps(run_record(1000)), encoding="utf-8")
        after.write_text(json.dumps(run_record(700)), encoding="utf-8")
        result = ce.verify_change(
            self.root,
            "CHG-101",
            before_run=before,
            after_run=after,
        )
        self.assertEqual(result["status"], "VERIFIED_KEEP")
        self.assertEqual(result["verification"]["verdict"], "PASS")

    def test_quality_fail_recommends_rollback_not_auto_rollback(self):
        self.apply()
        before = self.root / "before.json"
        after = self.root / "after.json"
        before.write_text(json.dumps(run_record(1000)), encoding="utf-8")
        after.write_text(json.dumps(run_record(700, errors=1)), encoding="utf-8")
        result = ce.verify_change(
            self.root,
            "CHG-101",
            before_run=before,
            after_run=after,
        )
        self.assertEqual(result["status"], "ROLLBACK_RECOMMENDED")
        self.assertTrue(result["rollback_approval_token"].startswith("ROLLBACK-"))
        self.assertEqual(self.target.read_text(encoding="utf-8"), "A\nC\n")

    def test_unverified_quality_never_becomes_keep(self):
        self.apply()
        before = run_record(1000)
        after = run_record(700)
        after["tokens"]["measurement_type"] = "HEURISTIC_ESTIMATE"
        p1 = self.root / "before.json"
        p2 = self.root / "after.json"
        p1.write_text(json.dumps(before), encoding="utf-8")
        p2.write_text(json.dumps(after), encoding="utf-8")
        result = ce.verify_change(self.root, "CHG-101", before_run=p1, after_run=p2)
        self.assertEqual(result["status"], "NEEDS_MORE_DATA")
        self.assertEqual(result["verification"]["verdict"], "UNVERIFIED")

    def test_symlink_target_refused(self):
        outside = self.root / "outside.txt"
        outside.write_text("B\n", encoding="utf-8")
        link = self.root / "link.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("Symlink unavailable")
        change = self.change("CHG-103")
        change["target"] = "link.txt"
        change["expected_before_sha256"] = ce.hash_file(outside)
        with self.assertRaises(ce.ChangeError):
            ce.dry_run(self.root, change, allow_global=False)


if __name__ == "__main__":
    unittest.main()