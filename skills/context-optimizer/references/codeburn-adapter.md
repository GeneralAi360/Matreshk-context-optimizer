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

## Provenance optimize findings

CodeBurn различает basis findings: `measured` и `estimated`. В normalized finding:

- `measured` → `PROVIDER_MEASURED`, потому что upstream определяет эту basis как сумму provider-counted usage;
- `estimated` → `HEURISTIC_ESTIMATE`;
- raw CodeBurn id, class, basis и fix сохраняются в evidence/proposal;
- health grade CodeBurn не подменяет собственный `CONTEXT_HEALTH`.

## Provenance context tree

В upstream CodeBurn block-level counts дерева контекста оцениваются по содержимому, а поле `reported.context` берётся из provider usage последнего assistant message. Поэтому Context Optimizer обязан различать:

- `reported.context` → `PROVIDER_MEASURED`;
- `effective.tokens`, `full.tokens`, `toolResult.tokens` и другие block counts → `HEURISTIC_ESTIMATE`;
- ratios, рассчитанные из estimated blocks, могут быть `TOOL_MEASURED`, но должны явно сообщать, что исходные величины estimated.

## Ограничение providers

`codeburn context` upstream в текущей реализации поддерживает Claude Code и Codex. Нельзя предполагать такую же context-tree глубину для Antigravity только потому, что CodeBurn умеет читать часть Antigravity telemetry.

## Fail-closed

Если CodeBurn отсутствует, команда завершилась ошибкой, JSON не распарсился или структура неизвестна — adapter возвращает ошибку/UNKNOWN и не создаёт выдуманные findings.
