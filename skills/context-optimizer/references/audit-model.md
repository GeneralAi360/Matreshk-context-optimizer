# Модель аудита проекта

## Слои

Read-only аудит v0.1 разделён на независимые слои:

1. **STATIC_CONTEXT** — точные bytes instruction/skill файлов и exact duplicate lines.
2. **INSTRUCTION_HYGIENE** — кандидаты на progressive disclosure, history/progress и временные правила.
3. **SKILLS** — размер body, длина description, scope collision и routing overlap.
4. **MCP_CONFIG** — регистрации MCP, дубли по имени и локальные команды, которые не обнаружены.
5. **CODEBURN** — runtime/session evidence, когда внешний CodeBurn доступен.
6. **CONTEXT_INGRESS** — большие/repetitive payload и CodeBurn context-tree composition.

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
