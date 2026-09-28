# Apply / Backup / Rollback

Этот слой выполняет **только одно заранее описанное обратимое изменение**. Finding сам по себе не даёт права менять проект.

## Поддерживаемые операции

- `REPLACE_EXACT_TEXT` — точечная замена известного текста;
- `JSON_SET` — изменение одного значения по существующему JSON path;
- `MOVE_PATH` — перенос file/directory в другой путь.

Массовое удаление, shell-команды, произвольный Python, recursive cleanup и изменение `.git`/служебного состояния этим executor не поддерживаются.

## Безопасный цикл

~~~text
finding
→ сформировать change.json
→ dry-run
→ показать пользователю exact diff/target/risk
→ получить точный APPLY-... token
→ apply
→ выполнить сопоставимую задачу после изменения
→ verify
→ VERIFIED_KEEP / NEEDS_MORE_DATA / ROLLBACK_RECOMMENDED
→ при необходимости отдельное подтверждение ROLLBACK-...
~~~

### 1. Dry run

~~~bash
python skills/context-optimizer/scripts/change_executor.py   --project . dry-run --change change.json
~~~

Dry-run не создаёт backup, journal или ledger. Он проверяет:

- формат `CHG-xxx` и `CTX-xxx`;
- разрешённую операцию и параметры;
- path boundary;
- отсутствие symlink/junction в mutation path;
- запрет `.git`, `.context-optimizer` и installer state;
- exact SHA-256 текущего target;
- exact preview результата.

Возвращаемый `APPLY-...` привязан к содержимому change, resolved path, текущему SHA-256 и preview результата. Любое изменение change или target делает старое подтверждение недействительным.

### 2. Apply

~~~bash
python skills/context-optimizer/scripts/change_executor.py   --project . apply --change change.json   --approve "APPLY-СТРОКА_ИЗ_АКТУАЛЬНОГО_DRY_RUN"
~~~

Перед mutation executor:

1. повторно строит preview;
2. проверяет content-bound approval;
3. создаёт backup;
4. сверяет SHA-256 backup с исходным target;
5. ещё раз проверяет target непосредственно перед записью;
6. пишет journal;
7. выполняет одну операцию;
8. валидирует результат;
9. сверяет результат с подтверждённым preview;
10. записывает событие `APPLIED`.

После apply изменение **ещё не считается успешной оптимизацией**.

### 3. Verify

Для полного вывода нужны два сопоставимых benchmark run-файла:

~~~bash
python skills/context-optimizer/scripts/change_executor.py   --project . verify --change-id CHG-001   --before before-run.json --after after-run.json
~~~

Результат:

- `VERIFIED_KEEP` — measured cost снизился и quality regression не обнаружена;
- `ROLLBACK_RECOMMENDED` — сопоставимые данные показали ухудшение/отсутствие требуемого эффекта;
- `NEEDS_MORE_DATA` — данных недостаточно, эвристики не превращаются в PASS.

Перед quality evaluation проверяются current after-hash и целостность backup.

### 4. Rollback

Получите актуальный токен через `status` или результат `verify`:

~~~bash
python skills/context-optimizer/scripts/change_executor.py   --project . status --change-id CHG-001
~~~

Затем:

~~~bash
python skills/context-optimizer/scripts/change_executor.py   --project . rollback --change-id CHG-001   --approve "ROLLBACK-СТРОКА_ИЗ_АКТУАЛЬНОГО_STATUS"
~~~

Rollback остановится, если:

- backup повреждён;
- target/destination менялся после apply;
- journal не соответствует допустимому состоянию;
- approval устарел.

Он не должен затирать новые пользовательские изменения.

## User scope

По умолчанию target обязан находиться внутри project root. `--allow-global` разрешает только user-scope путь внутри домашней папки текущего пользователя; system paths всё равно запрещены.

## Runtime state

~~~text
.context-optimizer/
├── backups/<change_id>/payload
├── journal/<change_id>.json
├── change-locks/
└── optimization-ledger.jsonl
~~~

Эта директория не должна анализироваться как исходный project context и не должна автоматически попадать в Git.

## Что показывать новичку

Перед apply агент обязан простыми словами показать:

- какой файл изменится;
- что именно изменится;
- почему это связано с конкретным finding;
- риск;
- можно ли откатить;
- exact APPLY token.

Нельзя самостоятельно генерировать согласие пользователя. `ROLLBACK_RECOMMENDED` — рекомендация, а не разрешение на откат.
