# План реализации

## Gate 0–2 — Основа и контракты
**PASS**
- [x] provenance model;
- [x] measurement/finding/audit/plan schemas;
- [x] safety/approval model;
- [x] русскоязычная основная документация.

## Gate 3 — Static Audit
**PASS**
- [x] environment scan;
- [x] exact static bytes;
- [x] instruction duplication/hygiene;
- [x] skill inventory/scope;
- [x] MCP config inventory.

## Gate 4 — Нативная Runtime Telemetry
**PASS / HARDENING CONTINUES**
- [x] Codex local session discovery/provider counters;
- [x] Claude Code JSONL usage parser;
- [x] Antigravity read-only SQLite decoder;
- [x] current-context provenance;
- [x] file/tool/skill/MCP events;
- [x] cache opt-in only;
- [ ] legacy Antigravity `.pb` decoder;
- [ ] Claude cross-file resumed-session dedup hardening.

## Gate 5–6 — Собственные аудиторы и Context Ingress
**PASS**
- [x] instruction hygiene;
- [x] skill body/description/overlap signals;
- [x] MCP duplicate/broken-local-command signals;
- [x] payload byte/line/type analysis;
- [x] repeated ingress detection;
- [x] tool-result dominance;
- [x] compaction/repeated-read signals.

## Gate 7 — Нативная карта проекта
**PASS**
- [x] project area/file inventory;
- [x] source/test/docs/config classification;
- [x] navigation pressure LOW/MEDIUM/HIGH;
- [x] area-first routing rule;
- [x] без внешних runtime dependencies.

## Gate 8 — Apply / Backup / Rollback
**PASS**
- [x] one-change-per-run;
- [x] dry-run;
- [x] exact approval token;
- [x] expected-before SHA-256;
- [x] project-boundary protection;
- [x] backup before mutation;
- [x] exact text / JSON / path operations;
- [x] post-change validation;
- [x] hash-safe rollback.

## Gate 9 — Optimization Ledger
**PASS**
- [x] append-only history;
- [x] APPLIED / ROLLED_BACK / VERIFICATION;
- [x] KEEP / ROLLBACK / UNVERIFIED / NEEDS_MORE_DATA;
- [x] metrics and quality separated.

## Gate 10 — Matreshka Agent Bridge
**PASS / INTEGRATED**
- [x] compact bridge;
- [x] runtime-vs-static separation;
- [x] top findings/recommendations cap;
- [x] native `projectMap`;
- [x] trigger projection;
- [x] ledger pending-verification projection;
- [x] approval state projection;
- [x] Matreshka controller auto-invocation rules через peer `auto` entrypoint;
- [x] русскоязычная dashboard section/tab `Контекст`.

## Gate 11 — Before/After Benchmark
**HARNESS PASS / PRODUCTION EVIDENCE PENDING**
- [x] comparable-run schemas;
- [x] PASS / FAIL / UNVERIFIED evaluator;
- [x] quality regression gates;
- [x] static/heuristic measurements cannot produce runtime PASS;
- [x] real repository read-only pilot;
- [ ] comparable provider-measured production before/after sessions.

## Gate 12 — Commands and Trigger Policy
**PASS / END-TO-END WIRED**
- [x] `start`;
- [x] `adopt`;
- [x] `resume`;
- [x] `check`;
- [x] `status`;
- [x] `optimize`;
- [x] `auto` — внутренний entrypoint Matreshka, который сам решает RUN/SKIP;
- [x] deterministic trigger policy;
- [x] anti-overhead rule: no full audit on every message;
- [x] Russian user messages;
- [x] source-qualified baseline snapshots (`snapshotId` / `capturedAt`);
- [x] `trigger.nextCheck` для dashboard;
- [x] end-to-end Matreshka controller → real peer skill `auto` smoke;

## Acceptance

Оптимизация считается успешной только когда измеренный context/token cost уменьшается при сохранённом task success, без роста retries/errors/wrong-file reads и без потери нужной информации.

## Административно

- [ ] При желании переименовать репозиторий `Matreshk-context-optimizer` → `Matreshka-context-optimizer` через GitHub settings.

## v0.4 — Автономная версия для новичков
**В РАЗРАБОТКЕ. Не считать весь этап завершённым по тестам прежней версии.**
- [x] Исправление effective/full byte breakdown в нативном детекторе.
- [x] Проектный отбор сессий до лимита; приведение runtime findings к общему отчёту.
- [x] Сквозные тесты provider-shaped JSONL → parser → detector → report.
- [x] Автономное сохранение аудит / Markdown / HTML / STATE без Matreshka Agent.
- [x] Content-bound предпросмотр и подтверждение блока памяти проекта.
- [x] Явный finish без ложного PASS по одному уменьшению bytes.
- [x] Разбор двух файлов пользовательского архива и письменное ревью.
- [ ] Установщик с manifest, безопасным обновлением и удалением только собственных файлов.
- [ ] Быстрые команды и проверка открытия внутри Codex / Claude Code / Cursor / Antigravity.
- [ ] Сквозной путь approved proposal → hardened change executor → реальная quality verification.
- [ ] Автоматическая фиксация завершения сессии там, где host даёт подтверждённый lifecycle hook.
- [ ] Реальные provider-measured пары before/after и проверки на пользовательском компьютере.
