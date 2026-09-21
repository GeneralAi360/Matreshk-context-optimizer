# Apply / Backup / Rollback

Gate 8 вводит только **reversible changes**. Автоматический массовый cleanup по-прежнему запрещён.

## Поддерживаемые операции

- `REPLACE_EXACT_TEXT` — точечная замена exact text;
- `JSON_SET` — установка значения по существующему JSON object path;
- `MOVE_PATH` — перенос file/directory в другой путь.

Каждая операция требует:

- `change_id`;
- exact `expected_before_sha256`;
- source findings;
- `approval_required=true`;
- quality risk;
- явные параметры операции.

## Dry run

~~~bash
python skills/context-optimizer/scripts/change_executor.py --project . dry-run --change change.json
~~~

Dry run не создаёт backup, journal или ledger event.

## Apply

~~~bash
python skills/context-optimizer/scripts/change_executor.py --project . apply --change change.json --approve CHG-001
~~~

Перед mutation executor:

1. проверяет path boundary;
2. сверяет current SHA-256 с `expected_before_sha256`;
3. строит exact operation;
4. требует approval token;
5. создаёт backup;
6. пишет journal;
7. выполняет только один change;
8. валидирует результат;
9. записывает APPLIED event в Optimization Ledger.

## Rollback

~~~bash
python skills/context-optimizer/scripts/change_executor.py --project . rollback --change-id CHG-001 --approve CHG-001:ROLLBACK
~~~

Rollback разрешён только если текущий target/destination всё ещё имеет hash, полученный сразу после apply. Если пользователь или другой агент уже изменил файл, rollback останавливается, чтобы не затереть новые изменения.

## Global scope

По умолчанию target обязан находиться внутри project root. Для global path нужен отдельный `--allow-global`, но approval token всё равно обязателен.

## State

Runtime state хранится локально:

~~~text
.context-optimizer/
├── backups/<change_id>/payload
├── journal/<change_id>.json
└── optimization-ledger.jsonl
~~~

Эта директория не должна попадать обратно в аудит как исходный project context.
