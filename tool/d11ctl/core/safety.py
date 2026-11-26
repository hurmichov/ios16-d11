"""Правила безопасности: dry-run по умолчанию, проверка модели, подтверждения.

Любая операция, которая пишет на устройство, обязана пройти через guard_write().
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from d11ctl.core import log
from d11ctl.core.config import TARGET_BOARDS, TARGET_CPID, TARGET_PRODUCTS, Paths

_log = log.get("safety")


class SafetyError(RuntimeError):
    pass


@dataclass
class Context:
    paths: Paths
    dry_run: bool = True
    assume_yes: bool = False
    extra: dict = field(default_factory=dict)


def verify_target(dev) -> None:
    """Бросает SafetyError, если подключено не iPhone 7 Plus."""
    problems = []
    if dev.cpid is not None and dev.cpid != TARGET_CPID:
        problems.append(f"CPID 0x{dev.cpid:04x} ≠ 0x{TARGET_CPID:04x} (A10)")
    if dev.product_type and dev.product_type not in TARGET_PRODUCTS:
        problems.append(f"ProductType {dev.product_type} не входит в {sorted(TARGET_PRODUCTS)}")
    if dev.board and dev.board.lower() not in TARGET_BOARDS:
        problems.append(f"BoardConfig {dev.board} не входит в {sorted(TARGET_BOARDS)}")
    if dev.product_type and dev.board:
        expected = TARGET_PRODUCTS.get(dev.product_type)
        if expected and expected != dev.board.lower():
            problems.append(f"{dev.product_type} должен иметь board {expected}, а не {dev.board}")
    if not (dev.product_type or dev.board):
        problems.append("модель устройства не удалось определить")
    if problems:
        raise SafetyError("устройство не прошло проверку модели: " + "; ".join(problems))


def confirm(ctx: Context, prompt: str) -> bool:
    if ctx.assume_yes:
        return True
    if not sys.stdin.isatty():
        _log.error("нужно подтверждение, но stdin не терминал; используй --yes осознанно")
        return False
    answer = input(f"{prompt}\nНапиши 'да' для продолжения: ").strip().lower()
    return answer in ("да", "yes")


def guard_write(ctx: Context, dev, action: str) -> bool:
    """True — можно выполнять реальную запись. False — dry-run или отказ."""
    verify_target(dev)
    _log.info("устройство прошло проверку: %s / %s", dev.product_type, dev.board)
    if ctx.dry_run:
        _log.warning("[dry-run] '%s' не будет выполнено. Для записи нужен --execute", action)
        return False
    if not confirm(ctx, f"ВНИМАНИЕ: '{action}' изменит устройство {dev.product_type} ECID={dev.ecid_hex}."):
        raise SafetyError("операция отменена пользователем")
    return True
