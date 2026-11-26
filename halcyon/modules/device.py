"""Device Manager: discover the connected device, its mode and whether it is a supported target."""

from __future__ import annotations

from dataclasses import dataclass, field

from halcyon import devices
from halcyon.modules.transport import Transport


@dataclass
class DeviceState:
    mode: str  # "normal" | "recovery" | "dfu" | "none"
    product_type: str | None = None
    board_config: str | None = None
    cpid: int | None = None
    bdid: int | None = None
    ecid: str | None = None
    ios_version: str | None = None
    build: str | None = None
    udid: str | None = None
    raw: dict = field(default_factory=dict)

    @property
    def spec(self) -> devices.DeviceSpec | None:
        return devices.target_for(self.cpid, self.bdid, self.product_type)

    @property
    def is_target(self) -> bool:
        return self.spec is not None


def _int(v: str | None) -> int | None:
    if not v:
        return None
    try:
        return int(v, 0)
    except ValueError:
        return None


def detect(t: Transport | None = None) -> DeviceState:
    t = t or Transport()
    udids = t.list_udids()
    if udids:
        info = t.lockdown_info(udids[0])
        if info:
            spec = devices.by_product_type(info.get("ProductType", ""))
            return DeviceState(
                mode="normal",
                product_type=info.get("ProductType"),
                board_config=(info.get("HardwareModel") or "").lower() or None,
                cpid=_int(info.get("ChipID")) or (spec.cpid if spec else None),
                bdid=_int(info.get("BoardId")),
                ecid=info.get("UniqueChipID"),
                ios_version=info.get("ProductVersion"),
                build=info.get("BuildVersion"),
                udid=udids[0],
                raw=info,
            )
    q = t.irecovery_query()
    if q:
        mode = q.get("MODE", "").lower()
        return DeviceState(
            mode="dfu" if "dfu" in mode else "recovery",
            product_type=q.get("PRODUCT"),
            board_config=(q.get("MODEL") or "").lower() or None,
            cpid=_int(q.get("CPID")),
            bdid=_int(q.get("BDID")),
            ecid=q.get("ECID"),
            raw=q,
        )
    return DeviceState(mode="none")
