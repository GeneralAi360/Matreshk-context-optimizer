# Установка Context Optimizer

Полное руководство находится в [skills/context-optimizer/references/installation.md](skills/context-optimizer/references/installation.md).

Начните с проверки Python 3.11+, затем выберите приложение и запустите `install.py` из распакованного пакета.
Предпросмотр не пишет файлы. Запись требует `--approve INSTALL-...` из вашего предпросмотра.

```text
python3 install.py install --host codex --project "/путь/к/проекту"
```

В Windows: `py -3` вместо `python3`. Значения host: `codex`, `claude`, `cursor`, `antigravity`, `antigravity-cli`.
Для остальных локальных проектов — `--scope user` вместо `--project ...`.

После установки: в Codex `$context-optimizer help`, в Claude Code / Cursor / Antigravity `/context-optimizer help`.
Рабочая v0.4 ещё не означает, что завершено усиление применения произвольных исправлений. `optimize` остаётся планом; ограниченная запись памяти `remember` требует отдельного подтверждения.
