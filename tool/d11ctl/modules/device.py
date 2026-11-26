"""Device Manager: определение модели и состояния устройства."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from d11ctl.core import log, runner
from d11ctl.modules import usb

_log = log.get("device")


@dataclass
class DeviceInfo:
    mode: str  # normal | recovery | dfu | wtf | unknown
    product_type: str | None = None
    board: str | None = None
    cpid: int | None = None
    ecid: int | None = None
    ios_version: str | None = None
    build: str | None = None
    udid: str | None = None
    pwned: bool = False

    @property
    def ecid_hex(self) -> str:
        return f"0x{self.ecid:x}" if self.ecid is not None else "?"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["cpid"] = f"0x{self.cpid:04x}" if self.cpid is not None else None
        d["ecid"] = self.ecid_hex if self.ecid is not None else None
        return d


def _int(v: str | None) -> int | None:
    if not v:
        return None
    try:
        return int(v, 0)
    except ValueError:
        try:
            return int(v, 16)
        except ValueError:
            return None


def parse_irecovery(text: str) -> DeviceInfo:
    kv = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            kv[k.strip().upper()] = v.strip()
    mode = kv.get("MODE", "unknown").lower()
    return DeviceInfo(
        mode="dfu" if "dfu" in mode else ("recovery" if "recovery" in mode else mode),
        product_type=kv.get("PRODUCT"),
        board=(kv.get("MODEL") or "").lower() or None,
        cpid=_int(kv.get("CPID")),
        ecid=_int(kv.get("ECID")),
        pwned="PWND" in kv.get("SRTG", "") or "PWND" in text,
    )


def parse_ideviceinfo(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            out[k.strip()] = v.strip()
    return out


def _from_normal(dev: usb.UsbDevice) -> DeviceInfo:
    info = DeviceInfo(mode="normal", udid=dev.serial or None)
    if not runner.have("ideviceinfo"):
        _log.warning("ideviceinfo не установлен — модель в Normal-режиме неизвестна")
        return info
    args = ["ideviceinfo"] + (["-u", dev.serial] if dev.serial else [])
    res = runner.run(args)
    if not res.ok:
        _log.warning("ideviceinfo: %s (устройство не доверяет ПК?)", res.stderr.strip())
        return info
    kv = parse_ideviceinfo(res.stdout)
    info.product_type = kv.get("ProductType")
    info.board = (kv.get("HardwareModel") or "").lower() or None
    info.cpid = _int(kv.get("ChipID"))
    info.ecid = _int(kv.get("UniqueChipID"))
    info.ios_version = kv.get("ProductVersion")
    info.build = kv.get("BuildVersion")
    return info


def _from_irecv(dev: usb.UsbDevice) -> DeviceInfo:
    fields = dev.serial_fields()
    if runner.have("irecovery"):
        res = runner.run(["irecovery", "-q"])
        if res.ok:
            info = parse_irecovery(res.stdout)
            info.mode = dev.mode
            return info
    # fallback — только то, что видно в USB serial
    return DeviceInfo(
        mode=dev.mode,
        cpid=_int("0x" + fields["CPID"]) if "CPID" in fields else None,
        ecid=_int("0x" + fields["ECID"]) if "ECID" in fields else None,
        pwned="PWND" in dev.serial,
    )


def detect() -> list[DeviceInfo]:
    out = []
    for d in usb.enumerate_apple():
        if d.mode == "normal":
            out.append(_from_normal(d))
        elif d.mode in ("recovery", "dfu", "wtf"):
            out.append(_from_irecv(d))
    _log.info("найдено Apple-устройств: %d", len(out), extra={"data": [i.as_dict() for i in out]})
    return out


def require_single() -> DeviceInfo:
    devs = detect()
    if not devs:
        raise RuntimeError("устройство не найдено. Проверь кабель и режим (Normal/Recovery/DFU)")
    if len(devs) > 1:
        raise RuntimeError("подключено больше одного Apple-устройства — оставь только iPhone 7 Plus")
    return devs[0]
