"""Boot Monitor: stream boot logs (serial / file / stdin), classify milestones and failures.

Sources:
  * the RP2350 diagnostic adapter (USB CDC, /dev/ttyACM*) — see firmware/rp2350-diag
  * any 115200 8N1 UART (a validated DCSD path, if one is confirmed)
  * a saved log file (e.g. verbose boot captured over SSH or by a PongoOS shell)
"""

from __future__ import annotations

import os
import re
import termios
import time
import tty
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Iterator

# (category, severity, stage, regex). Order matters: first match wins.
RULES: list[tuple[str, str, str, re.Pattern]] = [(c, s, st, re.compile(r, re.I)) for c, s, st, r in [
    ("sep-panic",  "fatal", "kernel",  r"panic\(cpu.*\bSEP\b|SEP Panic"),
    ("sep",        "error", "kernel",  r"(sep.*(panic|timeout|failed|not responding))|AppleSEPManager.*(err|fail)|sepfw"),
    ("panic",      "fatal", "kernel",  r"panic\(cpu \d+ caller|Kernel (data abort|instruction fetch abort)"),
    ("watchdog",   "fatal", "kernel",  r"watchdog|wdt.*(timeout|reset)"),
    ("devicetree", "error", "kernel",  r"(missing|could not find|no) .*(device ?tree|DT) (node|entry|property)"),
    ("rootdev",    "error", "bsd",     r"Waiting on <dict.*IOProviderClass|Still waiting for root device"),
    ("apfs",       "error", "bsd",     r"apfs.*(error|failed|corrupt)|mount.*rootfs.*fail"),
    ("codesign",   "error", "launchd", r"AMFI:.*(denied|not valid|kill)|code signature (invalid|not valid)|CS_KILL"),
    ("dyld",       "error", "launchd", r"dyld.*(shared cache|Library not loaded|symbol not found)"),
    ("crash",      "error", "launchd", r"(exited|terminated) (due to|with) (signal|abnormal)|Crashing on exception"),
    ("display",    "info",  "kernel",  r"AppleCLCD|IOMobileFramebuffer|AppleDisplayPipe"),
    ("iboot",      "info",  "iboot",   r"iBoot|iBSS|iBEC|=======================================\s*::"),
    ("xnu",        "info",  "kernel",  r"Darwin Kernel Version"),
    ("bsdroot",    "info",  "bsd",     r"BSD root:|Rooting from"),
    ("launchd",    "info",  "launchd", r"launchd\[1\]|com\.apple\.xpc\.launchd"),
    ("springboard","info",  "ui",      r"SpringBoard.*(launch|started|ready)|backboardd.*start"),
]]

STAGES = ("iboot", "kernel", "bsd", "launchd", "ui")


@dataclass
class Event:
    t: float
    line: str
    category: str
    severity: str
    stage: str


@dataclass
class Summary:
    furthest_stage: str | None = None
    counts: Counter = field(default_factory=Counter)
    first_fatal: Event | None = None
    events: list[Event] = field(default_factory=list)

    def verdict(self) -> str:
        if self.first_fatal:
            return f"FAIL at {self.first_fatal.stage}: {self.first_fatal.category} — {self.first_fatal.line[:160]}"
        if self.furthest_stage == "ui":
            return "UI reached"
        return f"furthest stage: {self.furthest_stage or 'nothing recognised'}"


def classify(line: str, t: float | None = None) -> Event | None:
    for cat, sev, stage, rx in RULES:
        if rx.search(line):
            return Event(t if t is not None else time.time(), line.rstrip(), cat, sev, stage)
    return None


def analyze(lines: Iterable[str]) -> Summary:
    s = Summary()
    for line in lines:
        ev = classify(line)
        if not ev:
            continue
        s.events.append(ev)
        s.counts[ev.category] += 1
        if s.furthest_stage is None or STAGES.index(ev.stage) > STAGES.index(s.furthest_stage):
            s.furthest_stage = ev.stage
        if ev.severity == "fatal" and s.first_fatal is None:
            s.first_fatal = ev
    return s


def open_serial(path: str, baud: int = 115200) -> int:
    fd = os.open(path, os.O_RDONLY | os.O_NOCTTY)
    tty.setraw(fd)
    attrs = termios.tcgetattr(fd)
    speed = getattr(termios, f"B{baud}")
    attrs[4] = attrs[5] = speed
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    return fd


def stream_lines(fd: int) -> Iterator[str]:
    buf = b""
    while True:
        chunk = os.read(fd, 4096)
        if not chunk:
            if buf:
                yield buf.decode("utf-8", "replace")
            return
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            yield line.decode("utf-8", "replace").rstrip("\r")
