# План реализации

## Gate 0 — Provenance и базовая структура

Статус: **IN PROGRESS**

- [x] Зафиксировать рабочий репозиторий.
- [x] Создать реестр источников.
- [x] Зафиксировать лицензионные ограничения внешних инструментов.
- [x] Создать русскоязычный README.
- [ ] Переименовать репозиторий из `Matreshk-context-optimizer` в `Matreshka-context-optimizer` через GitHub repository settings.

## Gate 1 — Спецификация Context Optimizer v0.1

Статус: **IN PROGRESS**

- [x] Определить цель и non-goals.
- [x] Определить модель измерений.
- [x] Определить safety/approval policy.
- [x] Определить первичную capability model.
- [x] Определить интеграционную границу с Matreshka Agent.

## Gate 2 — Единый контракт Finding

Статус: **PLANNED**

- finding schema;
- evidence schema;
- measurement provenance;
- expected effect;
- quality risk;
- proposed change;
- approval state;
- verification state.

## Gate 3 — Read-only MVP

Статус: **PLANNED**

Первая рабочая версия ничего не меняет. Она только:

```text
SCAN → MEASURE → AUDIT → REPORT
```

## Gate 4 — CodeBurn Adapter

Статус: **PLANNED**

- detect;
- version check;
- provider capabilities;
- overview/audit/context/optimize JSON;
- normalization into our findings.

## Gate 5 — Собственные аудиторы

Статус: **PLANNED**

- Instructions Audit;
- Skills Audit;
- MCP / Tools Audit;
- scope mismatch;
- duplicates;
- conflicts;
- stale instructions;
- routing collisions.

## Gate 6 — Context Ingress Audit

Статус: **PLANNED**

- LOG_OVERFLOW;
- JSON_OVERFLOW;
- DIFF_OVERFLOW;
- TEST_OUTPUT_OVERFLOW;
- DIRECTORY_LISTING_OVERFLOW;
- REPEATED_FILE_READ.

## Gate 7 — Graphify Adapter

Статус: **PLANNED**

Graphify не является обязательной зависимостью. Подключается только при доказанной пользе для конкретного проекта.

## Gate 8 — Apply / Backup / Rollback

Статус: **PLANNED**

```text
FINDING → EVIDENCE → EXPECTED EFFECT → RISK
→ DRY RUN → APPROVAL → BACKUP → APPLY
→ RE-MEASURE → VERIFY → KEEP / ROLLBACK
```

## Gate 9 — Optimization Ledger

Статус: **PLANNED**

История изменений, измерений и решений KEEP / ROLLBACK / UNVERIFIED.

## Gate 10 — Matreshka Agent Bridge

Статус: **PLANNED**

В Matreshka Agent передаётся компактный capability/result contract, а не весь optimizer.

## Gate 11 — Реальные benchmark/evals

Статус: **PLANNED**

Acceptance:

```text
TOKEN / CONTEXT COST ↓
AND TASK SUCCESS >= BEFORE
AND RETRIES <= BEFORE
AND ERRORS <= BEFORE
AND INFORMATION LOSS = NO
```
