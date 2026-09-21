#!/usr/bin/env python3
"""Read-only аудит MCP-конфигураций без запуска серверов."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

from audit_common import finding, json_evidence, measurement


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_toml(path: Path) -> dict[str, Any] | None:
    if tomllib is None:
        return None
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return data if isinstance(data, dict) else None


def extract_json_servers(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("mcpServers", "mcp_servers"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return {}


def extract_toml_servers(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("mcp_servers", "mcpServers"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return {}


def candidate_configs(root: Path, include_global: bool) -> list[tuple[Path, str, str]]:
    result = [
        (root / ".mcp.json", "PROJECT", "json"),
        (root / ".claude" / "settings.json", "PROJECT", "json"),
        (root / ".claude" / "settings.local.json", "PROJECT", "json"),
        (root / ".codex" / "config.toml", "PROJECT", "toml"),
    ]
    if include_global:
        home = Path.home()
        result.extend(
            [
                (home / ".claude.json", "GLOBAL", "json"),
                (home / ".claude" / "settings.json", "GLOBAL", "json"),
                (home / ".codex" / "config.toml", "GLOBAL", "toml"),
            ]
        )
    return result


def executable_state(server: Any) -> dict[str, Any] | None:
    if not isinstance(server, dict):
        return None
    command = server.get("command")
    if not isinstance(command, str) or not command.strip():
        return None

    command = command.strip()
    if any(char in command for char in ("$", "~", "*", "|", "&", ";", ">", "<")):
        return {
            "command": command,
            "check": "SKIPPED_COMPLEX_COMMAND",
            "available": None,
        }

    path = Path(command)
    if path.is_absolute() or "/" in command or "\\" in command:
        return {
            "command": command,
            "check": "PATH_EXISTS",
            "available": path.expanduser().exists(),
        }

    resolved = shutil.which(command)
    return {
        "command": command,
        "check": "PATH_LOOKUP",
        "available": bool(resolved),
        "resolved": resolved,
    }


def audit_mcp(
    root: Path,
    *,
    include_global: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    measurements: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []

    for path, scope, format_name in candidate_configs(root, include_global):
        if not path.exists() or not path.is_file():
            continue

        data = load_json(path) if format_name == "json" else load_toml(path)
        if data is None:
            continue

        servers = extract_json_servers(data) if format_name == "json" else extract_toml_servers(data)
        if not servers:
            continue

        for name, server in servers.items():
            record = {
                "name": str(name),
                "scope": scope,
                "config": str(path.resolve()),
                "format": format_name,
                "executable": executable_state(server),
            }
            inventory.append(record)

        measurements.append(
            measurement(
                len(servers),
                "count",
                "TOOL_MEASURED",
                "mcp-audit",
                "HIGH",
                method=f"configured MCP entries in {format_name}",
                notes=str(path.resolve()),
            )
        )

    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in inventory:
        by_name.setdefault(item["name"], []).append(item)

    for name, items in sorted(by_name.items()):
        unique_configs = {item["config"] for item in items}
        if len(unique_configs) <= 1:
            continue
        findings.append(
            finding(
                "MCP_DUPLICATE_REGISTRATION",
                "UNKNOWN",
                "MCP с одинаковым именем зарегистрирован в нескольких конфигурациях",
                (
                    f"MCP {name} найден в {len(unique_configs)} конфигурациях. "
                    "Это может быть намеренное переопределение, поэтому автоматическое удаление запрещено."
                ),
                [
                    {
                        "source": "mcp-audit",
                        "detail": json_evidence(items),
                        "locator": None,
                        "observed_at": None,
                    }
                ],
                measurement(
                    len(unique_configs),
                    "count",
                    "TOOL_MEASURED",
                    "mcp-audit",
                    "HIGH",
                    method="same MCP name across config sources",
                ),
                direction="IMPROVE_ROUTING",
                effect="Проверка precedence может выявить ненужную или конфликтующую регистрацию.",
                confidence="MEDIUM",
                quality_risk="HIGH",
                action="REVIEW_MCP_PRECEDENCE",
                proposal="Сначала определить effective config и usage; ничего не удалять автоматически.",
            )
        )

    for item in inventory:
        state = item.get("executable")
        if not isinstance(state, dict) or state.get("available") is not False:
            continue
        findings.append(
            finding(
                "MCP_COMMAND_NOT_FOUND",
                item["scope"],
                "Команда локального MCP не найдена",
                f"MCP {item['name']} ссылается на команду {state.get('command')}, которая не обнаружена read-only проверкой.",
                [
                    {
                        "source": "mcp-audit",
                        "detail": json_evidence(state),
                        "locator": item["config"],
                        "observed_at": None,
                    }
                ],
                measurement(
                    1,
                    "count",
                    "TOOL_MEASURED",
                    "mcp-audit",
                    "HIGH",
                    method=str(state.get("check")),
                ),
                direction="REDUCE_CONTEXT",
                effect="Если регистрация действительно сломана и не используется, её ревизия может убрать бесполезную конфигурацию.",
                confidence="HIGH",
                quality_risk="MEDIUM",
                action="REVIEW_BROKEN_MCP",
                proposal="Проверить, должен ли MCP быть установлен. Не удалять запись автоматически.",
                target=item["config"],
            )
        )

    return measurements, findings, inventory


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only аудит MCP-конфигураций")
    parser.add_argument("--project", default=".", help="Корень проекта")
    parser.add_argument("--include-global", action="store_true")
    args = parser.parse_args()

    root = Path(args.project).expanduser().resolve()
    measurements, findings, inventory = audit_mcp(root, include_global=args.include_global)
    print(
        json.dumps(
            {
                "mode": "READ_ONLY",
                "inventory": inventory,
                "measurements": measurements,
                "findings": findings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
