"""Firmware Manager: каталог прошивок, загрузка с проверкой целостности, разбор IPSW.

Образы скачиваются напрямую с серверов Apple (ссылки отдаёт api.ipsw.me) на машину
пользователя. В репозиторий ничего из этого не попадает.
"""

from __future__ import annotations

import hashlib
import json
import plistlib
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from d11ctl import __version__
from d11ctl.core import log

_log = log.get("firmware")
API = "https://api.ipsw.me/v4"
_UA = f"d11ctl/{__version__}"


@dataclass
class Firmware:
    identifier: str
    version: str
    build: str
    url: str
    signed: bool
    size: int | None = None
    sha1: str | None = None
    sha256: str | None = None

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def list_firmwares(identifier: str) -> list[Firmware]:
    data = _get_json(f"{API}/device/{identifier}?type=ipsw")
    out = []
    for f in data.get("firmwares", []):
        out.append(Firmware(
            identifier=identifier,
            version=f["version"],
            build=f["buildid"],
            url=f["url"],
            signed=bool(f.get("signed")),
            size=f.get("filesize"),
            sha1=f.get("sha1sum"),
            sha256=f.get("sha256sum"),
        ))
    return out


def find(identifier: str, version: str) -> Firmware:
    cands = [f for f in list_firmwares(identifier) if f.version == version or f.build == version]
    if not cands:
        raise LookupError(f"прошивка {version} для {identifier} не найдена")
    return cands[0]


def hash_file(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(path: Path, fw: Firmware) -> bool:
    if fw.sha256:
        algo, expected = "sha256", fw.sha256
    elif fw.sha1:
        algo, expected = "sha1", fw.sha1
    else:
        _log.warning("для %s нет эталонного хеша — целостность проверить нельзя", fw.filename)
        return False
    actual = hash_file(path, algo)
    ok = actual.lower() == expected.lower()
    (_log.info if ok else _log.error)("%s %s: %s", algo, path.name, "OK" if ok else f"НЕСОВПАДЕНИЕ ({actual})")
    return ok


def download(fw: Firmware, dest_dir: Path) -> Path:
    """Скачивает с докачкой и сверяет хеш. Повреждённый файл удаляется."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / fw.filename
    if dest.exists() and fw.size and dest.stat().st_size == fw.size and verify(dest, fw):
        _log.info("уже скачано: %s", dest)
        return dest

    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": _UA}
    if have:
        headers["Range"] = f"bytes={have}-"
        _log.info("докачка %s с %d МБ", fw.filename, have >> 20)
    req = urllib.request.Request(fw.url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r, part.open("ab" if have else "wb") as out:
        if have and r.status != 206:
            out.truncate(0)
            have = 0
        total = (fw.size or 0)
        done = have
        last = -1
        for chunk in iter(lambda: r.read(1 << 20), b""):
            out.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                if pct != last and pct % 5 == 0:
                    _log.info("%s: %d%%", fw.filename, pct)
                    last = pct
    part.rename(dest)
    if not verify(dest, fw):
        dest.unlink()
        raise IOError(f"{fw.filename}: хеш не совпал, файл удалён")
    return dest


# --- Разбор IPSW ---------------------------------------------------------------

@dataclass
class Component:
    name: str
    path: str
    personalize: bool


def read_manifest(ipsw: Path) -> dict:
    with zipfile.ZipFile(ipsw) as z:
        return plistlib.loads(z.read("BuildManifest.plist"))


def identities(manifest: dict, board: str | None = None) -> list[dict]:
    out = []
    for ident in manifest.get("BuildIdentities", []):
        info = ident.get("Info", {})
        if board and info.get("DeviceClass", "").lower() != board.lower():
            continue
        out.append(ident)
    return out


def components(identity: dict) -> list[Component]:
    out = []
    for name, entry in sorted(identity.get("Manifest", {}).items()):
        info = entry.get("Info", {})
        if "Path" in info:
            out.append(Component(name, info["Path"], bool(info.get("Personalize", False))))
    return out


def summary(ipsw: Path) -> dict:
    m = read_manifest(ipsw)
    res = {
        "file": ipsw.name,
        "version": m.get("ProductVersion"),
        "build": m.get("ProductBuildVersion"),
        "products": m.get("SupportedProductTypes", []),
        "identities": [],
    }
    for ident in m.get("BuildIdentities", []):
        info = ident.get("Info", {})
        res["identities"].append({
            "board": info.get("DeviceClass"),
            "variant": info.get("Variant"),
            "restore": info.get("RestoreBehavior"),
            "components": {c.name: c.path for c in components(ident)},
        })
    return res


def extract(ipsw: Path, board: str, names: list[str], out_dir: Path,
            variant_contains: str = "Erase") -> dict[str, Path]:
    """Извлекает компоненты (KernelCache, DeviceTree, SEP, ...) для заданной платы."""
    m = read_manifest(ipsw)
    idents = identities(m, board)
    if not idents:
        raise LookupError(f"в {ipsw.name} нет BuildIdentity для {board}")
    ident = next((i for i in idents if variant_contains in i["Info"].get("Variant", "")), idents[0])
    comp = {c.name: c for c in components(ident)}
    out_dir.mkdir(parents=True, exist_ok=True)
    got = {}
    with zipfile.ZipFile(ipsw) as z:
        for n in names:
            if n not in comp:
                _log.warning("компонент %s отсутствует для %s", n, board)
                continue
            dst = out_dir / Path(comp[n].path).name
            dst.write_bytes(z.read(comp[n].path))
            got[n] = dst
            _log.info("извлечён %s → %s", n, dst)
    return got
