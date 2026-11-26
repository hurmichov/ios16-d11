"""Hardware Diagnostics: the component matrix and live probes over lockdownd.

Device-side probes (ioreg class presence over SSH) are listed so they can be run once a
port boots far enough to have SSH; until then only lockdown domains are queried.
"""

from __future__ import annotations

from dataclasses import dataclass

from halcyon.modules.transport import Transport


@dataclass(frozen=True)
class Component:
    key: str
    name: str
    ioreg_classes: tuple[str, ...]
    track: str = "main"  # "main" | "research"


# ioreg class names are *candidates* taken from public A10 ioreg dumps; confirm them
# against a stock iOS 15 dump of your own device (`halcyon hw probe-script`) in EVT1.
COMPONENTS: tuple[Component, ...] = (
    Component("display", "Дисплей", ("AppleCLCD", "IOMobileFramebuffer")),
    Component("touch", "Сенсор / 3D Touch", ("AppleMultitouchSPI", "AppleMultitouchN1SPI")),
    Component("gpu", "GPU (PowerVR-derived, AGX G9)", ("AGXAcceleratorG9P", "AGXAccelerator")),
    Component("wifi", "Wi-Fi (BCM4355)", ("AppleBCMWLANCore", "AppleBCMWLANBusInterfacePCIe")),
    Component("bt", "Bluetooth", ("AppleConvergedIPCOLYBTControl", "AppleBluetoothModule")),
    Component("audio", "Звук / микрофоны", ("AppleCS42L71Audio", "AppleCS35L26Amp", "AppleEmbeddedAudio")),
    Component("camera", "Камеры (ISP)", ("AppleH9CamIn", "AppleH9ISP")),
    Component("taptic", "Taptic Engine", ("AppleHapticsSupportCallan", "AppleHaptics")),
    Component("home", "Кнопка Home (сенсорная)", ("AppleMesaButton", "AppleHIDTransportHome")),
    Component("touchid", "Touch ID", ("AppleMesaSEPDriver", "AppleBiometricSensor"), "research"),
    Component("baseband", "Мобильная связь", ("AppleBasebandPCI", "AppleBasebandManager"), "research"),
    Component("charger", "Зарядка", ("AppleARMPMUCharger", "AppleSMCCharger")),
    Component("pmu", "Управление питанием", ("AppleDialogSPMIPMU", "AppleARMPMU")),
    Component("sleep", "Режим сна", ("IOPMrootDomain",)),
    Component("sep", "Secure Enclave", ("AppleSEPManager", "AppleSEPKeyStore"), "research"),
)


def ioreg_probe_script() -> str:
    """Shell snippet to run on the device (over SSH) — prints PRESENT/ABSENT per component."""
    lines = ["#!/bin/sh", "R=$(ioreg -l 2>/dev/null)"]
    for c in COMPONENTS:
        alt = "|".join(c.ioreg_classes)
        lines.append(f'echo "$R" | grep -Eq "<class ({alt})" && echo "{c.key} PRESENT" || echo "{c.key} ABSENT"')
    return "\n".join(lines) + "\n"


def battery(t: Transport, udid: str | None = None) -> dict[str, str]:
    return t.lockdown_info(udid, "com.apple.mobile.battery")
