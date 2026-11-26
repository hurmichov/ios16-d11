"""Boot Monitor: чтение лога загрузки (последовательный порт адаптера RP2350 или файл)
и классификация ошибок."""

from __future__ import annotations

import os
import re
import select
import sys
import termios
import time
from dataclasses import dataclass
from pathlib import Path

from d11ctl.core import log

_log = log.get("bootmon")


@dataclass(frozen=True)
class Rule:
    code: str
    stage: str
    pattern: re.Pattern
    hint: str


def _r(code, stage, rx, hint):
    return Rule(code, stage, re.compile(rx, re.IGNORECASE), hint)


# Порядок важен: более специфичные правила раньше.
RULES = [
    _r("SEP_PANIC", "kernel", r"SEP (panic|ROM boot|firmware).*(fail|panic)|sep.*not responding",
       "SEP не принял прошивку или протокол несовместим — см. docs/SEP.md"),
    _r("AMFI", "kernel", r"AMFI:|code signature.*invalid|amfid.*(denied|kill)",
       "Отказ проверки подписи кода"),
    _r("ROOT_WAIT", "kernel", r"Waiting on .*IOResources|Still waiting for root device",
       "Ядро не нашло корневой том: APFS/NAND-драйвер или boot-args"),
    _r("WATCHDOG", "kernel", r"watchdog (timeout|panic)|wdt reset",
       "Зависание — драйвер не ответил вовремя (часто питание/PMU)"),
    _r("KPANIC", "kernel", r"panic\(cpu \d+ caller",
       "Kernel panic — разобрать backtrace и имя kext"),
    _r("KEXT_FAIL", "kernel", r"(kext|kxld).*(fail|not found|unresolved)",
       "Драйвер не загрузился (символы/ABI)"),
    _r("LAUNCHD", "userspace", r"launchd.*(crash|exit|abort)|com\.apple\.launchd.*failed",
       "Падение launchd — userspace не поднялся"),
    _r("SPRINGBOARD", "userspace", r"SpringBoard.*(crash|exit|jetsam)",
       "Падение SpringBoard"),
    _r("IBOOT_ERR", "iboot", r"(image|img4).*(validation|decode) fail|boot failure",
       "iBoot отклонил образ: подпись, формат IMG4 или DeviceTree"),
    _r("STAGE_IBOOT", "iboot", r"iBoot-\d+|=======================================", "этап: iBoot"),
    _r("STAGE_KERNEL", "kernel", r"Darwin Kernel Version", "этап: XNU стартовало"),
    _r("STAGE_LAUNCHD", "userspace", r"launchd\[1\]|BSD root:", "этап: смонтирован root, launchd"),
]


@dataclass
class Event:
    line_no: int
    code: str
    stage: str
    text: str
    hint: str


def classify_line(line: str, line_no: int = 0) -> Event | None:
    for r in RULES:
        if r.pattern.search(line):
            return Event(line_no, r.code, r.stage, line.strip()[:300], r.hint)
    return None


def analyze(lines) -> dict:
    events, furthest = [], None
    order = {"iboot": 1, "kernel": 2, "userspace": 3}
    for i, line in enumerate(lines, 1):
        ev = classify_line(line, i)
        if ev:
            events.append(ev)
            if furthest is None or order[ev.stage] > order[furthest]:
                furthest = ev.stage
    errors = [e for e in events if not e.code.startswith("STAGE_")]
    return {
        "furthest_stage": furthest,
        "verdict": errors[-1].code if errors else ("NO_ERRORS_SEEN" if events else "EMPTY"),
        "errors": [e.__dict__ for e in errors],
        "stages": [e.__dict__ for e in events if e.code.startswith("STAGE_")],
    }


def analyze_file(path: Path) -> dict:
    with path.open(errors="replace") as fh:
        return analyze(fh)


def _open_serial(dev: str, baud: int) -> int:
    fd = os.open(dev, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    speed = getattr(termios, f"B{baud}")
    attrs[0] = 0  # iflag
    attrs[1] = 0  # oflag
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0  # lflag (raw)
    attrs[4] = attrs[5] = speed
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    return fd


def monitor(dev: str, out: Path, baud: int = 115200, duration: float | None = None) -> dict:
    """Живой вывод с порта: дублирует в файл, подсвечивает классифицированные события."""
    fd = _open_serial(dev, baud)
    _log.info("слушаю %s @ %d, запись в %s (Ctrl+C — стоп)", dev, baud, out)
    buf, lines, start = b"", [], time.time()
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out.open("a", encoding="utf-8") as fh:
            while duration is None or time.time() - start < duration:
                r, _, _ = select.select([fd], [], [], 0.5)
                if not r:
                    continue
                buf += os.read(fd, 4096)
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    line = raw.decode("utf-8", "replace").rstrip("\r")
                    stamp = f"{time.time() - start:9.3f}"
                    fh.write(f"[{stamp}] {line}\n")
                    lines.append(line)
                    ev = classify_line(line, len(lines))
                    mark = f"  <<< {ev.code}: {ev.hint}" if ev else ""
                    sys.stdout.write(f"[{stamp}] {line}{mark}\n")
                fh.flush()
    except KeyboardInterrupt:
        pass
    finally:
        os.close(fd)
    return analyze(lines)
