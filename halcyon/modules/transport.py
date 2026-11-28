"""USB Transport: thin, mockable wrappers around libimobiledevice / libirecovery CLIs.

Using the CLIs (instead of ctypes bindings) keeps Halcyon trivially packageable on
Fedora, and every call is logged and can be replaced by a fake runner in tests.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence

Runner = Callable[[Sequence[str], float], "Result"]


@dataclass
class Result:
    rc: int
    out: str
    err: str


def _default_runner(argv: Sequence[str], timeout: float) -> Result:
    if not shutil.which(argv[0]):
        return Result(127, "", f"{argv[0]}: not installed")
    try:
        p = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return Result(124, "", f"{argv[0]}: timeout")
    return Result(p.returncode, p.stdout, p.stderr)


class Transport:
    def __init__(self, runner: Runner | None = None, timeout: float = 15.0):
        self.run = runner or _default_runner
        self.timeout = timeout

    # --- normal mode (lockdownd via usbmuxd) ---
    def list_udids(self) -> list[str]:
        r = self.run(["idevice_id", "-l"], self.timeout)
        return [l.strip() for l in r.out.splitlines() if l.strip()] if r.rc == 0 else []

    def lockdown_info(self, udid: str | None = None, domain: str | None = None) -> dict[str, str]:
        argv = ["ideviceinfo"]
        if udid:
            argv += ["-u", udid]
        if domain:
            argv += ["-q", domain]
        r = self.run(argv, self.timeout)
        return parse_kv(r.out) if r.rc == 0 else {}

    # --- recovery / DFU (libirecovery) ---
    def irecovery_query(self) -> dict[str, str]:
        r = self.run(["irecovery", "-q"], self.timeout)
        return parse_kv(r.out) if r.rc == 0 else {}


def parse_kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out
