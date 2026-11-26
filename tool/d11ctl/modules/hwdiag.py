"""Hardware Diagnostics: опрос периферии устройства в Normal-режиме через libimobiledevice."""

from __future__ import annotations

from d11ctl.core import log, runner
from d11ctl.modules.device import parse_ideviceinfo

_log = log.get("hwdiag")

DOMAINS = {
    "battery": ["ideviceinfo", "-q", "com.apple.mobile.battery"],
    "wifi_bt": ["ideviceinfo", "-k", "WiFiAddress"],
    "bt_addr": ["ideviceinfo", "-k", "BluetoothAddress"],
    "baseband": ["ideviceinfo", "-k", "BasebandVersion"],
    "touchid": ["ideviceinfo", "-q", "com.apple.mobile.iTunes", "-k", "BiometricKitInfo"],
}

IOREG = {
    "charger": "AppleARMPMUCharger",
    "battery_gauge": "AppleSmartBattery",
}


def run_all() -> dict:
    report = {}
    for name, cmd in DOMAINS.items():
        try:
            r = runner.run(cmd)
            report[name] = {"ok": r.ok, "value": parse_ideviceinfo(r.stdout) or r.stdout.strip() or None}
        except runner.ToolMissing as e:
            report[name] = {"ok": False, "error": str(e)}
    for name, entry in IOREG.items():
        try:
            r = runner.run(["idevicediagnostics", "ioregentry", entry])
            report[name] = {"ok": r.ok and bool(r.stdout.strip()), "bytes": len(r.stdout)}
        except runner.ToolMissing as e:
            report[name] = {"ok": False, "error": str(e)}
    _log.info("диагностика завершена", extra={"data": report})
    return report
