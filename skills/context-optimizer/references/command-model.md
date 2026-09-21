# Команды Context Optimizer

## Общий принцип

Пользователь видит короткие команды, а Matreshka Agent вызывает тот же интерфейс программно. Все объяснения и статусы для пользователя — на русском.

~~~text
start     новый проект
adopt     подключение к готовому проекту
resume    продолжение после паузы
check     событийная проверка
status    текущее состояние
optimize  план оптимизации без автоматического применения
auto      внутренний режим для Matreshka: решить RUN/SKIP по сигналу
~~~

Базовый вызов:

~~~bash
python skills/context-optimizer/scripts/context_optimizer.py --project . <command>
~~~

## auto

Matreshka передаёт компактный JSON сигнал через `--signal`. Skill сам вызывает trigger policy и возвращает либо конкретную проверку (`start/adopt/resume/check`), либо `SKIPPED/NO_TRIGGER`.

~~~bash
python skills/context-optimizer/scripts/context_optimizer.py --project . --signal '{"scenario":"EXISTING_PROJECT","baseline_exists":false}' auto
~~~

Это единственный рекомендуемый путь для автоматических запусков: Matreshka не дублирует пороги внутри собственного controller-кода.

## start

Использовать один раз в начале нового проекта после появления project root/первичной структуры и до массовой реализации.

Результат: `baseline_candidate`, static audit, нативная карта проекта, доступная runtime telemetry и compact bridge. `baseline_candidate.snapshot_id` сохраняется контроллером Matreshka при наличии state-write authority.

Пользовательское сообщение: «Контроль контекста подключён. Снят базовый снимок до масштабной реализации.»

## adopt

Использовать при первом подключении к существующему проекту, который ранее не управлялся Matreshka.

До любых архитектурных изменений: read-only orientation → audit → project map → рекомендации.

## resume

Использовать при восстановлении старого run, особенно если последний аудит старше 24 часов или baseline отсутствует.

Нельзя считать старый dashboard актуальным без перепроверки.

## check

Не является периодическим таймером «на всякий случай». Запускается при evidence-trigger: слишком широкий контекст, повторные чтения, compaction, большие tool results, заметный рост инструкций, изменение skills/tools или существенное изменение структуры проекта.

## status

Быстрый пользовательский запрос текущего состояния. Может выполнить свежую read-only сверку, если сохранённая проекция устарела.

## optimize

Формирует только список proposed changes. Каждое изменение получает отдельный `CHG-xxx` и требует approval перед mutation.

## Машинные и пользовательские имена

Machine command остаётся коротким английским идентификатором для переносимости между ОС и harness. Dashboard, сообщения, пояснения, ошибки и рекомендации локализуются на русский.

## Не делать

- Не создавать скрытые команды установки сторонних инструментов.
- Не выполнять mutation из `start`, `adopt`, `resume`, `check` или `status`.
- Не считать запуск skill разрешением на запись, Git, сеть или dependency install.