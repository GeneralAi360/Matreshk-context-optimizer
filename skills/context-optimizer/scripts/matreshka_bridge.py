#!/usr/bin/env python3
"""Build a compact, truthful Context Optimizer bridge for Matreshka Agent."""

from __future__ import annotations

import argparse
import json
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
        "source": "instruction-file inventory",
        "fileCount": count,
    }


def runtime_from_context_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    unknown = {
        "status": "UNKNOWN",
        "value": None,
        "unit": "unknown",
        "type": "UNKNOWN",
        "source": None,
        "semantics": "UNKNOWN",
    }
    if not payload:
        return unknown

    # Output from analyze_context_tree.py.
    measurements = payload.get("measurements")
    if isinstance(measurements, list):
        for item in measurements:
            if not isinstance(item, dict):
                continue
            if (
                item.get("measurement_type") == "PROVIDER_MEASURED"
                and item.get("unit") == "tokens"
                and item.get("source") == "codeburn-context"
                and "reported.context" in str(item.get("method") or "")
                and isinstance(item.get("value"), (int, float))
            ):
                return {
                    "status": "AVAILABLE",
                    "value": item["value"],
                    "unit": "tokens",
                    "type": "PROVIDER_MEASURED",
                    "source": "codeburn-context",
                    "semantics": "CURRENT_CONTEXT",
                }

    # Raw/adapter CodeBurn context tree.
    raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else payload
    reported = raw.get("reported") if isinstance(raw, dict) else None
    if isinstance(reported, dict) and isinstance(reported.get("context"), (int, float)):
        return {
            "status": "AVAILABLE",
            "value": reported["context"],
            "unit": "tokens",
            "type": "PROVIDER_MEASURED",
            "source": "codeburn-context",
            "semantics": "CURRENT_CONTEXT",
        }

    return unknown


def compact_findings(audit: dict[str, Any], limit: int) -> tuple[list[dict[str, Any]], list[str], bool]:
    raw = audit.get("findings")
    if not isinstance(raw, list):
        return [], [], False

    def rank(item: dict[str, Any]) -> tuple[int, int]:
        risk = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "UNKNOWN": 3}.get(str(item.get("quality_risk")), 3)
        confidence = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "UNKNOWN": 3}.get(str(item.get("confidence")), 3)
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
                "title": str(problem.get("title") or item.get("category") or "Finding"),
                "confidence": str(item.get("confidence") or "UNKNOWN"),
                "qualityRisk": str(item.get("quality_risk") or "UNKNOWN"),
                "action": action,
            }
        )
        description = str(proposal.get("description") or "").strip()
        recommendation = action if not description else f"{action}: {description}"
        if recommendation not in recommendations:
            recommendations.append(recommendation)
        approval = approval or item.get("approval_required") is True

    return rows, recommendations[:limit], approval


def graphify_compact(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {"state": "UNKNOWN", "reason": None}

    recommendation = payload.get("recommendation")
    action = recommendation.get("action") if isinstance(recommendation, dict) else None
    reason = None
    if isinstance(recommendation, dict):
        reasons = recommendation.get("reasons")
        if isinstance(reasons, list) and reasons:
            reason = "; ".join(str(x) for x in reasons[:3])

    mapping = {
        "USE_EXISTING_GRAPH": "READY",
        "UPDATE_RECOMMENDED": "STALE",
        "BUILD_RECOMMENDED": "RECOMMENDED",
        "INSTALL_RECOMMENDED": "RECOMMENDED",
        "NOT_NEEDED_BY_CURRENT_EVIDENCE": "NOT_NEEDED",
    }
    if action in mapping:
        return {"state": mapping[action], "reason": reason}

    install = payload.get("project_install")
    graph = payload.get("graph")
    if isinstance(graph, dict) and graph.get("exists") is True:
        return {"state": "READY", "reason": "graphify-out/graph.json обнаружен"}
    if isinstance(install, dict) and install.get("state") == "INSTALLED":
        return {"state": "INSTALLED", "reason": "project-scoped Graphify skill обнаружен"}
    return {"state": "UNKNOWN", "reason": reason}


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


def build_bridge(
    audit: dict[str, Any],
    *,
    runtime: dict[str, Any] | None = None,
    graphify: dict[str, Any] | None = None,
    ledger: dict[str, Any] | None = None,
    finding_limit: int = 5,
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

    runtime_measurement = runtime_from_context_payload(runtime)
    if runtime_measurement["status"] == "AVAILABLE":
        health_basis = "MEASURED" if health != "UNKNOWN" else "PARTIAL"
    elif static_context(audit)["fileCount"] > 0:
        health_basis = "STATIC_ONLY"
    else:
        health_basis = "UNKNOWN"

    findings, recommendations, findings_need_approval = compact_findings(audit, finding_limit)
    ledger_state, ledger_needs_approval = ledger_compact(ledger)
    graph_state = graphify_compact(graphify)

    return {
        "schemaVersion": "0.1",
        "status": "READY",
        "health": health,
        "healthBasis": health_basis,
        "runtimeMeasurement": runtime_measurement,
        "staticContext": static_context(audit),
        "staticRisk": static_risk,
        "topFindings": findings,
        "recommendations": recommendations,
        "graphify": graph_state,
        "ledger": ledger_state,
        "approvalRequired": findings_need_approval or ledger_needs_approval,
        "source": {
            "auditSchemaVersion": audit.get("schema_version"),
            "runtimeSource": "provided-runtime-json" if runtime else None,
            "graphifySource": "provided-graphify-json" if graphify else None,
            "ledgerSource": "provided-ledger-summary" if ledger else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build compact Matreshka Context Optimizer bridge")
    parser.add_argument("--audit", required=True)
    parser.add_argument("--runtime")
    parser.add_argument("--graphify")
    parser.add_argument("--ledger")
    parser.add_argument("--finding-limit", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()

    try:
        audit = load_object(Path(args.audit).expanduser().resolve())
        assert audit is not None
        result = build_bridge(
            audit,
            runtime=load_object(Path(args.runtime).expanduser().resolve()) if args.runtime else None,
            graphify=load_object(Path(args.graphify).expanduser().resolve()) if args.graphify else None,
            ledger=load_object(Path(args.ledger).expanduser().resolve()) if args.ledger else None,
            finding_limit=max(1, min(args.finding_limit, 8)),
        )
    except (BridgeError, AssertionError) as exc:
        print(json.dumps({"status": "UNAVAILABLE", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).expanduser().resolve().write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
