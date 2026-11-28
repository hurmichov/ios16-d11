"""Kernelcache inventory: list kexts in an iOS 15/16 kernelcache and diff two of them.

iOS 15/16 kernelcaches are a single arm64 Mach-O of type MH_FILESET: the kernel and
every kext are embedded as fileset entries (LC_FILESET_ENTRY), and __PRELINK_INFO.__info
holds a plist with CFBundleVersion and IOKitPersonalities (what hardware each kext binds).

This module is read-only. It is the inventory half of the EVT2 `kext-relink` step and
also answers the EVT1 question "which D11 drivers are missing from the iOS 16 kernel".

Input may be a raw Mach-O, or an IM4P (the IPSW form). lzfse-compressed payloads need
the `lzfse` tool on PATH; uncompressed and macho payloads need nothing.
"""

from __future__ import annotations

import plistlib
import shutil
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from halcyon.modules import img4

MH_MAGIC_64 = 0xFEEDFACF
MH_FILESET = 0x0C
LC_SEGMENT_64 = 0x19
LC_REQ_DYLD = 0x80000000
LC_FILESET_ENTRY = 0x35 | LC_REQ_DYLD


class KCError(ValueError):
    pass


@dataclass
class Kext:
    bundle_id: str
    vmaddr: int = 0
    version: str | None = None
    matches: list[str] = field(default_factory=list)  # IOProviderClass / name matches

    @property
    def is_kernel(self) -> bool:
        return self.bundle_id in ("com.apple.kernel", "com.apple.kec.corecrypto") or \
               self.bundle_id.endswith(".kernel")


@dataclass
class Kernelcache:
    source: str
    filetype: int
    kexts: list[Kext] = field(default_factory=list)
    kernel_version: str | None = None

    def by_id(self) -> dict[str, Kext]:
        return {k.bundle_id: k for k in self.kexts}

    @property
    def is_fileset(self) -> bool:
        return self.filetype == MH_FILESET


# ---------------------------------------------------------------- payload -> macho

def to_macho(data: bytes) -> bytes:
    if data[:4] == struct.pack("<I", MH_MAGIC_64):
        return data
    if data[:1] == b"\x30":  # DER SEQUENCE -> IM4P
        im = img4.parse_im4p(data)
        kind = im.payload_kind
        if kind == "macho":
            return im.payload
        if kind == "lzfse":
            if not shutil.which("lzfse"):
                raise KCError("kernelcache is lzfse-compressed; install `lzfse` (dnf install lzfse)")
            p = subprocess.run(["lzfse", "-decode"], input=im.payload, capture_output=True)
            if p.returncode != 0 or p.stdout[:4] != struct.pack("<I", MH_MAGIC_64):
                raise KCError("lzfse decode failed or did not yield a Mach-O")
            return p.stdout
        if kind == "lzss":
            raise KCError("legacy complzss kernelcache; not supported yet")
        raise KCError(f"unexpected IM4P payload kind: {kind}")
    raise KCError("not a Mach-O and not an IM4P")


# ---------------------------------------------------------------- Mach-O parsing

