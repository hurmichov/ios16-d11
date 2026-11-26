"""Firmware Manager: open IPSW archives, read BuildManifest, locate & verify components."""

from __future__ import annotations

import hashlib
import plistlib
import zipfile
from dataclasses import dataclass
from pathlib import Path

# Components Halcyon cares about, in BuildManifest naming.
KEY_COMPONENTS = (
    "KernelCache", "DeviceTree", "SEP", "RestoreSEP", "BasebandFirmware",
    "iBSS", "iBEC", "LLB", "iBoot", "RestoreRamDisk", "RestoreKernelCache",
    "OS", "Cryptex1,SystemOS", "StaticTrustCache", "AOP", "ANE", "AVE",
    "Multitouch", "AudioCodecFirmware", "ISP", "SmartIOFirmware", "BatteryCharging0",
)


@dataclass
class Identity:
    index: int
    board_config: str
    cpid: int | None
    bdid: int | None
    variant: str
    components: dict[str, str]  # name -> path inside IPSW
    digests: dict[str, bytes]

    @property
    def is_erase(self) -> bool:
        return "erase" in self.variant.lower()


class IPSW:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path)
        self.manifest = plistlib.loads(self.zip.read("BuildManifest.plist"))
        self.product_version: str = self.manifest.get("ProductVersion", "?")
        self.build: str = self.manifest.get("ProductBuildVersion", "?")
        self.supported: list[str] = list(self.manifest.get("SupportedProductTypes", []))
        self.identities = [self._identity(i, bi) for i, bi in enumerate(self.manifest.get("BuildIdentities", []))]

    def close(self) -> None:
        self.zip.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @staticmethod
    def _int(v) -> int | None:
        if isinstance(v, int):
            return v
        try:
            return int(str(v), 0)
        except (TypeError, ValueError):
            return None

    def _identity(self, i: int, bi: dict) -> Identity:
        info = bi.get("Info", {})
        comps, digests = {}, {}
        for name, ent in bi.get("Manifest", {}).items():
            p = ent.get("Info", {}).get("Path")
            if p:
                comps[name] = p
            if "Digest" in ent:
                digests[name] = ent["Digest"]
        return Identity(i, str(info.get("DeviceClass", "?")).lower(), self._int(bi.get("ApChipID")),
                        self._int(bi.get("ApBoardID")), str(info.get("Variant", "")), comps, digests)

    def identities_for(self, board_config: str) -> list[Identity]:
        return [x for x in self.identities if x.board_config == board_config.lower()]

    def read(self, inner_path: str) -> bytes:
        return self.zip.read(inner_path)

    def has(self, inner_path: str) -> bool:
        try:
            self.zip.getinfo(inner_path)
            return True
        except KeyError:
            return False

    def extract(self, inner_path: str, dest_dir: Path) -> Path:
        dest = Path(dest_dir) / inner_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self.zip.open(inner_path) as src, open(dest, "wb") as dst:
            while chunk := src.read(1 << 20):
                dst.write(chunk)
        return dest

    def verify_zip(self) -> list[str]:
        """CRC-check every member. Returns list of bad members (empty == OK)."""
        bad = self.zip.testzip()
        return [bad] if bad else []


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()
