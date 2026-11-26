"""Log Manager: every run gets a session directory with a human log and a JSONL event log."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

DEFAULT_ROOT = Path(os.environ.get("HALCYON_HOME", Path.home() / ".local/share/halcyon"))


class Session:
    def __init__(self, root: Path | None = None, name: str = "run"):
        root = Path(root or DEFAULT_ROOT) / "logs"
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.dir = root / f"{stamp}-{name}"
        i = 1
        while self.dir.exists():
            self.dir = root / f"{stamp}-{name}-{i}"
            i += 1
        self.dir.mkdir(parents=True)
        self._events = open(self.dir / "events.jsonl", "a", encoding="utf-8")
        self.log = logging.getLogger(f"halcyon.{self.dir.name}")
        self.log.setLevel(logging.DEBUG)
        fh = logging.FileHandler(self.dir / "halcyon.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        self.log.addHandler(fh)

    def event(self, kind: str, **data) -> None:
        rec = {"t": time.time(), "kind": kind, **data}
        self._events.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        self._events.flush()
        self.log.info("%s %s", kind, json.dumps(data, ensure_ascii=False, default=str))

    def attach(self, name: str, content: str | bytes) -> Path:
        p = self.dir / name
        p.write_bytes(content.encode() if isinstance(content, str) else content)
        return p

    def close(self) -> None:
        self._events.close()
        for h in list(self.log.handlers):
            h.close()
            self.log.removeHandler(h)


def read_events(session_dir: Path) -> list[dict]:
    out = []
    with open(Path(session_dir) / "events.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
