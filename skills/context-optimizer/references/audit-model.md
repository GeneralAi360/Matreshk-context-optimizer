# Модель аудита проекта

## Слои

Read-only аудит разделён на независимые слои:

1. **STATIC_CONTEXT** — точные bytes instruction/skill файлов и exact duplicate lines.
2. **INSTRUCTION_HYGIENE** — кандидаты на progressive disclosure, history/progress и временные правила.
3. **SKILLS** — размер body, длина description, scope collision и routing overlap.
4. **MCP_CONFIG** — регистрации MCP, дубли по имени и локальные команды, которые не обнаружены.
5. **NATIVE_TELEMETRY** — локальные provider/session counters и события.
6. **CONTEXT_INGRESS** — большие/repetitive payload и runtime ingress signals.
7. **PROJECT_MAP** — нативная карта областей и navigation pressure.

## Принцип доказательности

Каждый слой обязан отделять:

- точное наблюдение;
- эвристический вывод;
- неизвестное;
- proposed change.

Размер файла, similarity score или порог сами по себе не дают права на mutation.

## Сводный запуск

~~~bash
python skills/context-optimizer/scripts/audit_extended.py --project .
~~~

Глобальные skills/MCP добавляются только явным флагом:

~~~bash
python skills/context-optimizer/scripts/audit_extended.py --project . --include-global
~~~