"""Запуск uvicorn с автоперезапуском при изменении кода и .env.dev.

Замена `uvicorn --reload`: на Windows встроенный reload останавливает процесс через CTRL_C_EVENT,
а он уходит всем процессам консоли — nushell от этого закрывается. Здесь uvicorn живёт в своей
группе процессов и получает CTRL_BREAK_EVENT адресно, терминал его не видит.

    uv run python scripts/dev.py [--port 8000]
"""

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WATCH_DIRS = [ROOT / "app", ROOT / "config"]
WATCH_FILES = [ROOT / ".env.dev"]
POLL_INTERVAL = 0.5
STOP_TIMEOUT = 10


def snapshot() -> dict[Path, float]:
    files = [p for d in WATCH_DIRS for p in d.rglob("*.py")] + [p for p in WATCH_FILES if p.exists()]
    result: dict[Path, float] = {}
    for path in files:
        try:
            result[path] = path.stat().st_mtime
        except FileNotFoundError:
            pass  # файл удалили между rglob и stat
    return result


def start(port: int) -> subprocess.Popen[bytes]:
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)]
    if sys.platform == "win32":
        return subprocess.Popen(cmd, cwd=ROOT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    return subprocess.Popen(cmd, cwd=ROOT)


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    # Ctrl+Break уходит только группе uvicorn; он обрабатывает его как штатное завершение
    process.send_signal(signal.CTRL_BREAK_EVENT if sys.platform == "win32" else signal.SIGTERM)
    try:
        process.wait(STOP_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    port = parser.parse_args().port

    state = snapshot()
    process = start(port)
    try:
        while True:
            time.sleep(POLL_INTERVAL)
            current = snapshot()
            if current == state:
                continue
            changed = {p for p in current.keys() | state.keys() if current.get(p) != state.get(p)}
            print(f"[dev] Изменено: {', '.join(str(p.relative_to(ROOT)) for p in sorted(changed))}. Перезапуск...")
            state = current
            stop(process)
            process = start(port)
    except KeyboardInterrupt:
        pass
    finally:
        stop(process)


if __name__ == "__main__":
    main()
