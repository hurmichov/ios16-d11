"""Recovery Manager: резервная копия и штатное восстановление на подписанную iOS 15."""

from __future__ import annotations

import time
from pathlib import Path

from d11ctl.core import log, runner
from d11ctl.core.safety import Context, guard_write
from d11ctl.modules import firmware
from d11ctl.modules.device import DeviceInfo

_log = log.get("recovery")


def backup(ctx: Context, dev: DeviceInfo) -> Path | None:
    """Полный бэкап через idevicebackup2. Запись идёт на ПК, устройство не меняется."""
    if dev.mode != "normal":
        raise RuntimeError("бэкап возможен только в Normal-режиме")
    dest = ctx.paths.backups / f"{dev.udid or 'device'}-{time.strftime('%Y%m%d-%H%M%S')}"
    _log.info("рекомендуется включить шифрование бэкапа: `idevicebackup2 encryption on`"
              " — иначе пароли и Health не сохранятся")
    res = runner.run(["idevicebackup2", "backup", "--full", str(dest)],
                     mutating=True, dry_run=ctx.dry_run, timeout=None)
    if res.skipped:
        return None
    if not res.ok:
        raise RuntimeError(f"бэкап не удался: {res.stderr.strip()}")
    _log.info("бэкап сохранён: %s", dest)
    return dest


def signed_base(product: str) -> firmware.Firmware:
    signed = [f for f in firmware.list_firmwares(product) if f.signed and f.version.startswith("15.")]
    if not signed:
        raise LookupError(f"для {product} сейчас не подписана ни одна iOS 15 — штатный restore невозможен")
    return signed[0]


def restore(ctx: Context, dev: DeviceInfo, ipsw: Path | None, erase: bool) -> None:
    if not dev.product_type:
        raise RuntimeError("модель неизвестна — подключи устройство в Normal или Recovery")
    fw = signed_base(dev.product_type)
    _log.info("подписана: iOS %s (%s)", fw.version, fw.build)
    if ipsw is None:
        ipsw = ctx.paths.cache / fw.filename
        if not ipsw.exists():
            if ctx.dry_run:
                _log.warning("[dry-run] нужно скачать %s (%s)", fw.filename, fw.url)
            else:
                ipsw = firmware.download(fw, ctx.paths.cache)
    elif not firmware.verify(ipsw, fw):
        raise RuntimeError(f"{ipsw} не совпадает с подписанной {fw.version} по хешу")

    cmd = ["idevicerestore", "-y"] + (["-e"] if erase else []) + [str(ipsw)]
    if not guard_write(ctx, dev, ("стереть и " if erase else "") + f"восстановить iOS {fw.version}"):
        _log.warning("[dry-run] команда: %s", " ".join(cmd))
        return
    res = runner.run(cmd, mutating=True, dry_run=False, timeout=None)
    if not res.ok:
        raise RuntimeError(f"idevicerestore: код {res.returncode}, подробности в журнале сессии")
    _log.info("восстановление завершено")
