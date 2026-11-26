"""Static device knowledge: the target and the donor candidates.

Values marked ``verify=True`` come from public references and must be confirmed
against a real BuildManifest before being trusted by any write path.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeviceSpec:
    product_type: str
    board_config: str
    cpid: int
    bdid: int | None
    soc: str
    name: str
    ram_mb: int
    max_official: str
    role: str  # "target" | "donor"
    notes: tuple[str, ...] = field(default_factory=tuple)
    verify: bool = False


TARGETS: tuple[DeviceSpec, ...] = (
    DeviceSpec("iPhone9,2", "d11ap", 0x8010, 0x0A, "A10 Fusion (T8010)", "iPhone 7 Plus (Global)",
               3072, "15.8.x", "target", ("Qualcomm MDM9645M baseband",)),
    DeviceSpec("iPhone9,4", "d111ap", 0x8010, 0x0E, "A10 Fusion (T8010)", "iPhone 7 Plus (GSM)",
               3072, "15.8.x", "target", ("Intel XMM7360 baseband",)),
)

# Donor candidates for iOS 16 userspace / kernel components.
DONORS: tuple[DeviceSpec, ...] = (
    DeviceSpec("iPad7,11", "j171ap", 0x8010, None, "A10 Fusion (T8010)", "iPad (7th gen) Wi-Fi",
               3072, "18.x", "donor",
               ("Same SoC: primary kernelcache/DT donor candidate",), verify=True),
    DeviceSpec("iPad7,12", "j172ap", 0x8010, None, "A10 Fusion (T8010)", "iPad (7th gen) Cellular",
               3072, "18.x", "donor",
               ("Same SoC, has baseband stack (different modem)",), verify=True),
    DeviceSpec("iPad7,5", "j71bap", 0x8010, None, "A10 Fusion (T8010)", "iPad (6th gen) Wi-Fi",
               2048, "17.x", "donor", ("Same SoC, 2 GB RAM",), verify=True),
    DeviceSpec("iPhone10,2", "d21ap", 0x8015, None, "A11 Bionic (T8015)", "iPhone 8 Plus",
               3072, "16.7.x", "donor",
               ("Phone userspace (SpringBoard phone idiom, Telephony) donor; different SoC",), verify=True),
    DeviceSpec("iPhone10,5", "d211ap", 0x8015, None, "A11 Bionic (T8015)", "iPhone 8 Plus (GSM)",
               3072, "16.7.x", "donor", ("Phone userspace donor; different SoC",), verify=True),
)

ALL: tuple[DeviceSpec, ...] = TARGETS + DONORS


def by_product_type(pt: str) -> DeviceSpec | None:
    for d in ALL:
        if d.product_type.lower() == pt.lower():
            return d
    return None


def target_for(cpid: int | None = None, bdid: int | None = None,
               product_type: str | None = None) -> DeviceSpec | None:
    """Return the target spec matching the given identifiers, or None."""
    for t in TARGETS:
        if product_type and t.product_type.lower() != product_type.lower():
            continue
        if cpid is not None and t.cpid != cpid:
            continue
        if bdid is not None and t.bdid is not None and t.bdid != bdid:
            continue
        return t
    return None
