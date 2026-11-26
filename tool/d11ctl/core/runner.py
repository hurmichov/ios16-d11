"""Запуск внешних инструментов (libimobiledevice, irecovery, ipsw...) с учётом dry-run."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass

from d11ctl.core import log

_log = log.get("runner")


class ToolMissing(RuntimeError):
    pass


@dataclass
class Result:
    cmd: list[str]
    returncode: int
    stdout: str
    stderr: str
    skipped: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def run(cmd: list[str], *, mutating: bool = False, dry_run: bool = True,
        timeout: float | None = 120, check: bool = False) -> Result:
    """Запускает команду.

    mutating=True помечает команду, способную что-то изменить на устройстве или
    диске. В режиме dry-run такие команды только печатаются и не выполняются.
    Читающие команды выполняются всегда.
    """
    printable = shlex.join(cmd)
    if mutating and dry_run:
        _log.warning("[dry-run] пропущено: %s", printable)
        return Result(cmd, 0, "", "", skipped=True)

    if not have(cmd[0]):
        raise ToolMissing(f"не найден инструмент '{cmd[0]}' — запусти `d11ctl env check`")

    _log.debug("exec: %s", printable)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    res = Result(cmd, proc.returncode, proc.stdout, proc.stderr)
    _log.debug("exit=%d", proc.returncode, extra={"data": {
        "cmd": cmd, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}})
    if check and not res.ok:
        raise RuntimeError(f"{printable} завершилась с кодом {proc.returncode}: {proc.stderr.strip()}")
    return res
