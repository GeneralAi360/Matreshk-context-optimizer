# Adapter CodeBurn

Repository upstream: https://github.com/getagentseal/codeburn

## Роль

CodeBurn используется как внешний read-only источник runtime/session telemetry и findings. Context Optimizer не форкает CodeBurn и не запускает его mutation-команды.

## Разрешённые команды в Gate 4

- `codeburn optimize --format json` — findings и setup health;
- `codeburn context <session> --json --provider claude|codex` — дерево контекста конкретной сессии;
- `codeburn doctor --json` — состояние discovery/parsing;
- `codeburn --version` — provenance версии.

## Запрещено без отдельного approval

- `codeburn optimize --apply`;
- `codeburn act undo`;
- `codeburn guard install`;
- любые команды, которые меняют конфигурацию.

## Provenance

CodeBurn сам различает basis findings: `measured` и `estimated`. В нашем normalized finding:

- `measured` → `PROVIDER_MEASURED`, потому что upstream определяет эту basis как сумму provider-counted usage;
- `estimated` → `HEURISTIC_ESTIMATE`;
- raw CodeBurn id, class, basis и fix сохраняются в evidence/proposal;
- health grade CodeBurn не подменяет собственный `CONTEXT_HEALTH`.

## Важное ограничение providers

`codeburn context` upstream в текущей реализации поддерживает Claude Code и Codex. Нельзя предполагать такую же context-tree глубину для Antigravity только потому, что CodeBurn умеет читать часть Antigravity telemetry.

## Fail-closed

Если CodeBurn отсутствует, команда завершилась ошибкой, JSON не распарсился или структура неизвестна — adapter возвращает ошибку/UNKNOWN и не создаёт выдуманные findings.
