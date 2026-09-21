# Спецификация: Оптимизатор контекста v0.1

Статус: **DRAFT / GATE-1**

## 1. Назначение

`$context-optimizer` — русскоязычный reusable skill для диагностики и безопасной оптимизации контекста AI-агентов.

Он должен отвечать на четыре вопроса:

1. Что реально занимает контекст и расходует токены?
2. Что из этого является необходимым, а что — потерями?
3. Какое изменение может уменьшить расход без ухудшения качества?
4. Дало ли изменение реальный положительный эффект?

## 2. Цель

Снизить ненужный context/token cost при сохранении или повышении качества выполнения задач.

Успех не определяется одной метрикой токенов.

## 3. Non-goals v0.1

Первая версия НЕ должна:

- автоматически удалять MCP;
- автоматически удалять или переписывать skills;
- автоматически переписывать AGENTS.md/CLAUDE.md/GEMINI.md;
- устанавливать proxy/hooks без approval;
- подменять provider telemetry эвристической оценкой;
- строить Graphify graph для каждого проекта по умолчанию;
- копировать Caveman Engine;
- становиться форком CodeBurn;
- смешивать static byte budgets Matreshka Agent с runtime token usage.

## 4. Поддерживаемые среды

Целевая capability model:

- Codex;
- Claude Code;
- Antigravity / agy.

Поддержка определяется не по имени платформы, а через runtime capability detection.

## 5. Главный workflow

```text
MEASURE
→ DIAGNOSE
→ CLASSIFY
→ RECOMMEND
→ APPROVAL
→ APPLY
→ RE-MEASURE
→ QUALITY VERIFY
→ KEEP / ROLLBACK
```

В v0.1 рабочий scope ограничивается этапами:

```text
MEASURE → DIAGNOSE → CLASSIFY → REPORT
```

## 6. Зоны аудита

### 6.1 Environment

- agent/harness;
- version;
- OS;
- project root;
- instruction files;
- installed skills;
- MCP/connectors/tools;
- hooks;
- local provider telemetry;
- external optimizer dependencies.

### 6.2 Static instructions

Проверять:

- duplication;
- stale state;
- history instead of current state;
- scope mismatch;
- contradictory rules;
- verbose reference material;
- information that should be lazy-loaded;
- project-specific instructions stored globally;
- module-specific instructions stored at root.

### 6.3 Skills

Классы:

- GLOBAL / PROJECT;
- USED / UNUSED / UNKNOWN;
- DUPLICATE;
- OVERLAPPING;
- TOO_BROAD_DESCRIPTION;
- BODY_BLOAT;
- WRONG_SCOPE;
- ROUTING_COLLISION;
- CANDIDATE_FOR_REFERENCE_SPLIT.

### 6.4 MCP / tools

Проверять:

- configured vs used;
- schema/tool-catalog overhead;
- tool search/lazy loading availability;
- global vs project scope;
- duplicate capability;
- CLI/native alternative;
- broken server;
- low coverage.

### 6.5 Context ingress

Искать:

- oversized logs;
- oversized JSON;
- oversized diffs;
- test output noise;
- directory listing noise;
- repeated file reads;
- repeated tool output;
- data that can be summarized while preserving recoverability.

### 6.6 Repository navigation

Определять, когда проект достаточно большой/дорогой по навигации, чтобы рекомендовать graph-based navigation.

## 7. Finding contract

Каждый finding обязан содержать:

```yaml
finding_id:
category:
platform:
scope:

problem:
evidence:

measurement:
  type:
  source:

expected_effect:
confidence:
quality_risk:

proposal:
approval_required:
status:
```

Finding без evidence не может автоматически переходить в изменение.

## 8. Приоритеты

Порядок ранжирования:

1. доказанный recurring overhead;
2. повторные чтения/повторная подача одинаковых данных;
3. неиспользуемые always-on capabilities;
4. oversized ingress;
5. scope mismatch;
6. navigation overhead;
7. эвристические возможности с низкой уверенностью.

## 9. Quality model

После будущего APPLY проверять минимум:

- task success;
- retries;
- wrong-file reads;
- repeated reads;
- tool-call count;
- elapsed time, если доступно;
- context/token metrics;
- information loss.

## 10. Matreshka Agent integration boundary

Context Optimizer является отдельным проектом и не встраивает весь код внутрь Matreshka Agent.

Matreshka получает компактный результат:

```text
CONTEXT_HEALTH
MEASUREMENT_PROVENANCE
TOP_FINDINGS
AVAILABLE_IMPROVEMENTS
APPROVAL_REQUIRED
EXTERNAL_DEPENDENCY_STATE
```

Optimizer не получает права на изменение проекта только потому, что его вызвал Matreshka Agent.

## 11. Язык

Пользовательские:

- отчёты;
- объяснения;
- рекомендации;
- approval prompts;
- dashboard labels;
- README/основная документация

— на русском языке.

Machine-readable enums и schema keys могут оставаться английскими.
