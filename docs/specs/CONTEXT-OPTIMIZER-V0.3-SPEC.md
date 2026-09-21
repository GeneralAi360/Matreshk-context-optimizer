# Спецификация: Оптимизатор контекста v0.3

Статус: **ACTIVE**

## 1. Назначение

`$context-optimizer` — русскоязычный reusable skill для диагностики и безопасной оптимизации контекста AI-агентов.

Он отвечает на четыре вопроса:

1. Что реально занимает контекст и расходует токены?
2. Что из этого необходимо, а что создаёт ненужный overhead?
3. Какое изменение может уменьшить расход без ухудшения качества?
4. Дало ли изменение реальный положительный эффект?

## 2. Цель

Снизить ненужный context/token cost при сохранении или повышении качества выполнения задач.

## 3. Не входит в задачу

- автоматически удалять MCP;
- автоматически удалять или переписывать skills;
- переписывать AGENTS.md/CLAUDE.md/GEMINI.md без approved change;
- подменять provider telemetry эвристикой;
- устанавливать сторонние оптимизаторы;
- отправлять telemetry наружу;
- смешивать static byte budgets с runtime token usage.

## 4. Поддерживаемые среды

- Codex;
- Claude Code;
- Antigravity / agy.

Поддержка определяется через capability detection и доступные локальные данные.

## 5. Workflow

~~~text
MEASURE
→ DIAGNOSE
→ CLASSIFY
→ RECOMMEND
→ APPROVAL
→ APPLY
→ RE-MEASURE
→ QUALITY VERIFY
→ KEEP / ROLLBACK
~~~

## 6. Сценарии входа

- `start` — новый проект;
- `adopt` — первое подключение к готовому проекту;
- `resume` — восстановление после паузы;
- `check` — evidence-driven проверка;
- `status` — текущее состояние;
- `optimize` — только план изменений.

## 7. Зоны аудита

### Environment

- harness/OS/project root;
- instruction files;
- skills;
- MCP/tools;
- local telemetry availability.

### Static instructions

- duplication;
- stale state;
- history instead of current state;
- scope mismatch;
- verbose reference material;
- information that should be lazy-loaded.

### Skills

- GLOBAL / PROJECT;
- USED / UNUSED / UNKNOWN;
- DUPLICATE / OVERLAPPING;
- BODY_BLOAT / WRONG_SCOPE / ROUTING_COLLISION.

### MCP / tools

- configured vs used;
- duplicate capability;
- scope mismatch;
- broken local command;
- oversized results.

### Context ingress

- large logs/JSON/diffs;
- repeated file reads;
- repeated tool output;
- recoverable summarization opportunities.

### Repository navigation

Нативная карта проекта определяет области и navigation pressure. Сначала выбирается область, затем читается минимальный набор файлов.

## 8. Finding contract

Каждый finding содержит problem, evidence, measurement provenance, expected effect, confidence, quality risk, proposal, approval_required и status.

Finding без evidence не может автоматически перейти в изменение.

## 9. Quality model

После APPLY проверять минимум task success, retries, wrong-file reads, repeated reads, tool-call count, elapsed time (если доступно), context/token metrics и information loss.

## 10. Matreshka Agent integration

Context Optimizer — отдельный peer skill. Matreshka вызывает единый command interface и получает компактный bridge, не raw telemetry.

Bridge содержит `health`, `runtimeMeasurement`, `staticContext`, `projectMap`, `topFindings`, `recommendations`, `ledger`, `trigger`, `approvalRequired`.

Вызов optimizer не расширяет permission envelope Matreshka.

## 11. Язык

Пользовательские отчёты, объяснения, рекомендации, approval prompts и dashboard labels — на русском. Machine enums/keys могут оставаться английскими.
