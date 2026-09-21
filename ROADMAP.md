# План реализации

## Gate 0 — Provenance и базовая структура

Статус: **PASS с административным follow-up**

- [x] Зафиксировать рабочий репозиторий.
- [x] Создать реестр источников.
- [x] Зафиксировать лицензионные ограничения внешних инструментов.
- [x] Создать русскоязычный README.
- [ ] Переименовать репозиторий из `Matreshk-context-optimizer` в `Matreshka-context-optimizer` через GitHub repository settings.
- [ ] Установить GitHub short description через repository settings.

## Gate 1 — Спецификация Context Optimizer v0.1

Статус: **PASS**

- [x] Определить цель и non-goals.
- [x] Определить модель измерений.
- [x] Определить safety/approval policy.
- [x] Определить первичную capability model.
- [x] Определить интеграционную границу с Matreshka Agent.

## Gate 2 — Единый контракт Finding

Статус: **PASS**

- [x] measurement schema;
- [x] finding schema;
- [x] audit report schema;
- [x] optimization plan schema;
- [x] evidence requirement;
- [x] measurement provenance;
- [x] expected effect;
- [x] quality risk;
- [x] approval state;
- [x] verification-ready statuses.

## Gate 3 — Read-only MVP

Статус: **IMPLEMENTED / NEEDS REAL PROJECT PILOT**

Первая рабочая версия ничего не меняет:

~~~text
SCAN → MEASURE → AUDIT → REPORT
~~~

Реализовано:

- [x] compact `SKILL.md`;
- [x] environment scanner;
- [x] static instruction byte measurements;
- [x] exact cross-file duplicate detection;
- [x] project/global skill inventory;
- [x] skill scope collision detection;
- [x] Graphify graph presence detection;
- [x] external CLI availability detection;
- [x] no-dependency smoke test;
- [x] запрет на fake token conversion.

Следующий acceptance gate: запуск на реальном проекте и сверка отчёта вручную.

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
- semantic overlaps;
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

~~~text
FINDING → EVIDENCE → EXPECTED EFFECT → RISK
→ DRY RUN → APPROVAL → BACKUP → APPLY
→ RE-MEASURE → VERIFY → KEEP / ROLLBACK
~~~

## Gate 9 — Optimization Ledger

Статус: **PLANNED**

История изменений, измерений и решений KEEP / ROLLBACK / UNVERIFIED.

## Gate 10 — Matreshka Agent Bridge

Статус: **PLANNED**

В Matreshka Agent передаётся компактный capability/result contract, а не весь optimizer.

## Gate 11 — Реальные benchmark/evals

Статус: **PLANNED**

Acceptance:

~~~text
TOKEN / CONTEXT COST ↓
AND TASK SUCCESS >= BEFORE
AND RETRIES <= BEFORE
AND ERRORS <= BEFORE
AND INFORMATION LOSS = NO
~~~
