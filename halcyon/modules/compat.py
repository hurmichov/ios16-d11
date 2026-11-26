"""Compatibility Analyzer: compare a target (iOS 15, D11) IPSW against an iOS/iPadOS 16 donor.

Produces a component map and, where possible, a DeviceTree node diff and XNU version strings.
The output is the input for docs/COMPAT_MAP.md and the Build Engine profile.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field

from halcyon.modules import devicetree, img4
from halcyon.modules.firmware import IPSW, KEY_COMPONENTS, Identity

XNU_RE = re.compile(rb"Darwin Kernel Version [^\0]{5,160}")


@dataclass
class ComponentRow:
    name: str
    target: str | None
    donor: str | None
    note: str = ""


@dataclass
class Report:
    target: str
    donor: str
    rows: list[ComponentRow] = field(default_factory=list)
    xnu_target: str | None = None
    xnu_donor: str | None = None
    dt_diff: devicetree.DTDiff | None = None
    warnings: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        out = [f"# Compatibility map\n", f"- target: `{self.target}`", f"- donor:  `{self.donor}`"]
        if self.xnu_target or self.xnu_donor:
            out += [f"- XNU target: `{self.xnu_target or 'n/a'}`", f"- XNU donor:  `{self.xnu_donor or 'n/a'}`"]
        out += ["", "| Component | Target (iOS 15) | Donor (16.x) | Note |", "|---|---|---|---|"]
        for r in self.rows:
            out.append(f"| {r.name} | {r.target or '—'} | {r.donor or '—'} | {r.note} |")
        if self.dt_diff:
            d = self.dt_diff
            out += ["", "## DeviceTree", f"- nodes only in target: {len(d.only_a)}",
                    f"- nodes only in donor: {len(d.only_b)}", f"- compatible changed: {len(d.compatible_changed)}", ""]
            for p in d.only_a[:200]:
                out.append(f"- `-` {p}")
            for p in d.only_b[:200]:
                out.append(f"- `+` {p}")
            for p, a, b in d.compatible_changed[:200]:
                out.append(f"- `~` {p}: {a} → {b}")
        if self.warnings:
            out += ["", "## Warnings"] + [f"- {w}" for w in self.warnings]
        return "\n".join(out) + "\n"


def _pick(ipsw: IPSW, board: str | None) -> Identity:
    ids = ipsw.identities_for(board) if board else ipsw.identities
    if not ids:
        raise ValueError(f"{ipsw.path.name}: no BuildIdentity for board {board!r}")
    # prefer the Erase identity: it carries the full component set
    return next((i for i in ids if i.is_erase), ids[0])


def _note(name: str, t: str | None, d: str | None) -> str:
    if name in ("SEP", "RestoreSEP"):
        return "SEP: research track (see docs/SEP.md)" if t and d else ""
    if name == "BasebandFirmware":
        return "baseband: research track; donor modem may differ" if d or t else ""
    if t and not d:
        return "missing in donor → keep target / port"
    if d and not t:
        return "new in 16 → needs driver/DT support"
    return ""


def _payload(ipsw: IPSW, path: str) -> bytes | None:
    try:
        im = img4.parse_im4p(ipsw.read(path))
    except (img4.DERError, KeyError):
        return None
    if im.payload_kind == "lzfse":
        if not shutil.which("lzfse"):
            return None
        p = subprocess.run(["lzfse", "-decode"], input=im.payload, capture_output=True)
        return p.stdout if p.returncode == 0 else None
    return im.payload


def xnu_version(ipsw: IPSW, ident: Identity) -> str | None:
    path = ident.components.get("KernelCache")
    if not path:
        return None
    data = _payload(ipsw, path)
    if not data:
        return None
    m = XNU_RE.search(data)
    return m.group(0).decode("ascii", "replace") if m else None


def analyze(target: IPSW, donor: IPSW, target_board: str = "d11ap", donor_board: str | None = None) -> Report:
    ti = _pick(target, target_board)
    di = _pick(donor, donor_board)
    rep = Report(f"{target.product_version} ({target.build}) {ti.board_config}",
                 f"{donor.product_version} ({donor.build}) {di.board_config}")
    names = list(KEY_COMPONENTS) + sorted((set(ti.components) | set(di.components)) - set(KEY_COMPONENTS))
    for n in names:
        t, d = ti.components.get(n), di.components.get(n)
        if t or d:
            rep.rows.append(ComponentRow(n, t, d, _note(n, t, d)))
    if ti.cpid and di.cpid and ti.cpid != di.cpid:
        rep.warnings.append(f"different SoC: target CPID {ti.cpid:#x}, donor CPID {di.cpid:#x} — "
                            "kernelcache/firmware from this donor will not boot as-is")
    rep.xnu_target = xnu_version(target, ti)
    rep.xnu_donor = xnu_version(donor, di)
    if rep.xnu_target is None or rep.xnu_donor is None:
        rep.warnings.append("XNU version not extracted (install `lzfse` for compressed kernelcaches)")
    tdt, ddt = ti.components.get("DeviceTree"), di.components.get("DeviceTree")
    if tdt and ddt:
        try:
            a, b = _payload(target, tdt), _payload(donor, ddt)
            if a and b:
                rep.dt_diff = devicetree.diff(devicetree.parse(a), devicetree.parse(b))
        except ValueError as e:
            rep.warnings.append(f"DeviceTree parse failed: {e}")
    return rep
