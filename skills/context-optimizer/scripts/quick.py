#!/usr/bin/env python3
"""Один переносимый обработчик быстрых режимов; без shell/eval/автоустановки."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.dont_write_bytecode = True
MODES = {
    "help": "Показать режимы и их назначение; файлы не меняются.",
    "doctor": "Проверить Python, комплектность и наличие сохранённого аудита.",
    "start": "Новый проект: начальный аудит и сохранение исходного снимка.",
    "adopt": "Готовый проект: первый аудит до изменений архитектуры.",
    "resume": "Новый чат/пауза: перепроверить состояние, не стирая исходный снимок.",
    "check": "Повторный аудит при росте контекста, повторных чтениях или смене инструментов.",
    "status": "Прочитать последний сохранённый отчёт без нового аудита.",
    "optimize": "Подготовить приоритетные предложения. Сам код проекта не меняется.",
    "remember": "Предпросмотр ссылки на состояние в инструкциях; запись только после подтверждения.",
    "finish": "Сохранить итог сессии и доступное сравнение; не обещать экономию по одним байтам.",
}
PROVIDERS = {"codex": "codex", "claude": "claude", "cursor": "none", "antigravity": "antigravity"}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if callable(getattr(stream, "reconfigure", None)):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Режимы Context Optimizer. Полные отчёты локальные, Matreshka не требуется.")
    p.add_argument("mode", choices=MODES, nargs="?", default="help")
    p.add_argument("--harness", choices=PROVIDERS, required=True)
    p.add_argument("--project", default=".")
    p.add_argument("--read-only", action="store_true", help="Не сохранять новый аудит")
    p.add_argument("--approve", help="Только MEMORY-... для remember; не разрешает другие изменения")
    args = p.parse_args()
    if sys.version_info < (3, 11):
        print("Нужен Python 3.11+. Установите его с python.org и повторите проверку.", file=sys.stderr)
        return 2
    if args.approve and (args.mode != "remember" or args.read_only):
        print("Подтверждение допустимо только для записи remember, без --read-only.", file=sys.stderr)
        return 2
    if args.mode == "help":
        print("Режимы оптимизатора контекста\n")
        for mode, description in MODES.items():
            print(mode + " — " + description)
        print("\nВ чате Codex: $context-optimizer adopt. В остальных средах: /context-optimizer adopt.")
        print("start/adopt/resume/check/optimize/finish сохраняют локальный отчёт. Для проверки без записи используйте --read-only.")
        print("remember требует отдельного подтверждения. finish запускается явно до закрытия приложения.")
        return 0
    root = Path(args.project).expanduser().resolve()
    if not root.is_dir():
        print("Каталог проекта не найден.", file=sys.stderr)
        return 2
    if args.mode == "doctor":
        here = Path(__file__).resolve().parent
        missing = [name for name in ("standalone.py", "context_optimizer.py", "native_telemetry.py") if not (here / name).is_file()]
        print("Python: " + sys.version.split()[0])
        print("Каталог проверяемого проекта: " + str(root))
        print("Файлы навыка: " + ("на месте" if not missing else "отсутствуют: " + ", ".join(missing)))
        print("Сохранённое состояние: " + ("найдено" if (root / ".context-optimizer/STATE.md").is_file() else "ещё не создано; начните с start или adopt"))
        print("Телеметрия Cursor не реализована; для него доступен статический аудит." if args.harness == "cursor" else "Токены появятся только при наличии подходящих локальных журналов. Наличие Python не доказывает наличие данных.")
        print("Интерфейс приложения здесь не проверяется. Для проверки целостности установки: install.py doctor.")
        return 2 if missing else 0
    import standalone
    if args.mode == "status" and standalone.read_latest(root) is None:
        print("Сохранённого аудита нет. Запустите start для нового проекта или adopt для существующего. Это не нулевой расход.")
        return 0
    argv = [str(Path(standalone.__file__)), "--project", str(root), "--provider", PROVIDERS[args.harness], "--harness", args.harness]
    if args.mode not in {"status", "remember"} and not args.read_only:
        argv.append("--save")
    if args.approve:
        argv.extend(["--approve", args.approve])
    argv.append(args.mode)
    previous = sys.argv
    try:
        sys.argv = argv
        return standalone.main()
    finally:
        sys.argv = previous


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print("Ошибка: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
