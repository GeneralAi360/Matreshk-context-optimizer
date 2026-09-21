# План реализации

## Gate 0 — Provenance и базовая структура
**PASS с административным follow-up**
- [x] Источники и лицензии.
- [x] Русскоязычный README.
- [ ] Переименовать репозиторий `Matreshk-context-optimizer` → `Matreshka-context-optimizer` через GitHub repository settings.
- [ ] Установить GitHub short description через repository settings.

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

## Gate 4 — CodeBurn Adapter
**IMPLEMENTED / REAL CODEBURN PILOT PENDING**
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
**PLANNED**

## Gate 11 — Реальные benchmark/evals
**PLANNED**
Acceptance: context/token cost ↓ при task success >= baseline, retries/errors <= baseline и без information loss.