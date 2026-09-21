---
name: context-optimizer
description: Использовать, когда нужно измерить и диагностировать расход контекста или токенов, проверить project instructions, skills, MCP/tools, большие tool outputs или навигацию по репозиторию и подготовить безопасные рекомендации без потери качества.
---

# Оптимизатор контекста

## Назначение

Навык проводит аудит контекста AI-агента и помогает уменьшать ненужный overhead без подмены измерений оценками.

Текущий режим `v0.1` — **READ_ONLY**.

## Основной запуск

1. Определи project root и фактический harness.
2. Проверь capabilities, а не предполагай их по названию платформы.
3. Запусти сводный read-only аудит:
   ~~~bash
   python skills/context-optimizer/scripts/audit_extended.py --project .
   ~~~
4. Если нужны глобальные skills/MCP, добавь `--include-global` явно.
5. Если CodeBurn уже установлен, запусти read-only adapter:
   ~~~bash
   python skills/context-optimizer/scripts/codeburn_adapter.py --command optimize
   ~~~
6. Для конкретной Codex/Claude Code сессии получи context tree через adapter, затем проанализируй его:
   ~~~bash
   python skills/context-optimizer/scripts/codeburn_adapter.py --command context --provider codex --session <id> --output context.json
   python skills/context-optimizer/scripts/analyze_context_tree.py --input context.json
   ~~~
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
- CodeBurn → [codeburn-adapter.md](references/codeburn-adapter.md).
- Context ingress → [context-ingress.md](references/context-ingress.md).
- Graphify → [graphify-adapter.md](references/graphify-adapter.md).
- Mutation/rollback в будущих версиях → [approval-model.md](references/approval-model.md).
- Matreshka Agent → [matreshka-integration.md](references/matreshka-integration.md).

Не загружай все references заранее.

## Жёсткие правила

- `BYTE_COUNT` не является token count.
- `chars / N` — только `HEURISTIC_ESTIMATE`.
- Если точного runtime measurement нет, используй `UNKNOWN`.
- В CodeBurn context tree `reported.context` и block-level token counts имеют разное provenance.
- CodeBurn health grade не является нашим `CONTEXT_HEALTH`.
- Не запускай `codeburn optimize --apply` из v0.1.
- Не удаляй и не отключай MCP/skills.
- Не переписывай AGENTS.md, CLAUDE.md или GEMINI.md.
- Не устанавливай CodeBurn, Caveman или Graphify без отдельного approval.
- Не строй Graphify graph только потому, что Graphify существует.
- Не копируй Caveman Engine.
- Порог размера/overlap — review signal, не доказательство мусора.
- Отчёт и рекомендации пользователю — на русском языке.