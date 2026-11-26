"""Log Manager, нижний уровень: консоль + подробный JSONL-журнал на каждую сессию."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

_SESSION_ID = time.strftime("%Y%m%d-%H%M%S")


class JsonlHandler(logging.Handler):
    def __init__(self, path: Path):
        super().__init__(level=logging.DEBUG)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a", encoding="utf-8")
        self.path = path

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "ts": round(record.created, 3),
            "level": record.levelname,
            "module": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "data", None)
        if extra is not None:
            entry["data"] = extra
        self._fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()
        super().close()


def session_id() -> str:
    return _SESSION_ID


def setup(log_dir: Path, verbose: bool = False) -> Path:
    root = logging.getLogger("d11ctl")
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(levelname).1s %(name)s: %(message)s"))
    root.addHandler(console)

    path = log_dir / f"session-{_SESSION_ID}.jsonl"
    root.addHandler(JsonlHandler(path))
    return path


def get(name: str) -> logging.Logger:
    return logging.getLogger(f"d11ctl.{name}")
