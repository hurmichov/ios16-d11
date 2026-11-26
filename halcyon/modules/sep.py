"""SEP Compatibility: research helper, not a bypass.

Collects what can be learned *passively* from manifests: SEP firmware path/version per
identity, and whether target and donor SEP images are from the same SoC family. The
known state of the art (yigitzra1n on A9, iOS 16) is SEP-less boot with an unencrypted
Data volume; Halcyon treats that as a documented trade-off, not a default — see docs/SEP.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from halcyon.modules import img4
from halcyon.modules.firmware import IPSW


@dataclass
class SEPInfo:
    ipsw: str
    board: str
    path: str | None
    fourcc: str | None
    description: str | None
    encrypted: bool | None


def inspect(ipsw: IPSW, board: str) -> list[SEPInfo]:
    out = []
    for ident in ipsw.identities_for(board):
        path = ident.components.get("SEP")
        fourcc = desc = None
        enc = None
        if path and ipsw.has(path):
            try:
                im = img4.parse_im4p(ipsw.read(path))
                fourcc, desc, enc = im.fourcc, im.description, im.has_keybag
            except img4.DERError:
                pass
        out.append(SEPInfo(f"{ipsw.product_version} ({ipsw.build})", ident.board_config, path, fourcc, desc, enc))
    return out


FINDINGS = (
    "SEP firmware is signed per-device and personalised via TSS; an iOS 16 SEP for T8010 exists only "
    "in iPadOS 16 for A10 iPads, whose SEP is paired to different sensors (no Touch ID on the same bus layout).",
    "SEP ROM on A10 is not covered by checkm8 code execution in the SEP itself; loading an unsigned or "
    "mismatched sepOS is not expected to work.",
    "Practical options to evaluate: (a) iOS 15 SEP + iOS 16 kernel with AppleSEPManager compatibility shims; "
    "(b) SEP-less boot (no Touch ID / passcode / Data Protection) — documented, opt-in only.",
)
