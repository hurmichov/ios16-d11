"""Пути, константы целевой платформы и настройки по умолчанию."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# --- Целевая платформа -------------------------------------------------------

TARGET_CPID = 0x8010  # Apple A10 Fusion
TARGET_PRODUCTS = {
    "iPhone9,2": "d11ap",
    "iPhone9,4": "d111ap",
}
TARGET_BOARDS = set(TARGET_PRODUCTS.values())

# Доноры iOS 16 на том же T8010. Ветка 16 для T8010 закончилась на 16.6.1 (20G81):
# iPad 6 и iPad 7 перешли на iPadOS 17, 16.7.x для A10 не выпускалась.
# Cellular-варианты предпочтительнее — в их IPSW есть baseband-стек.
DONOR_PRODUCTS = {
    "iPad7,12": "j172ap",  # iPad 7 Cellular — основной донор
    "iPad7,11": "j171ap",  # iPad 7 Wi-Fi
    "iPad7,6": "j72bap",   # iPad 6 Cellular
    "iPad7,5": "j71bap",   # iPad 6 Wi-Fi
}

BASE_IOS = ("15.6.1", "15.8.8")
TARGET_VERSION = "16.6.1"  # 20G81, последняя iPadOS 16 для T8010


def _xdg(var: str, fallback: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / fallback)


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def cache(self) -> Path:  # скачанные IPSW
        return self.root / "cache"

    @property
    def work(self) -> Path:  # распакованные компоненты, промежуточные сборки
        return self.root / "work"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    def ensure(self) -> "Paths":
        for p in (self.cache, self.work, self.logs, self.backups):
            p.mkdir(parents=True, exist_ok=True)
        return self


def default_paths() -> Paths:
    override = os.environ.get("D11CTL_HOME")
    root = Path(override) if override else _xdg("XDG_DATA_HOME", ".local/share") / "d11ctl"
    return Paths(root)
