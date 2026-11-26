"""Dependency checker. Host is macOS (primary, yigitzra1n-style image build) or Linux
(analysis/diagnostics subset). Package names are provided for both Homebrew and dnf.

brew == None means the tool is provided by the Xcode Command Line Tools or by macOS
itself (not a formula); on macOS such a missing tool points the user at
`xcode-select --install` rather than a brew package.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Dep:
    name: str
    kind: str          # "bin" | "pkgconfig" | "python"
    probe: str
    dnf: str | None
    brew: str | None
    required: bool = True
    why: str = ""
    macos_builtin: bool = False  # satisfied by macOS even if the probe binary is absent


DEPS: tuple[Dep, ...] = (
    Dep("git", "bin", "git", "git", "git"),
    Dep("cmake", "bin", "cmake", "cmake", "cmake"),
    Dep("clang", "bin", "clang", "clang", None, why="compiler (Xcode CLT on macOS)"),
    Dep("ld", "bin", "ld", "binutils", None, why="linker (Xcode CLT on macOS)"),
    Dep("pkg-config", "bin", "pkg-config", "pkgconf-pkg-config", "pkgconf"),
    Dep("libusb", "pkgconfig", "libusb-1.0", "libusb1-devel", "libusb"),
    Dep("libplist", "pkgconfig", "libplist-2.0", "libplist-devel", "libplist"),
    Dep("libimobiledevice", "pkgconfig", "libimobiledevice-1.0", "libimobiledevice-devel", "libimobiledevice"),
    Dep("libirecovery", "pkgconfig", "libirecovery-1.0", "libirecovery-devel", "libirecovery"),
    Dep("ideviceinfo", "bin", "ideviceinfo", "libimobiledevice-utils", "libimobiledevice"),
    Dep("irecovery", "bin", "irecovery", "libirecovery-utils", "libirecovery"),
    Dep("usbmuxd", "bin", "usbmuxd", "usbmuxd", None, macos_builtin=True,
        why="device transport (built into macOS)"),
    Dep("zstd", "bin", "zstd", "zstd", "zstd", why="image (de)compression"),
    Dep("lzfse", "bin", "lzfse", "lzfse", "lzfse", why="kernelcache decompression (kernel kexts/diff)"),
    Dep("img4tool", "bin", "img4tool", None, "img4tool", required=False,
        why="IMG4 (un)wrap/sign — tihmstar tap on macOS"),
    Dep("idevicerestore", "bin", "idevicerestore", "idevicerestore", "idevicerestore", required=False,
        why="stock iOS 15 restore (Recovery Manager)"),
    Dep("idevicebackup2", "bin", "idevicebackup2", "libimobiledevice-utils", "libimobiledevice",
        why="user data backup before any write"),
    Dep("sshpass", "bin", "sshpass", "sshpass", None, required=False,
        why="scripted SSH to the device ramdisk (brew hudochenkov/sshpass on macOS)"),
    Dep("arm-none-eabi-gcc", "bin", "arm-none-eabi-gcc", "arm-none-eabi-gcc-cs", "arm-none-eabi-gcc",
        required=False, why="RP2350 diagnostic adapter firmware"),
)


def _present(d: Dep) -> bool:
    if d.macos_builtin and sys.platform == "darwin":
        return True
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


def install_hints(results: list[tuple[Dep, bool]], include_optional: bool = False,
                  platform: str | None = None) -> list[str]:
    """Return human-ready install commands for the current (or given) platform."""
    platform = platform or sys.platform
    missing = [d for d, ok in results if not ok and (d.required or include_optional)]
    hints: list[str] = []
    if platform == "darwin":
        formulae = sorted({d.brew for d in missing if d.brew})
        if formulae:
            hints.append("brew install " + " ".join(formulae))
        if any(d.brew is None and not d.macos_builtin for d in missing):
            hints.append("xcode-select --install   # для clang/ld и базовых инструментов")
        if any(d.name == "sshpass" for d in missing):
            hints.append("brew install hudochenkov/sshpass/sshpass")
        if any(d.name == "img4tool" for d in missing):
            hints.append("brew install tihmstar/tihmstar/img4tool")
    else:
        pkgs = sorted({d.dnf for d in missing if d.dnf})
        if pkgs:
            hints.append("sudo dnf install -y " + " ".join(pkgs))
    return hints
