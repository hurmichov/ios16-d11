"""USB Transport: перечисление Apple-устройств на шине.

Через sysfs, без лишних зависимостей. Нужно, чтобы различать Normal / Recovery / DFU
даже тогда, когда usbmuxd или irecovery ещё не установлены.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

APPLE_VID = 0x05AC
# Известные PID'ы режимов (из libirecovery)
MODE_BY_PID = {
    0x1227: "dfu",
    0x1281: "recovery",
    0x1280: "recovery",
    0x1282: "recovery",
    0x1283: "recovery",
    0x1222: "wtf",
}
NORMAL_PID_RANGE = range(0x12A0, 0x12B0)


@dataclass
class UsbDevice:
    bus_path: str
    vid: int
    pid: int
    serial: str
    product: str

    @property
    def mode(self) -> str:
        if self.pid in MODE_BY_PID:
            return MODE_BY_PID[self.pid]
        if self.pid in NORMAL_PID_RANGE:
            return "normal"
        return "unknown"

    def serial_fields(self) -> dict[str, str]:
        """В DFU/Recovery строка serial содержит CPID:8010 CPRV:.. ECID:.. и т.д."""
        out = {}
        for part in self.serial.split():
            if ":" in part:
                k, v = part.split(":", 1)
                out[k] = v.strip("[]")
        return out


def _read(p: Path) -> str:
    try:
        return p.read_text().strip()
    except OSError:
        return ""


def enumerate_apple(sysfs: Path = Path("/sys/bus/usb/devices")) -> list[UsbDevice]:
    found = []
    if not sysfs.exists():
        return found
    for d in sorted(sysfs.iterdir()):
        vid = _read(d / "idVendor")
        if not vid or int(vid, 16) != APPLE_VID:
            continue
        found.append(UsbDevice(
            bus_path=d.name,
            vid=int(vid, 16),
            pid=int(_read(d / "idProduct") or "0", 16),
            serial=_read(d / "serial"),
            product=_read(d / "product"),
        ))
    return found
