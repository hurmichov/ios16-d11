#!/usr/bin/env bash
# Сборка прошивки адаптера: PICO_SDK_PATH=~/pico-sdk ./scripts/build-firmware.sh
set -euo pipefail
cd "$(dirname "$0")/../firmware/rp2350"
: "${PICO_SDK_PATH:?укажи PICO_SDK_PATH (pico-sdk >= 2.0)}"
cmake -S . -B build -G Ninja
cmake --build build
echo "Готово: firmware/rp2350/build/d11diag.uf2 — зажми BOOT, подключи плату, скопируй .uf2 на RP2350-диск"
