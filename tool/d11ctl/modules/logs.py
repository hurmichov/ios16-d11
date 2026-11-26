"""Log Manager: просмотр и анализ сохранённых журналов сессий и логов загрузки."""

from __future__ import annotations

import json
from pathlib import Path

from d11ctl.modules import bootmon


def sessions(log_dir: Path) -> list[Path]:
    return sorted(log_dir.glob("session-*.jsonl"))


def tail(path: Path, n: int = 50, level: str | None = None) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if level and e.get("level") != level.upper():
            continue
        out.append(e)
    return out[-n:]


def analyze(path: Path) -> dict:
    """Для текстовых логов загрузки — классификация через Boot Monitor."""
    return bootmon.analyze_file(path)
