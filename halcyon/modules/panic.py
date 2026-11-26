"""Panic log reader.

When there is no serial console (no DCSD), an on-disk kernel panic is the main
post-mortem signal. iOS writes panics under /var/mobile/Library/Logs/CrashReporter
(or the ramdisk equivalent). The modern format is an `.ips` file: a one-line JSON
header, then a JSON body with a `panicString`. Older/verbose captures are plain text.

This reader handles both, pulls out the key fields, and runs the boot-log classifier
over the panic string so a silent early hang gets the same category as a live log.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from halcyon.modules import bootmon

_KV = re.compile(r'"?([A-Za-z0-9_]+)"?\s*[:=]\s*"?([^",\n}]+)')


@dataclass
class Panic:
    source: str
    panic_string: str
    os_version: str | None = None
    build: str | None = None
    kernel_version: str | None = None
    product: str | None = None
    categories: list[str] = field(default_factory=list)
    verdict: str = "unclassified"
    header: dict = field(default_factory=dict)

    def summary(self) -> str:
        out = [f"# {self.source}",
               f"product: {self.product or '-'}   os: {self.os_version or '-'} ({self.build or '-'})",
               f"kernel : {self.kernel_version or '-'}",
               f"verdict: {self.verdict}",
               f"tags   : {', '.join(self.categories) or '-'}",
               "--- panic string ---",
               self.panic_string.strip()[:4000]]
        return "\n".join(out)


def _try_json(text: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def parse(path: str | Path) -> Panic:
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    header, body = {}, None

    # .ips: first line JSON header, remainder JSON body
    nl = text.find("\n")
    if nl > 0:
        h = _try_json(text[:nl])
        if isinstance(h, dict):
            header = h
            body = _try_json(text[nl + 1:])

    if isinstance(body, dict):
        ps = body.get("panicString") or body.get("macOSPanicString") or ""
        pan = Panic(
            source=p.name,
            panic_string=ps,
            os_version=body.get("os_version") or header.get("os_version"),
            build=body.get("build"),
            product=body.get("product"),
            kernel_version=body.get("kernel"),
            header=header,
        )
    else:
        # plain text panic / verbose capture
        pan = Panic(source=p.name, panic_string=text)
        if m := re.search(r"Darwin Kernel Version[^\n]*", text):
            pan.kernel_version = m.group(0)

    _classify(pan)
    return pan


def _classify(pan: Panic) -> None:
    # Unlike a live log (first match per line), a panic string is dense: collect
    # every rule that matches anywhere, so the real signature isn't masked by the
    # generic "panic(cpu ...)" prefix sharing a line with the actual reason.
    text = pan.panic_string
    cats: list[str] = []
    has_fatal = False
    for cat, sev, _stage, rx in bootmon.RULES:
        if rx.search(text):
            cats.append(cat)
            if sev == "fatal":
                has_fatal = True
    pan.categories = cats
    specific = [c for c in cats if c not in ("panic", "watchdog", "xnu", "iboot", "pongo")]
    if specific:
        pan.verdict = f"likely {specific[0]}"
    elif has_fatal:
        pan.verdict = f"panic ({cats[0]})"
    elif cats:
        pan.verdict = cats[0]
