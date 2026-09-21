# Optimization Ledger

Optimization Ledger — append-only история реальных изменений и их проверки.

## События

- `APPLIED`;
- `ROLLED_BACK`;
- `VERIFICATION`.

Verification решения:

- `KEEP` — изменение подтверждено и остаётся;
- `ROLLBACK` — проверка рекомендует откат;
- `UNVERIFIED` — данных недостаточно;
- `NEEDS_MORE_DATA` — нужна дополнительная выборка.

## Важный принцип

APPLIED не означает VERIFIED. После apply изменение должно пройти re-measure и quality verification.

## Просмотр

~~~bash
python skills/context-optimizer/scripts/optimization_ledger.py --project . list
python skills/context-optimizer/scripts/optimization_ledger.py --project . show --change-id CHG-001
~~~

## Запись verification

~~~bash
python skills/context-optimizer/scripts/optimization_ledger.py --project . record-verification --change-id CHG-001 --status KEEP --finding-id CTX-001 --metrics-json metrics.json --quality-json quality.json
~~~

Metrics и quality не смешиваются: снижение bytes/tokens отдельно, task success/retries/errors/information loss отдельно.