def _cstr(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("utf-8", "replace")


def _parse_prelink_info(macho: bytes) -> tuple[dict[str, Kext], str | None]:
    """Return (bundle_id -> partial Kext) from __PRELINK_INFO.__info, plus nothing else."""
    magic, cputype, cpusub, ftype, ncmds, sizeofcmds, flags, _ = struct.unpack_from("<IIIIIIII", macho, 0)
    off = 32
    plist_bytes = None
    for _ in range(ncmds):
        if off + 8 > len(macho):
            break
        cmd, cmdsize = struct.unpack_from("<II", macho, off)
        if cmdsize < 8 or off + cmdsize > len(macho):
            raise KCError("bad load command size")
        if cmd == LC_SEGMENT_64:
            segname = _cstr(macho[off + 8:off + 24])
            nsects = struct.unpack_from("<I", macho, off + 64)[0]
            if segname == "__PRELINK_INFO":
                so = off + 72
                for _s in range(nsects):
                    sectname = _cstr(macho[so:so + 16])
                    addr, size, offset = struct.unpack_from("<QQI", macho, so + 32)
                    if sectname == "__info" and size:
                        plist_bytes = macho[offset:offset + size].rstrip(b"\0")
                    so += 80
        off += cmdsize

    out: dict[str, Kext] = {}
    if not plist_bytes:
        return out, None
    try:
        info = plistlib.loads(plist_bytes)
    except Exception:
        return out, None
    entries = info.get("_PrelinkInfoDictionary", info) if isinstance(info, dict) else info
    if isinstance(entries, dict):
        entries = entries.get("_PrelinkInfoDictionary", [])
    for ent in entries if isinstance(entries, list) else []:
        if not isinstance(ent, dict):
            continue
        bid = ent.get("CFBundleIdentifier")
        if not bid:
            continue
        k = Kext(bid, version=ent.get("CFBundleVersion"))
        pers = ent.get("IOKitPersonalities", {})
        if isinstance(pers, dict):
            for pv in pers.values():
                if isinstance(pv, dict):
                    m = pv.get("IOProviderClass") or pv.get("IONameMatch") or pv.get("IONameMatched")
                    if isinstance(m, str) and m not in k.matches:
                        k.matches.append(m)
        out[bid] = k
    return out, None


def _parse_fileset_entries(macho: bytes) -> list[tuple[str, int]]:
    ncmds = struct.unpack_from("<I", macho, 16)[0]
    off = 32
    out = []
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from("<II", macho, off)
        if cmd == LC_FILESET_ENTRY:
            vmaddr, fileoff, entry_id_off = struct.unpack_from("<QQI", macho, off + 8)
            name = _cstr(macho[off + entry_id_off:off + cmdsize])
            out.append((name, vmaddr))
        off += cmdsize
    return out


def parse(data: bytes, source: str = "kernelcache") -> Kernelcache:
    macho = to_macho(data)
    if macho[:4] != struct.pack("<I", MH_MAGIC_64):
        raise KCError("not a 64-bit little-endian Mach-O")
    ftype = struct.unpack_from("<I", macho, 12)[0]

    prelink, _ = _parse_prelink_info(macho)
    kc = Kernelcache(source, ftype)

    merged: dict[str, Kext] = dict(prelink)
    for name, vmaddr in _parse_fileset_entries(macho):
        if name in merged:
            merged[name].vmaddr = vmaddr
        else:
            merged[name] = Kext(name, vmaddr=vmaddr)
    kc.kexts = sorted(merged.values(), key=lambda k: k.bundle_id)

    i = macho.find(b"Darwin Kernel Version")
    if i >= 0:
        kc.kernel_version = macho[i:i + 160].split(b"\0", 1)[0].split(b"\n", 1)[0].decode("ascii", "replace")
    return kc


def parse_file(path: str | Path) -> Kernelcache:
    p = Path(path)
    return parse(p.read_bytes(), p.name)


# ---------------------------------------------------------------- diff

@dataclass
class KextDiff:
    a: str
    b: str
    only_a: list[Kext]   # in A (e.g. iOS 15 / D11), missing in B (iOS 16 donor)
    only_b: list[Kext]
    common: list[str]

    def to_markdown(self, hardware_hint=None) -> str:
        out = [f"# Kext diff", f"- A: `{self.a}`", f"- B: `{self.b}`",
               f"- only in A (candidates to relink into B): {len(self.only_a)}",
               f"- only in B: {len(self.only_b)}", f"- common: {len(self.common)}", "",
               "## Only in A — missing from the iOS 16 donor"]
        for k in self.only_a:
            hit = ""
            if hardware_hint:
                for key in hardware_hint:
                    if key.lower() in k.bundle_id.lower():
                        hit = f"  <- HW:{key}"
            out.append(f"- `{k.bundle_id}` {k.version or ''} {('['+', '.join(k.matches)+']') if k.matches else ''}{hit}")
        out += ["", "## Only in B — new in iOS 16"]
        out += [f"- `{k.bundle_id}` {k.version or ''}" for k in self.only_b]
        return "\n".join(out) + "\n"


def diff(a: Kernelcache, b: Kernelcache) -> KextDiff:
    ma, mb = a.by_id(), b.by_id()
    only_a = sorted((ma[x] for x in ma.keys() - mb.keys()), key=lambda k: k.bundle_id)
    only_b = sorted((mb[x] for x in mb.keys() - ma.keys()), key=lambda k: k.bundle_id)
    return KextDiff(a.source, b.source, only_a, only_b, sorted(ma.keys() & mb.keys()))
