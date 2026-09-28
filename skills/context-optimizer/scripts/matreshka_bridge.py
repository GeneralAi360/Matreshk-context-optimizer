#!/usr/bin/env python3
"""Компактный bridge между Context Optimizer и Matreshka Agent."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


_configure_utf8_stdio()


class BridgeError(RuntimeError):
    pass


def load_object(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BridgeError(f"Не удалось прочитать {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BridgeError(f"{path} должен содержать JSON object")
    return value


def static_context(audit: dict[str, Any]) -> dict[str, Any]:
    env = audit.get("environment")
    instructions = env.get("instructions") if isinstance(env, dict) else None
    total = 0
    count = 0
    seen: set[str] = set()
    if isinstance(instructions, list):
        for item in instructions:
            if not isinstance(item, dict):
                continue
            identity = str(item.get("absolute_path") or item.get("path") or "")
            if not identity or identity in seen:
                continue
            value = item.get("bytes")
            if isinstance(value, int) and value >= 0:
                seen.add(identity)
                total += value
                count += 1
    return {
        "value": total,
        "unit": "bytes",
        "source": "inventory-instructions",
        "fileCount": count,
    }


def runtime_from_native(payload: dict[str, Any] | None) -> dict[str, Any]:
    unknown = {
        "status": "UNKNOWN",
        "value": None,
        "unit": "unknown",
        "type": "UNKNOWN",
        "source": None,
        "semantics": "UNKNOWN",
    }
    if not payload or payload.get("engine") != "Matreshka Context Telemetry":
        return unknown

    provider = str(payload.get("provider") or "unknown")
    sessions = payload.get("sessions")
    if not isinstance(sessions, list):
        return unknown

    # Caller selects the newest matching session; never substitute an older
    # measured session when that latest session has no counters.
    for session in sessions[:1]:
        if not isinstance(session, dict):
            continue
        context = session.get("context")
        if not isinstance(context, dict):
            continue
        value = context.get("reported_context_tokens")
        measurement_type = context.get("reported_context_measurement_type")
        if not (
            type(value) in (int, float)
            and math.isfinite(value)
            and value >= 0
            and measurement_type == "PROVIDER_MEASURED"
        ):
            continue

        raw_semantics = str(context.get("reported_context_semantics") or "")
        if provider == "codex":
            current_semantics = {"CURRENT_CONTEXT"}
        elif provider == "antigravity":
            current_semantics = {"CURRENT_CONTEXT"}
        else:
            current_semantics = set()

        semantics = "CURRENT_CONTEXT" if raw_semantics in current_semantics else "OBSERVED_SUBSET"
        return {
            "status": "AVAILABLE" if semantics == "CURRENT_CONTEXT" else "PARTIAL",
            "value": value,
            "unit": "tokens",
            "type": "PROVIDER_MEASURED",
            "source": f"native:{provider}",
            "semantics": semantics,
        }
    return unknown


def compact_findings(
    audit: dict[str, Any],
    limit: int,
) -> tuple[list[dict[str, Any]], list[str], bool]:
    raw = audit.get("findings")
    if not isinstance(raw, list):
        return [], [], False

    def rank(item: dict[str, Any]) -> tuple[int, int]:
        risk = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "UNKNOWN": 3}.get(
            str(item.get("quality_risk")),
            3,
        )
        confidence = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "UNKNOWN": 3}.get(
            str(item.get("confidence")),
            3,
        )
        return risk, confidence

    valid = [item for item in raw if isinstance(item, dict)]
    valid.sort(key=rank)
    rows: list[dict[str, Any]] = []
    recommendations: list[str] = []
    approval = False

    for item in valid[:limit]:
        problem = item.get("problem") if isinstance(item.get("problem"), dict) else {}
        proposal = item.get("proposal") if isinstance(item.get("proposal"), dict) else {}
        action = str(proposal.get("action") or "REVIEW")
        rows.append(
            {
                "id": str(item.get("finding_id") or ""),
                "category": str(item.get("category") or "UNKNOWN"),
                "title": str(problem.get("title") or item.get("category") or "Проверка"),
                "confidence": str(item.get("confidence") or "UNKNOWN"),
                "qualityRisk": str(item.get("quality_risk") or "UNKNOWN"),
                "action": action,
            }
        )
        description = str(proposal.get("description") or "").strip()
        if description and description not in recommendations:
            recommendations.append(description)
        approval = approval or item.get("approval_required") is True

    return rows, recommendations[:limit], approval


def project_map_compact(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {
            "state": "UNKNOWN",
            "pressure": "UNKNOWN",
            "files": 0,
            "areas": 0,
            "reason": None,
        }
    state = str(payload.get("state") or "UNKNOWN")
    pressure = str(payload.get("navigation_pressure") or "UNKNOWN")
    return {
        "state": state if state in {"READY", "UNKNOWN"} else "UNKNOWN",
        "pressure": pressure if pressure in {"LOW", "MEDIUM", "HIGH", "UNKNOWN"} else "UNKNOWN",
        "files": int(payload.get("file_count") or 0),
        "areas": int(payload.get("area_count") or 0),
        "reason": str(payload.get("reason") or "") or None,
    }


def ledger_compact(payload: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    empty = {
        "changeCount": 0,
        "pendingVerification": 0,
        "rollbackRecommended": 0,
        "latestDecision": None,
    }
    if not payload:
        return empty, False

    changes = payload.get("changes")
    if not isinstance(changes, list):
        return empty, False

    pending = 0
    rollback = 0
    latest = None
    for item in changes:
        if not isinstance(item, dict):
            continue
        status = str(item.get("latest_status") or "")
        if status == "APPLIED":
            pending += 1
        if status == "ROLLBACK":
            rollback += 1
        if status:
            latest = status

    result = {
        "changeCount": int(payload.get("change_count") or len(changes)),
        "pendingVerification": pending,
        "rollbackRecommended": rollback,
        "latestDecision": latest,
    }
    return result, pending > 0 or rollback > 0


def next_check_text(
    *,
    trigger_mode: str,
    project_pressure: str,
    pending_verification: int,
    approval_required: bool,
) -> str:
    if pending_verification > 0:
        return "После завершения текущей проверки качества и повторного измерения."
    if approval_required:
        return "После подтверждения и применения выбранного изменения — повторно измерить контекст."
    if project_pressure == "HIGH":
        return "После следующей крупной задачи или существенного изменения структуры проекта."
    if trigger_mode in {"NEW_PROJECT_BASELINE", "EXISTING_PROJECT_ADOPTION", "RESUME_RECONCILIATION"}:
        return "При первом подтверждённом событии перегрузки или после заметного роста проекта."
    return "При новом событии перегрузки или существенном изменении проекта."


def snapshot_id(bridge_without_id: dict[str, Any]) -> str:
    stable = {
        "health": bridge_without_id.get("health"),
        "healthBasis": bridge_without_id.get("healthBasis"),
        "runtimeMeasurement": bridge_without_id.get("runtimeMeasurement"),
        "staticContext": bridge_without_id.get("staticContext"),
        "staticRisk": bridge_without_id.get("staticRisk"),
        "projectMap": bridge_without_id.get("projectMap"),
        "topFindings": bridge_without_id.get("topFindings"),
        "ledger": bridge_without_id.get("ledger"),
    }
    encoded = json.dumps(
        stable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "CTXSNAP-" + hashlib.sha256(encoded).hexdigest()[:16]


def build_bridge(
    audit: dict[str, Any],
    *,
    runtime: dict[str, Any] | None = None,
    project_map: dict[str, Any] | None = None,
    ledger: dict[str, Any] | None = None,
    finding_limit: int = 5,
    trigger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if audit.get("mode") != "READ_ONLY":
        raise BridgeError("Bridge принимает только read-only audit report")

    summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
    health = str(summary.get("context_health") or "UNKNOWN")
    if health not in {"OK", "WARNING", "CRITICAL", "UNKNOWN"}:
        health = "UNKNOWN"

    static_risk = str(summary.get("static_risk") or "UNKNOWN")
    if static_risk not in {"OK", "WARNING", "CRITICAL", "UNKNOWN"}:
        static_risk = "UNKNOWN"

    runtime_measurement = runtime_from_native(runtime)
    static_state = static_context(audit)
    if runtime_measurement["status"] == "AVAILABLE":
        health_basis = "MEASURED" if health != "UNKNOWN" else "PARTIAL"
    elif static_state["fileCount"] > 0:
        health_basis = "STATIC_ONLY"
    else:
        health_basis = "UNKNOWN"

    findings, recommendations, findings_need_approval = compact_findings(
        audit,
        finding_limit,
    )
    ledger_state, ledger_needs_approval = ledger_compact(ledger)
    project_state = project_map_compact(project_map)

    trigger_state = {
        "mode": str((trigger or {}).get("mode") or "MANUAL"),
        "reason": str((trigger or {}).get("reason") or "") or None,
        "automatic": bool((trigger or {}).get("automatic") is True),
        "nextCheck": None,
    }

    approval_required = findings_need_approval or ledger_needs_approval
    trigger_state["nextCheck"] = next_check_text(
        trigger_mode=trigger_state["mode"],
        project_pressure=project_state["pressure"],
        pending_verification=ledger_state["pendingVerification"],
        approval_required=approval_required,
    )

    bridge = {
        "schemaVersion": "0.3",
        "snapshotId": None,
        "capturedAt": audit.get("generated_at"),
        "status": "READY",
        "health": health,
        "healthBasis": health_basis,
        "runtimeMeasurement": runtime_measurement,
        "staticContext": static_state,
        "staticRisk": static_risk,
        "projectMap": project_state,
        "topFindings": findings,
        "recommendations": recommendations,
        "ledger": ledger_state,
        "trigger": trigger_state,
        "approvalRequired": approval_required,
        "source": {
            "auditSchemaVersion": audit.get("schema_version"),
            "runtimeSource": "native-telemetry" if runtime else None,
            "projectMapSource": "native-project-map" if project_map else None,
            "ledgerSource": "optimization-ledger" if ledger else None,
        },
    }
    bridge["snapshotId"] = snapshot_id(bridge)
    return bridge


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Собрать компактное состояние Context Optimizer для Matreshka Agent"
    )
    parser.add_argument("--audit", required=True)
    parser.add_argument("--runtime")
    parser.add_argument("--project-map")
    parser.add_argument("--ledger")
    parser.add_argument("--trigger-mode", default="MANUAL")
    parser.add_argument("--trigger-reason")
    parser.add_argument("--trigger-automatic", action="store_true")
    parser.add_argument("--finding-limit", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        audit = load_object(Path(args.audit).expanduser().resolve())
        assert audit is not None
        result = build_bridge(
            audit,
            runtime=load_object(Path(args.runtime).expanduser().resolve())
            if args.runtime
            else None,
            project_map=load_object(Path(args.project_map).expanduser().resolve())
            if args.project_map
            else None,
            ledger=load_object(Path(args.ledger).expanduser().resolve())
            if args.ledger
            else None,
            finding_limit=max(1, min(args.finding_limit, 8)),
            trigger={
                "mode": args.trigger_mode,
                "reason": args.trigger_reason,
                "automatic": args.trigger_automatic,
            },
        )
    except (BridgeError, AssertionError) as exc:
        print(
            json.dumps(
                {"status": "UNAVAILABLE", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
