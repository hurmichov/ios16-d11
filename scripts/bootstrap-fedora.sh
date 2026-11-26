#!/usr/bin/env bash
# EVT0: подготовка Fedora к работе с d11ctl.
#   ./scripts/bootstrap-fedora.sh            — показать, что будет сделано
#   ./scripts/bootstrap-fedora.sh --execute  — установить
set -euo pipefail
cd "$(dirname "$0")/.."

EXEC=0; [[ "${1:-}" == "--execute" ]] && EXEC=1
run() { if ((EXEC)); then echo "+ $*"; "$@"; else echo "[dry-run] $*"; fi; }

. /etc/os-release
[[ "$ID" == "fedora" ]] || echo "⚠ это $PRETTY_NAME, а не Fedora — пакеты могут называться иначе"

PKGS=(python3 python3-pytest git clang llvm cmake ninja-build rpm-build rpmdevtools
      pyproject-rpm-macros python3-setuptools
      libusb1-devel libimobiledevice-utils libimobiledevice-devel usbmuxd
      libirecovery-utils libirecovery-devel idevicerestore libplist-utils libplist-devel
      arm-none-eabi-gcc-cs arm-none-eabi-gcc-cs-c++ arm-none-eabi-newlib)

run sudo dnf install -y "${PKGS[@]}"
run sudo systemctl enable --now usbmuxd.socket || true
run sudo cp firmware/rp2350/60-d11diag.rules /etc/udev/rules.d/
run sudo udevadm control --reload
run python3 -m pip install --user -e tool

cat <<'MSG'

Дополнительно вручную:
  • blacktop/ipsw (разбор kernelcache/DeviceTree): https://github.com/blacktop/ipsw/releases
  • pico-sdk >= 2.0 для прошивки RP2350: git clone -b 2.1.1 https://github.com/raspberrypi/pico-sdk
Проверка: d11ctl env check
MSG
