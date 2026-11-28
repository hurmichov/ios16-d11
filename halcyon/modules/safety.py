"""Safety guards shared by every module that can write to a device or to disk images."""

from __future__ import annotations

from dataclasses import dataclass

from halcyon.modules.device import DeviceState
from halcyon.modules.firmware import IPSW


class SafetyError(RuntimeError):
    pass


@dataclass
class Guard:
    dry_run: bool = True
    confirmed: bool = False  # set by --i-understand

    def require_write(self, what: str) -> bool:
        """Return True if the write may proceed. Dry-run returns False without raising."""
        if self.dry_run:
            return False
        if not self.confirmed:
            raise SafetyError(f"refusing to {what}: pass --i-understand together with --no-dry-run")
        return True


def require_target(state: DeviceState) -> None:
    if state.mode == "none":
        raise SafetyError("no device connected")
    if not state.is_target:
        raise SafetyError(
            f"connected device is not a supported target (ProductType={state.product_type}, "
            f"CPID={state.cpid and hex(state.cpid)}, BDID={state.bdid and hex(state.bdid)})")


def require_ipsw_matches(state: DeviceState, ipsw: IPSW) -> None:
    spec = state.spec
    if spec is None:
        raise SafetyError("unknown device")
    if spec.product_type not in ipsw.supported:
        raise SafetyError(f"{ipsw.path.name} does not list {spec.product_type} in SupportedProductTypes")
    if not ipsw.identities_for(spec.board_config):
        raise SafetyError(f"{ipsw.path.name} has no BuildIdentity for {spec.board_config}")
    bad = ipsw.verify_zip()
    if bad:
        raise SafetyError(f"IPSW integrity check failed: {bad}")
