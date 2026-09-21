# План реализации

## Gate 0 — Provenance и базовая структура
**PASS с административным follow-up**
- [x] Источники и лицензии.
- [x] Русскоязычный README.
- [ ] Переименовать репозиторий `Matreshk-context-optimizer` → `Matreshka-context-optimizer` через GitHub repository settings.
- [x] GitHub short description установлен.

## Gate 1 — Спецификация v0.1
**PASS**
- [x] Goal/non-goals.
- [x] Measurement model.
- [x] Safety/approval.
- [x] Capability model.
- [x] Matreshka integration boundary.

## Gate 2 — Finding contract
**PASS**
- [x] measurement/finding/audit/plan schemas.
- [x] evidence + provenance + risk + statuses.

## Gate 3 — Read-only MVP
**IMPLEMENTED / REAL PROJECT PILOT PENDING**
- [x] environment scan.
- [x] exact static bytes.
- [x] duplicate instruction lines.
- [x] skill inventory/scope.
- [x] Graphify/external CLI detection.
- [x] smoke test.

## Gate 4 — CodeBurn Compatibility Adapter
**IMPLEMENTED / OPTIONAL ORACLE-FALLBACK**
- [x] optimize/context/doctor read-only adapter.
- [x] version provenance.
- [x] measured vs estimated basis.
- [x] context tree provenance documented.
- [x] offline smoke test.

## Gate 5 — Собственные аудиторы
**IMPLEMENTED / PILOT PENDING**
- [x] Instruction hygiene review signals.
- [x] Skill body/description review.
- [x] Skill routing-overlap signal.
- [x] MCP config inventory.
- [x] MCP duplicate registration.
- [x] missing local MCP command.
- [x] aggregate read-only audit.
- [ ] semantic conflict detection — после пилота и только с evidence model.

## Gate 6 — Context Ingress Audit
**IMPLEMENTED / PILOT PENDING**
- [x] CodeBurn context-tree analyzer.
- [x] exact-vs-estimated provenance.
- [x] tool-result dominance signal.
- [x] payload type/byte/line analysis.
- [x] repeated-line ingress detection.
- [x] large-payload review signal.

## Gate 7 — Graphify Adapter
**IMPLEMENTED / PILOT PENDING**
- [x] external-only architecture; Graphify code не копируется;
- [x] CLI/version detection;
- [x] project-scoped install detection для Codex/Claude/Antigravity/Agent-Skills;
- [x] graph presence + nodes/edges/basic stats;
- [x] project source profile;
- [x] evidence-based recommendation;
- [x] heuristic size recommendation с явным provenance;
- [x] mtime stale signal;
- [x] plan-only install/build/update;
- [x] read-only graph query;
- [x] отдельный approval на каждый mutation step;
- [x] smoke test.

## Gate 8 — Apply / Backup / Rollback
**IMPLEMENTED / PILOT PENDING**
- [x] one-change-per-run;
- [x] dry-run without mutation;
- [x] exact approval token;
- [x] expected-before SHA-256;
- [x] project-boundary protection + explicit global override;
- [x] backup before mutation;
- [x] REPLACE_EXACT_TEXT;
- [x] JSON_SET;
- [x] MOVE_PATH;
- [x] post-change validation;
- [x] auto-restore on apply failure;
- [x] rollback refuses to overwrite later changes.

## Gate 9 — Optimization Ledger
**IMPLEMENTED / PILOT PENDING**
- [x] append-only JSONL ledger;
- [x] APPLIED / ROLLED_BACK / VERIFICATION events;
- [x] KEEP / ROLLBACK / UNVERIFIED / NEEDS_MORE_DATA decisions;
- [x] metrics and quality kept separate;
- [x] per-change history and summary;
- [x] runtime state excluded from future context audits.

## Gate 10 — Matreshka Agent Bridge
**PASS / INTEGRATED WITH MATRESHKA AGENT**
- [x] compact bridge schema;
- [x] deterministic bridge builder;
- [x] exact runtime-vs-static separation;
- [x] top findings/recommendations cap;
- [x] Graphify compact state;
- [x] Optimization Ledger pending-verification projection;
- [x] approval state projection;
- [x] CodeBurn optimize savings rejected as current runtime usage;
- [x] bridge smoke test;
- [x] Matreshka Agent controller/ledger/dashboard wiring;

## Gate 11 — Реальные benchmark/evals
**IMPLEMENTED HARNESS / REAL STATIC PILOT AUTOMATED / RUNTIME SAVINGS EVIDENCE PENDING**
- [x] benchmark run schema;
- [x] benchmark result schema;
- [x] comparability checks;
- [x] PASS / FAIL / UNVERIFIED evaluator;
- [x] quality-regression gates;
- [x] heuristic/static measurements cannot produce runtime PASS;
- [x] package-layout skill discovery;
- [x] real read-only Matreshka Agent pilot in CI;
- [x] target-cleanliness verification;
- [ ] comparable provider-measured before/after agent sessions;

Acceptance remains: measured context/token cost ↓ при task success >= baseline, retries/errors/wrong-file reads <= baseline и information loss = NO.

## Gate 12 — Native Telemetry Engine
**CORE IMPLEMENTED / REAL LOCAL CORPUS PARITY PENDING**
- [x] собственный telemetry package без runtime dependency на CodeBurn;
- [x] Codex strict local session discovery;
- [x] Codex provider-measured token parser;
- [x] Codex cumulative/dedup guards;
- [x] exact byte-level context composition;
- [x] file-read / skill / MCP / tool event extraction;
- [x] native waste detectors;
- [x] user-level cache, выключенный по умолчанию;
- [x] Claude Code native JSONL usage parser;
- [x] safe Antigravity static discovery;
- [x] Antigravity existing-statusline parser без process probe/RPC;
- [x] native telemetry schema;
- [x] Matreshka bridge принимает native current-context measurement;
- [x] CodeBurn comparison tool как optional test oracle;
- [x] synthetic multi-provider smoke suite;
- [ ] parity-check на реальном пользовательском Codex corpus против CodeBurn;
- [ ] direct safe Antigravity DB/PB decoder без live RPC;
- [ ] Claude cross-file resumed-session dedup hardening;
- [ ] comparable native provider-measured BEFORE/AFTER production sessions.

После Gate 12 CodeBurn имеет статус REFERENCE / OPTIONAL_ORACLE / COMPATIBILITY, а не REQUIRED_DEPENDENCY.
