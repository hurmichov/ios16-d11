"""Dependency checker for Fedora hosts."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Dep:
    name: str
    kind: str  # "bin" | "pkgconfig" | "python"
    probe: str
    dnf: str
    required: bool = True
    why: str = ""


DEPS: tuple[Dep, ...] = (
    Dep("git", "bin", "git", "git"),
    Dep("cmake", "bin", "cmake", "cmake"),
    Dep("clang", "bin", "clang", "clang"),
    Dep("lld", "bin", "ld.lld", "lld", why="linking arm64 Mach-O helpers"),
    Dep("pkg-config", "bin", "pkg-config", "pkgconf-pkg-config"),
    Dep("libusb", "pkgconfig", "libusb-1.0", "libusb1-devel"),
    Dep("libplist", "pkgconfig", "libplist-2.0", "libplist-devel"),
    Dep("libimobiledevice", "pkgconfig", "libimobiledevice-1.0", "libimobiledevice-devel"),
    Dep("libirecovery", "pkgconfig", "libirecovery-1.0", "libirecovery-devel"),
    Dep("ideviceinfo", "bin", "ideviceinfo", "libimobiledevice-utils"),
    Dep("irecovery", "bin", "irecovery", "libirecovery-utils"),
    Dep("usbmuxd", "bin", "usbmuxd", "usbmuxd"),
    Dep("idevicerestore", "bin", "idevicerestore", "idevicerestore", required=False,
        why="stock iOS 15 restore (Recovery Manager)"),
    Dep("idevicebackup2", "bin", "idevicebackup2", "libimobiledevice-utils",
        why="user data backup before any write"),
    Dep("apfs-fuse", "bin", "apfs-fuse", "apfs-fuse", required=False,
        why="read-only inspection of RootFS images (not in Fedora repos: build from source)"),
    Dep("lzfse", "bin", "lzfse", "lzfse", why="kernelcache decompression (kernel kexts/diff)"),
    Dep("arm-none-eabi-gcc", "bin", "arm-none-eabi-gcc", "arm-none-eabi-gcc-cs", required=False,
        why="RP2350 diagnostic adapter firmware"),
    Dep("rpmbuild", "bin", "rpmbuild", "rpm-build", required=False, why="RPM packaging"),
)


def _present(d: Dep) -> bool:
    if d.kind == "bin":
        return shutil.which(d.probe) is not None
    if d.kind == "pkgconfig":
        if not shutil.which("pkg-config"):
            return False
        return subprocess.run(["pkg-config", "--exists", d.probe]).returncode == 0
    if d.kind == "python":
        try:
            __import__(d.probe)
            return True
        except ImportError:
            return False
    raise ValueError(d.kind)


def check() -> list[tuple[Dep, bool]]:
    return [(d, _present(d)) for d in DEPS]


def dnf_command(results: list[tuple[Dep, bool]], include_optional: bool = False) -> str | None:
    pkgs = sorted({d.dnf for d, ok in results if not ok and (d.required or include_optional)})
    return f"sudo dnf install -y {' '.join(pkgs)}" if pkgs else None
