# Graphify Adapter

Upstream: https://github.com/Graphify-Labs/graphify

## Роль

Graphify остаётся внешней optional project-local зависимостью. Код Graphify внутрь Context Optimizer не копируется.

## Подтверждённые upstream-команды

- package: `graphifyy`; CLI: `graphify`;
- project install для Codex: `graphify install --project --platform codex`;
- project install для Claude Code: `graphify install --project`;
- project install для Antigravity: `graphify install --project --platform antigravity`;
- generic Agent-Skills: `graphify install --project --platform agents`;
- build: `graphify .`;
- update: `graphify update`;
- query: `graphify query "QUESTION" --budget 2000`;
- DFS query: `graphify query "QUESTION" --dfs --budget 3000`.

## Fast path

Если `graphify-out/graph.json` уже существует, adapter предпочитает graph-first navigation: сначала query graph, затем чтение только target files.

## Что делает наш adapter

1. Проверяет наличие CLI и версию.
2. Проверяет project-scoped skill artifacts для выбранной платформы.
3. Проверяет наличие `graphify-out/graph.json` и базовые graph stats.
4. Считает project profile: source file count и bytes.
5. Может принять audit/CodeBurn JSON как navigation evidence.
6. Даёт recommendation: `USE_EXISTING_GRAPH`, `UPDATE_RECOMMENDED`, `BUILD_RECOMMENDED`, `INSTALL_RECOMMENDED` или `NOT_NEEDED_BY_CURRENT_EVIDENCE`.
7. Формирует mutation plan, но не выполняет его автоматически.
8. Может выполнять только read-only `graphify query` по существующему graph.

## Freshness

`POSSIBLY_STALE` строится только по mtime: если source file новее graph.json. Это сигнал для review, а не доказательство логической устарелости graph.

## Порог рекомендации

Size thresholds (`source_files`, `source_bytes`) являются `HEURISTIC_ESTIMATE`. Более сильное основание — реальные navigation/re-read findings.

## Safety

- установка package требует approval;
- project skill registration требует approval;
- build/update graph требуют approval;
- query по уже существующему graph считается read-only;
- adapter не включает Graphify strict mode автоматически;
- adapter не ставит hooks автоматически.
