# Оптимизатор контекста Matreshka

**Навык для анализа и оптимизации контекста AI-агентов: измерение расхода токенов, аудит skills и MCP, оптимизация инструкций и результатов инструментов, навигация по большим проектам, проверка эффективности изменений и интеграция с Matreshka Agent.**

Технический идентификатор: `$context-optimizer`.

## Цель

Уменьшать ненужный context/token cost без ухудшения качества, точности, числа шагов и надёжности AI-агента.

## Базовый цикл

~~~text
ИЗМЕРИТЬ → НАЙТИ ПРИЧИНУ → КЛАССИФИЦИРОВАТЬ → ПРЕДЛОЖИТЬ
→ ПОДТВЕРЖДЕНИЕ → ИЗМЕНЕНИЕ → ПЕРЕИЗМЕРЕНИЕ → ПРОВЕРКА
→ ОСТАВИТЬ / ОТКАТИТЬ
~~~

## Собственное ядро

Проект не требует сторонних оптимизаторов. Основные функции реализованы внутри репозитория:

- `Matreshka Context Telemetry` — runtime/session telemetry для Codex, Claude Code и Antigravity;
- `project_map.py` — нативная карта проекта и оценка навигационной нагрузки;
- аудит project instructions, skills и MCP/tools;
- Context Ingress Audit;
- reversible apply / backup / rollback;
- Optimization Ledger;
- before/after benchmark;
- compact bridge для Matreshka Agent;
- детерминированная политика автоматических запусков.

По умолчанию сеть, сканирование процессов, локальные RPC, hook install и запись session files выключены.

## Команды

~~~bash
python skills/context-optimizer/scripts/context_optimizer.py --project . start
python skills/context-optimizer/scripts/context_optimizer.py --project . adopt
python skills/context-optimizer/scripts/context_optimizer.py --project . resume
python skills/context-optimizer/scripts/context_optimizer.py --project . check
python skills/context-optimizer/scripts/context_optimizer.py --project . status
python skills/context-optimizer/scripts/context_optimizer.py --project . optimize
python skills/context-optimizer/scripts/context_optimizer.py --project . --signal '{"scenario":"NEW_PROJECT","baseline_exists":false}' auto
~~~

`optimize` готовит предложения, но не применяет изменения без отдельного подтверждения.

## Автоматические сценарии

- новый проект без baseline → `start`;
- первое подключение к готовому проекту → `adopt`;
- возобновление после паузы при отсутствующем/устаревшем baseline → `resume`;
- evidence перегрузки → `check`;
- отсутствие нового evidence → полный аудит не запускается;
- в режиме `auto` решение принимается внутри skill, чтобы Matreshka не дублировала пороги.

## Измерения

- provider counters → `PROVIDER_MEASURED`;
- точный статический размер → bytes;
- неизвестные runtime значения → `UNKNOWN`;
- bytes, эвристики и runtime tokens никогда не смешиваются.

## Интеграция с Matreshka Agent

Matreshka Agent обращается к навыку как к отдельному peer skill и получает только компактный bridge:

~~~text
health
runtimeMeasurement
staticContext
staticRisk
projectMap
topFindings
recommendations
ledger
snapshotId
capturedAt
trigger
approvalRequired
~~~

Большие отчёты и сырые traces не должны попадать в постоянный controller context.

## Dashboard

В Matreshka dashboard предусмотрен отдельный пользовательский раздел **«Контекст»**: состояние, текущий измеренный контекст, статические инструкции, карта проекта, главные проблемы, история оптимизаций, причина последней проверки и действия, требующие подтверждения.

Все пользовательские сообщения и подписи dashboard — на русском языке.

## Безопасность изменений

Каждое изменение оформляется отдельно как `CHG-xxx`: dry-run → SHA-256 baseline → approval → backup → одна операция → re-measure → quality verification → KEEP/ROLLBACK.

Меньше токенов не считается успехом, если качество ухудшилось.

## Рабочая v0.4: автономное состояние и исправленная телеметрия

В ветке разработки добавлен `skills/context-optimizer/scripts/standalone.py`.
Он сохраняет нормализованный аудит, русский Markdown/HTML-отчёт и состояние следующей сессии
только с `--save`. `remember` записывает ограниченную ссылку в файл инструкций после отдельного
подтверждения содержимого. Поддержка установки и быстрых команд внутри четырёх приложений
остаётся отдельным незакрытым этапом; этот шаг не является полным релизом v0.4.

Подробности: `skills/context-optimizer/references/standalone.md`.
Ревью, исправления и оставшиеся риски: `docs/reviews/V0.4-STEP-1.md`.
