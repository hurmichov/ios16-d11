"""Compatibility Analyzer: сравнение компонентов базы (iOS 15, D11) и донора (iPadOS 16, J171).

Главный вопрос EVT1: какие драйверы и узлы DeviceTree, которые есть у iPhone 7 Plus,
отсутствуют в iPad-ядре iOS 16 и требуют переноса или замены.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from d11ctl.core import log, runner

_log = log.get("compat")

_BUNDLE_RE = re.compile(r"\b(com\.apple\.[A-Za-z0-9_.\-]+)")

# Эвристика: ключевые слова в bundle id → аппаратная подсистема из ТЗ.
SUBSYSTEMS = [
    ("baseband", ("baseband", "AppleBasebandPCI", "Mav", "Qualcomm", "Intel")),
    ("touchid_sep", ("Mesa", "SEP", "Biometric", "SEPManager", "AppleKeyStore")),
    ("camera", ("Camera", "ISP", "H9", "H10")),
    ("taptic_home", ("Haptic", "Vibrator", "Taptic", "Button", "HID")),
    ("touch", ("Multitouch", "MT", "Zephyr", "Touch")),
    ("display", ("Display", "CLCD", "Backlight", "Panel", "DCP", "IOMobileFramebuffer")),
    ("gpu", ("AGX", "GPU", "IMG", "GFX")),
    ("audio", ("Audio", "Codec", "Speaker", "Mic", "Cirrus", "CS35", "CS42")),
    ("wifi_bt", ("WLAN", "BCM", "Bluetooth", "BT", "Wifi")),
    ("power", ("PMU", "Charger", "Battery", "Smart", "Power", "Thermal", "Tristar", "Hydra")),
]


def classify(bundle: str) -> str:
    tail = bundle.split(".", 2)[-1]
    for subsystem, keys in SUBSYSTEMS:
        if any(k.lower() in tail.lower() for k in keys):
            return subsystem
    return "other"


def parse_kext_list(text: str) -> set[str]:
    return set(_BUNDLE_RE.findall(text))


def kexts_from_kernelcache(path: Path) -> set[str]:
    """Список kext'ов через blacktop/ipsw (`ipsw kernel kexts`)."""
    res = runner.run(["ipsw", "kernel", "kexts", str(path)], timeout=600, check=True)
    return parse_kext_list(res.stdout + res.stderr)


def load_kexts(path: Path) -> set[str]:
    """Файл может быть kernelcache (разбирается через ipsw) или готовым списком/JSON."""
    if path.suffix in (".txt", ".json", ".lst"):
        return parse_kext_list(path.read_text())
    return kexts_from_kernelcache(path)


@dataclass
class KextDiff:
    only_base: dict[str, list[str]] = field(default_factory=dict)
    only_donor: dict[str, list[str]] = field(default_factory=dict)
    common: int = 0

    def as_dict(self) -> dict:
        return {"common": self.common, "only_base": self.only_base, "only_donor": self.only_donor}


def diff_kexts(base: set[str], donor: set[str]) -> KextDiff:
    d = KextDiff(common=len(base & donor))
    for b in sorted(base - donor):
        d.only_base.setdefault(classify(b), []).append(b)
    for b in sorted(donor - base):
        d.only_donor.setdefault(classify(b), []).append(b)
    return d


# --- DeviceTree -------------------------------------------------------------

def flatten_dt(node, prefix: str = "") -> dict[str, dict]:
    """Плоское представление дерева из `ipsw dtree --json`: путь → свойства."""
    out = {}
    if isinstance(node, dict):
        name = node.get("name") or node.get("Name")
        props = {k: v for k, v in node.items() if not isinstance(v, (dict, list))}
        here = f"{prefix}/{name}" if name else prefix or "/"
        out[here] = props
        for k, v in node.items():
            if isinstance(v, list):
                for child in v:
                    out.update(flatten_dt(child, here))
            elif isinstance(v, dict):
                out.update(flatten_dt(v, f"{here}/{k}" if not v.get("name") else here))
    return out


def load_dt(path: Path) -> dict[str, dict]:
    if path.suffix == ".json":
        return flatten_dt(json.loads(path.read_text()))
    res = runner.run(["ipsw", "dtree", "--json", str(path)], timeout=300, check=True)
    return flatten_dt(json.loads(res.stdout))


def diff_dt(base: dict[str, dict], donor: dict[str, dict]) -> dict:
    def compat(props):
        c = props.get("compatible")
        return c if isinstance(c, str) else json.dumps(c, default=str) if c else None

    return {
        "only_base": sorted(base.keys() - donor.keys()),
        "only_donor": sorted(donor.keys() - base.keys()),
        "compatible_changed": sorted(
            p for p in base.keys() & donor.keys() if compat(base[p]) != compat(donor[p])
        ),
    }


def render_markdown(kd: KextDiff | None, dt: dict | None, base_label: str, donor_label: str) -> str:
    lines = [f"# Карта совместимости: {base_label} → {donor_label}", ""]
    if kd:
        lines += [f"Общих kext'ов: **{kd.common}**", "",
                  "## Есть в базе (iPhone), нет в доноре — кандидаты на перенос", ""]
        for sub, items in sorted(kd.only_base.items()):
            lines.append(f"### {sub} ({len(items)})")
            lines += [f"- `{i}`" for i in items] + [""]
        lines += ["## Есть только в доноре (iPad)", ""]
        for sub, items in sorted(kd.only_donor.items()):
            lines.append(f"- **{sub}**: {len(items)}")
        lines.append("")
    if dt:
        lines += ["## DeviceTree", "",
                  f"- узлов только в базе: {len(dt['only_base'])}",
                  f"- узлов только в доноре: {len(dt['only_donor'])}",
                  f"- изменён `compatible`: {len(dt['compatible_changed'])}", ""]
        for p in dt["only_base"][:200]:
            lines.append(f"- `{p}`")
    lines.append("\n_Классификация по подсистемам эвристическая, проверять вручную._")
    return "\n".join(lines)
