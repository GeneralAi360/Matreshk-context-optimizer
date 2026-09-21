#!/usr/bin/env python3
"""Read-only adapter for CodeBurn JSON output."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


_configure_utf8_stdio()

READ_ONLY_COMMANDS = {"optimize", "context", "doctor"}


class CodeBurnError(RuntimeError):
    pass


def codeburn_path() -> str | None:
    return shutil.which("codeburn")


def run_codeburn(args: list[str], timeout: int = 60) -> str:
    executable = codeburn_path()
    if not executable:
        raise CodeBurnError("CodeBurn не найден в PATH")

    if not args or args[0] not in READ_ONLY_COMMANDS:
        raise CodeBurnError("Adapter разрешает только read-only команды optimize/context/doctor")

    proc = subprocess.run(
        [executable, *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip() or f"exit={proc.returncode}"
        raise CodeBurnError(stderr)
    return proc.stdout


def get_version(timeout: int = 15) -> str | None:
    executable = codeburn_path()
    if not executable:
        return None
    proc = subprocess.run(
        [executable, "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def parse_json_text(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CodeBurnError(f"CodeBurn вернул невалидный JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise CodeBurnError("Ожидался JSON object от CodeBurn")
    return value


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CodeBurnError(f"Не удалось прочитать JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise CodeBurnError("Fixture/input должен быть JSON object")
    return value


def basis_to_measurement_type(basis: str | None) -> str:
    if basis == "measured":
        return "PROVIDER_MEASURED"
    if basis == "estimated":
        return "HEURISTIC_ESTIMATE"
    return "UNKNOWN"


def basis_to_confidence(basis: str | None) -> str:
    if basis == "measured":
        return "HIGH"
    if basis == "estimated":
        return "LOW"
    return "UNKNOWN"


def normalize_fix(raw_fix: Any) -> tuple[str, str, str | None]:
    if not isinstance(raw_fix, dict):
        return "REVIEW_CODEBURN_FINDING", "Проверить finding вручную.", None

    fix_type = str(raw_fix.get("type") or "unknown")
    label = str(raw_fix.get("label") or "CodeBurn recommendation")
    target = raw_fix.get("path")
    payload = {
        "type": fix_type,
        "label": label,
        "destination": raw_fix.get("destination"),
        "text": raw_fix.get("text"),
        "path": target,
    }
    description = "CodeBurn proposal: " + json.dumps(payload, ensure_ascii=False)
    return "REVIEW_CODEBURN_FINDING", description, str(target) if target else None


def normalize_optimize_report(
    report: dict[str, Any],
    tool_version: str | None = None,
) -> dict[str, Any]:
    raw_findings = report.get("findings")
    if raw_findings is None:
        raw_findings = []
    if not isinstance(raw_findings, list):
        raise CodeBurnError("Поле findings в CodeBurn optimize JSON должно быть массивом")

    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_findings, start=1):
        if not isinstance(raw, dict):
            continue

        basis = raw.get("basis")
        measurement_type = basis_to_measurement_type(str(basis) if basis is not None else None)
        confidence = basis_to_confidence(str(basis) if basis is not None else None)
        tokens_saved = raw.get("tokensSaved")

        if measurement_type == "UNKNOWN":
            value = None
            unit = "unknown"
        else:
            value = tokens_saved if isinstance(tokens_saved, (int, float)) else None
            unit = "tokens" if value is not None else "unknown"
            if value is None:
                measurement_type = "UNKNOWN"
                confidence = "UNKNOWN"

        action, proposal, target = normalize_fix(raw.get("fix"))
        codeburn_id = str(raw.get("id") or f"finding-{index}")
        raw_class = raw.get("class")
        raw_title = str(raw.get("title") or codeburn_id)
        explanation = str(raw.get("explanation") or "")
        severity = str(raw.get("severity") or "unknown")

        normalized.append(
            {
                "finding_id": f"CTX-{index:03d}",
                "category": "CODEBURN_" + codeburn_id.upper().replace("-", "_"),
                "platform": "codeburn",
                "scope": "UNKNOWN",
                "problem": {
                    "title": raw_title,
                    "description": explanation or "CodeBurn finding без дополнительного explanation.",
                },
                "evidence": [
                    {
                        "source": "codeburn",
                        "detail": json.dumps(
                            {
                                "id": codeburn_id,
                                "class": raw_class,
                                "basis": basis,
                                "severity": severity,
                                "trend": raw.get("trend"),
                                "estimatedSavingsUSD": raw.get("estimatedSavingsUSD"),
                            },
                            ensure_ascii=False,
                        ),
                        "locator": codeburn_id,
                        "observed_at": None,
                    }
                ],
                "measurement": {
                    "value": value,
                    "unit": unit,
                    "measurement_type": measurement_type,
                    "source": "codeburn",
                    "provider": None,
                    "tool": "codeburn",
                    "tool_version": tool_version,
                    "method": f"CodeBurn finding basis={basis}" if basis else "CodeBurn finding basis unknown",
                    "confidence": confidence,
                    "notes": "tokensSaved относится к потенциальной экономии finding, а не к текущему размеру контекста.",
                },
                "expected_effect": {
                    "direction": "REDUCE_TOKENS" if value is not None else "UNKNOWN",
                    "description": "Потенциальный эффект из CodeBurn finding; должен быть перепроверен после изменения.",
                    "estimated_saving": None,
                },
                "confidence": confidence,
                "quality_risk": "UNKNOWN",
                "proposal": {
                    "action": action,
                    "description": proposal,
                    "target": target,
                },
                "approval_required": True,
                "status": "OBSERVED",
            }
        )

    return {
        "adapter": "codeburn",
        "adapter_mode": "READ_ONLY",
        "tool_version": tool_version,
        "period": report.get("period"),
        "raw_summary": report.get("summary"),
        "findings": normalized,
    }


def collect_optimize(provider: str | None, period: str | None, timeout: int) -> dict[str, Any]:
    args = ["optimize", "--format", "json"]
    if provider:
        args.extend(["--provider", provider])
    if period:
        args.extend(["--period", period])
    raw = parse_json_text(run_codeburn(args, timeout=timeout))
    return normalize_optimize_report(raw, tool_version=get_version())


def collect_context(session: str, provider: str, timeout: int) -> dict[str, Any]:
    if provider not in {"claude", "codex"}:
        raise CodeBurnError("codeburn context upstream поддерживает provider claude или codex")
    raw = parse_json_text(
        run_codeburn(
            ["context", session, "--json", "--provider", provider],
            timeout=timeout,
        )
    )
    return {
        "adapter": "codeburn",
        "adapter_mode": "READ_ONLY",
        "tool_version": get_version(),
        "command": "context",
        "provider": provider,
        "session": session,
        "raw": raw,
    }


def collect_doctor(provider: str | None, timeout: int) -> dict[str, Any]:
    args = ["doctor", "--json"]
    if provider:
        args.extend(["--provider", provider])
    raw = parse_json_text(run_codeburn(args, timeout=timeout))
    return {
        "adapter": "codeburn",
        "adapter_mode": "READ_ONLY",
        "tool_version": get_version(),
        "command": "doctor",
        "provider": provider,
        "raw": raw,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only adapter для CodeBurn")
    parser.add_argument("--input", help="Разобрать сохранённый optimize JSON вместо запуска CodeBurn")
    parser.add_argument("--command", choices=["optimize", "context", "doctor"], default="optimize")
    parser.add_argument("--provider")
    parser.add_argument("--period")
    parser.add_argument("--session")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        if args.input:
            raw = load_json_file(Path(args.input).expanduser().resolve())
            result = normalize_optimize_report(raw, tool_version=None)
        elif args.command == "optimize":
            result = collect_optimize(args.provider, args.period, args.timeout)
        elif args.command == "context":
            if not args.session:
                raise CodeBurnError("--session обязателен для команды context")
            result = collect_context(args.session, args.provider or "claude", args.timeout)
        else:
            result = collect_doctor(args.provider, args.timeout)
    except (CodeBurnError, subprocess.TimeoutExpired) as exc:
        error = {
            "adapter": "codeburn",
            "adapter_mode": "READ_ONLY",
            "status": "UNAVAILABLE",
            "error": str(exc),
        }
        print(json.dumps(error, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).expanduser().resolve().write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())