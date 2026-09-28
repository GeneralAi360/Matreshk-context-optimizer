#!/usr/bin/env python3
"""CLI-обёртка общего quality verifier для before/after Context Optimizer runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/context-optimizer/scripts"
sys.path.insert(0, str(SCRIPTS))

from quality_verifier import VerificationError, evaluate_runs, load_object

# Backward-compatible import surface for existing smoke/eval callers.
evaluate = evaluate_runs


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate before/after optimization runs")
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        result = evaluate_runs(
            load_object(Path(args.before).expanduser().resolve()),
            load_object(Path(args.after).expanduser().resolve()),
        )
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

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).expanduser().resolve().write_text(
            rendered + "\n",
            encoding="utf-8",
        )
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())