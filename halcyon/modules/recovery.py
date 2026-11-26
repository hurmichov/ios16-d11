"""Recovery Manager: backup user data and restore stock (signed) iOS 15 with idevicerestore.

This is the escape hatch. It only uses Apple-signed stock firmware and the standard
restore path, so it is the one write operation that is always considered safe-ish.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from halcyon.modules import device as devmod
from halcyon.modules.firmware import IPSW
from halcyon.modules.logs import Session
from halcyon.modules.safety import Guard, require_ipsw_matches, require_target


def backup(dest: Path, guard: Guard, session: Session, udid: str | None = None) -> list[str]:
    argv = ["idevicebackup2"] + (["-u", udid] if udid else []) + ["backup", "--full", str(dest)]
    session.event("backup.plan", argv=argv, dry_run=guard.dry_run)
    if guard.dry_run:
        return argv
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(argv, check=True)
    session.event("backup.done", dest=str(dest))
    return argv


def restore_stock(ipsw_path: Path, guard: Guard, session: Session, erase: bool = False) -> list[str]:
    state = devmod.detect()
    require_target(state)
    with IPSW(ipsw_path) as ipsw:
        require_ipsw_matches(state, ipsw)
        if not ipsw.product_version.startswith("15."):
            raise ValueError(f"stock restore expects iOS 15.x, got {ipsw.product_version}")
        session.event("restore.ipsw", version=ipsw.product_version, build=ipsw.build)
    argv = ["idevicerestore"]
    if state.ecid:
        argv += ["--ecid", state.ecid]
    if erase:
        argv.append("-e")
    argv.append(str(ipsw_path))
    session.event("restore.plan", argv=argv, dry_run=guard.dry_run)
    if guard.require_write("restore the device"):
        subprocess.run(argv, check=True)
        session.event("restore.done")
    return argv
