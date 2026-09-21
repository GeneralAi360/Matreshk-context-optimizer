---
name: context-optimizer
description: Использовать, когда нужно измерить и диагностировать расход контекста или токенов, проверить project instructions, skills, MCP/tools, большие tool outputs или навигацию по репозиторию и подготовить безопасные рекомендации без потери качества.
---

# Оптимизатор контекста

## Назначение

Навык проводит аудит контекста AI-агента и помогает уменьшать ненужный overhead без подмены измерений оценками.

Текущий режим `v0.1` — **READ_ONLY**.

## Базовый процесс

1. Определи project root и фактический harness.
2. Проверь доступные capabilities, а не предполагай их по названию платформы.
3. Запусти project-local environment scan:
   ~~~bash
   python skills/context-optimizer/scripts/scan_environment.py --project .
   ~~~
4. Запусти статический аудит:
   ~~~bash
   python skills/context-optimizer/scripts/audit_static_context.py --project .
   ~~~
5. Если CodeBurn уже доступен, используй read-only adapter:
   ~~~bash
   python skills/context-optimizer/scripts/codeburn_adapter.py --command optimize
   ~~~
   Для конкретной Codex/Claude Code сессии допускается:
   ~~~bash
   python skills/context-optimizer/scripts/codeburn_adapter.py --command context --provider codex --session <id>
   ~~~
6. Нормализуй findings по единому контракту и не смешивай типы измерений.
7. Выведи отчёт на русском языке.
8. Ничего не изменяй в проекте или глобальной конфигурации в v0.1.

## Когда читать references

- Для любой числовой метрики прочитай [measurement-model.md](references/measurement-model.md).
- Для findings прочитай [finding-contract.md](references/finding-contract.md).
- Для capability detection прочитай [provider-capabilities.md](references/provider-capabilities.md).
- При использовании CodeBurn прочитай [codeburn-adapter.md](references/codeburn-adapter.md).
- Перед любым будущим mutation-flow прочитай [approval-model.md](references/approval-model.md).
- При работе из Matreshka Agent прочитай [matreshka-integration.md](references/matreshka-integration.md).

Не загружай все references без необходимости.

## Жёсткие правила

- `BYTE_COUNT` не является token count.
- `chars / N` — только `HEURISTIC_ESTIMATE`.
- Если точного runtime measurement нет, используй `UNKNOWN`.
- CodeBurn `basis=measured` можно сохранять как provider-measured provenance только с явной ссылкой на CodeBurn как источник агрегации.
- CodeBurn health grade не является нашим `CONTEXT_HEALTH`.
- Не запускай `codeburn optimize --apply` из v0.1.
- Не удаляй и не отключай MCP/skills.
- Не переписывай AGENTS.md, CLAUDE.md или GEMINI.md.
- Не устанавливай CodeBurn, Caveman или Graphify без отдельного approval.
- Не строй Graphify graph только потому, что Graphify существует.
- Не копируй Caveman Engine в этот проект.
- Отчёт и рекомендации пользователю — на русском языке.

## Формат короткого отчёта

~~~text
СОСТОЯНИЕ КОНТЕКСТА
Runtime measurement: <AVAILABLE/PARTIAL/UNKNOWN>
Static instructions: <точные bytes>
Findings: <N>

Основные причины:
1. ...
2. ...

Что измерено точно:
- ...

Что является оценкой:
- ...

Что пока неизвестно:
- ...

Рекомендации:
- ...

Изменения не применялись: READ_ONLY
~~~
