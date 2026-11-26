"""EVT0: проверка окружения Fedora и установка зависимостей через DNF."""

from __future__ import annotations

import platform
import shutil
from pathlib import Path

from d11ctl.core import log, runner

_log = log.get("env")

# бинарник → (пакет Fedora, зачем нужен, обязателен ли)
TOOLS = {
    "ideviceinfo": ("libimobiledevice-utils", "сведения об устройстве, Normal-режим", True),
    "idevicebackup2": ("libimobiledevice-utils", "резервные копии", True),
    "idevicediagnostics": ("libimobiledevice-utils", "диагностика периферии", False),
    "usbmuxd": ("usbmuxd", "транспорт Normal-режима", True),
    "irecovery": ("libirecovery-utils", "Recovery/DFU", True),
    "idevicerestore": ("idevicerestore", "штатное восстановление", True),
    "plistutil": ("libplist-utils", "работа с plist", False),
    "clang": ("clang", "сборка нативных компонентов", True),
    "cmake": ("cmake", "сборка", True),
    "git": ("git", "контроль версий", True),
    "rpmbuild": ("rpm-build", "упаковка RPM", False),
    "arm-none-eabi-gcc": ("arm-none-eabi-gcc-cs", "прошивка RP2350", False),
    "ipsw": (None, "разбор kernelcache/DeviceTree (blacktop/ipsw, ставится вручную)", False),
}

DEV_PACKAGES = ["libusb1-devel", "libimobiledevice-devel", "libirecovery-devel",
                "libplist-devel", "llvm", "python3-devel", "arm-none-eabi-newlib"]


def os_release() -> dict:
    p = Path("/etc/os-release")
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v.strip('"')
    return out


def check() -> dict:
    rel = os_release()
    tools = {}
    for binary, (pkg, why, required) in TOOLS.items():
        tools[binary] = {"found": shutil.which(binary) is not None, "package": pkg,
                         "why": why, "required": required}
    missing_pkgs = sorted({t["package"] for t in tools.values() if not t["found"] and t["package"]})
    udev = any(Path(p).exists() for p in ("/usr/lib/udev/rules.d/39-usbmuxd.rules",
                                         "/usr/lib/udev/rules.d/39-libirecovery.rules"))
    return {
        "os": rel.get("PRETTY_NAME", platform.platform()),
        "is_fedora": rel.get("ID") == "fedora",
        "python": platform.python_version(),
        "tools": tools,
        "missing_packages": missing_pkgs,
        "udev_rules": udev,
        "ok": all(t["found"] for t in tools.values() if t["required"]),
    }


def install(dry_run: bool, with_dev: bool = True) -> None:
    report = check()
    pkgs = report["missing_packages"] + (DEV_PACKAGES if with_dev else [])
    if not pkgs:
        _log.info("всё уже установлено")
        return
    if not report["is_fedora"]:
        _log.warning("это не Fedora — команда dnf может не подойти")
    runner.run(["sudo", "dnf", "install", "-y", *pkgs], mutating=True, dry_run=dry_run, timeout=None)
