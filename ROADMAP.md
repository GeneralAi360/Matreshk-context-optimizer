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

- [x] Цель и non-goals.
- [x] Measurement model.
- [x] Safety/approval policy.
- [x] Capability model.
- [x] Граница интеграции с Matreshka Agent.

## Gate 2 — Единый контракт Finding

Статус: **PASS**

- [x] measurement schema;
- [x] finding schema;
- [x] audit report schema;
- [x] optimization plan schema;
- [x] evidence + provenance + risk + status.

## Gate 3 — Read-only MVP

Статус: **IMPLEMENTED / NEEDS REAL PROJECT PILOT**

- [x] compact `SKILL.md`;
- [x] environment scanner;
- [x] exact static BYTE_COUNT;
- [x] cross-file duplicate detection;
- [x] skill inventory/scope collision;
- [x] Graphify presence detection;
- [x] external CLI detection;
- [x] smoke test;
- [x] no fake token conversion.

## Gate 4 — CodeBurn Adapter

Статус: **IMPLEMENTED / NEEDS REAL CODEBURN PILOT**

- [x] detect CodeBurn in PATH;
- [x] capture version;
- [x] read-only `optimize --format json`;
- [x] read-only `context --json` for Claude/Codex;
- [x] read-only `doctor --json`;
- [x] normalize `measured` vs `estimated` basis;
- [x] preserve raw finding id/class/fix;
- [x] never execute `--apply`;
- [x] offline fixture smoke test.

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

## Gate 10 — Matreshka Agent Bridge

Статус: **PLANNED**

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
