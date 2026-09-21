---
name: context-optimizer
description: Использовать, когда нужно измерить и диагностировать расход контекста или токенов, проверить project instructions, skills, MCP/tools, большие tool outputs или навигацию по репозиторию и подготовить безопасные рекомендации без потери качества.
---

# Оптимизатор контекста

## Назначение

Навык проводит аудит контекста AI-агента и помогает уменьшать ненужный overhead без подмены измерений оценками.

Режим `v0.2` по умолчанию — **READ_ONLY**. Reversible mutation разрешён только через отдельный approved `CHG-xxx` после dry-run.

## Основной запуск

1. Определи project root и фактический harness.
2. Проверь capabilities, а не предполагай их по названию платформы.
3. Запусти сводный read-only аудит:
   ~~~bash
   python skills/context-optimizer/scripts/audit_extended.py --project .
   ~~~
4. Если нужны глобальные skills/MCP, добавь `--include-global` явно.
5. Для runtime/session telemetry сначала используй собственный engine:
   ~~~bash
   python skills/context-optimizer/scripts/native_telemetry.py --provider codex --output runtime.json
   ~~~
   Для Claude замени provider на `claude`. Для Antigravity по умолчанию выполняется safe static discovery; существующий statusline можно передать через `--statusline <file>`.
6. CodeBurn не требуется. Если он уже установлен и нужен parity-check/compatibility evidence, используй [compatibility adapter](references/codeburn-adapter.md) отдельно; не устанавливай его автоматически.
7. Большой log/JSON/diff/tool output можно отдельно проверить:
   ~~~bash
   python skills/context-optimizer/scripts/analyze_payload.py --input <file>
   ~~~
8. Если repository navigation выглядит дорогой, проверь Graphify status/plan:
   ~~~bash
   python skills/context-optimizer/scripts/graphify_adapter.py --project . --platform codex status
   python skills/context-optimizer/scripts/graphify_adapter.py --project . --platform codex plan
   ~~~
   Если graph уже существует, для codebase-вопросов разрешён read-only query:
   ~~~bash
   python skills/context-optimizer/scripts/graphify_adapter.py --project . query --question "<вопрос>"
   ~~~
9. Сформируй findings по единому контракту и выведи отчёт на русском.
10. Ничего не изменяй в проекте или глобальной конфигурации в v0.1.

## References загружаются только по необходимости

- Числовые метрики → [measurement-model.md](references/measurement-model.md).
- Finding contract → [finding-contract.md](references/finding-contract.md).
- Слои аудита → [audit-model.md](references/audit-model.md).
- Capability detection → [provider-capabilities.md](references/provider-capabilities.md).
- Native telemetry → [native-telemetry.md](references/native-telemetry.md).
- CodeBurn compatibility/oracle → [codeburn-adapter.md](references/codeburn-adapter.md).
- Context ingress → [context-ingress.md](references/context-ingress.md).
- Graphify → [graphify-adapter.md](references/graphify-adapter.md).
- Apply/rollback → [apply-rollback.md](references/apply-rollback.md).
- Optimization Ledger → [optimization-ledger.md](references/optimization-ledger.md).
- Mutation/rollback в будущих версиях → [approval-model.md](references/approval-model.md).
- Matreshka Agent / compact bridge → [matreshka-integration.md](references/matreshka-integration.md).
- Before/after acceptance → [benchmarking.md](references/benchmarking.md).

Не загружай все references заранее.

## Жёсткие правила

- `BYTE_COUNT` не является token count.
- `chars / N` — только `HEURISTIC_ESTIMATE`.
- Если точного runtime measurement нет, используй `UNKNOWN`.
- Native provider counters и byte-level context composition имеют разное provenance; bytes не превращаются в tokens.
- В optional CodeBurn oracle `reported.context` и block-level token counts также имеют разное provenance.
- CodeBurn health grade не является нашим `CONTEXT_HEALTH`.
- Не запускай `codeburn optimize --apply` из v0.1.
- Не удаляй и не отключай MCP/skills.
- Не переписывай AGENTS.md, CLAUDE.md или GEMINI.md без отдельного approved change.
- Перед mutation всегда делай dry-run и сверяй `expected_before_sha256`.
- Один apply = один `CHG-xxx`; batch mutation запрещён.
- После apply статус остаётся непроверенным, пока нет re-measure + quality verification.
- Не устанавливай CodeBurn автоматически: штатная telemetry должна работать без него.
- Не устанавливай Caveman или Graphify без отдельного approval.
- Не строй Graphify graph только потому, что Graphify существует.
- Не копируй Caveman Engine.
- Порог размера/overlap — review signal, не доказательство мусора.
- Отчёт и рекомендации пользователю — на русском языке.
## Reversible mutation после approval

Когда пользователь явно одобрил конкретный change:

~~~bash
python skills/context-optimizer/scripts/change_executor.py --project . dry-run --change change.json
python skills/context-optimizer/scripts/change_executor.py --project . apply --change change.json --approve CHG-001
~~~

После измерений запиши verification в Optimization Ledger. При необходимости выполняй rollback только через hash-safe rollback token.
## Compact bridge для Matreshka Agent

После аудита сформируй только компактную проекцию, а не передавай весь audit/ledger в controller:

~~~bash
python skills/context-optimizer/scripts/matreshka_bridge.py --audit audit.json --runtime runtime.json --graphify graphify.json --ledger ledger.json --output context-optimizer-bridge.json
~~~

Runtime tokens и static bytes всегда остаются раздельными. Bridge не является authority на mutation.
## Before/after verification

После оптимизации не объявляй экономию успешной по одному token delta. Для сопоставимых run records используй:

~~~bash
python evals/evaluate_before_after.py --before before.json --after after.json
~~~

`HEURISTIC_ESTIMATE`, static bytes или несопоставимые provider/model/task conditions дают `UNVERIFIED`, а не PASS.