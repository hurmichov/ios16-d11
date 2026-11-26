"""SEP Compatibility: сведения о SEP и Baseband в образах, исследовательские заметки.

Сам по себе модуль ничего не прошивает: он сравнивает, какие SEP/BB-компоненты есть в
базе и доноре, и сохраняет это в отчёт, чтобы следить за гипотезами из docs/SEP.md.
"""

from __future__ import annotations

from pathlib import Path

from d11ctl.modules import firmware

SEP_KEYS = ("SEP", "RestoreSEP")
BB_KEYS = ("BasebandFirmware",)


def inspect(ipsw: Path, board: str) -> dict:
    m = firmware.read_manifest(ipsw)
    idents = firmware.identities(m, board)
    res = {"ipsw": ipsw.name, "version": m.get("ProductVersion"), "board": board, "variants": []}
    for ident in idents:
        man = ident.get("Manifest", {})
        res["variants"].append({
            "variant": ident["Info"].get("Variant"),
            "sep": {k: man[k]["Info"].get("Path") for k in SEP_KEYS if k in man},
            "baseband": {k: man[k]["Info"].get("Path") for k in BB_KEYS if k in man},
            "bb_chip_id": ident.get("BbChipID"),
            "sep_nonce_slot": "SepNonce" in str(ident.get("Info", {})),
        })
    return res


def compare(base: dict, donor: dict) -> list[str]:
    notes = []
    bv, dv = base["variants"], donor["variants"]
    if bv and dv:
        bsep = next(iter(bv[0]["sep"].values()), None)
        dsep = next(iter(dv[0]["sep"].values()), None)
        notes.append(f"SEP базы: {bsep}; SEP донора: {dsep}")
        if not any(v["baseband"] for v in dv):
            notes.append("у донора нет BasebandFirmware (Wi-Fi iPad) — стек связи брать неоткуда, "
                         "только из iOS 15 базы")
    notes.append("Гипотезы о совместимости SEPOS 15 с iOS 16 ведутся в docs/SEP.md")
    return notes
