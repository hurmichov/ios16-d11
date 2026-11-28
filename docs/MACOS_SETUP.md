# Установка на macOS (основной хост)

Подход — на базе yigitzra1n (см. `docs/APPROACH.md`). Хост — macOS на Apple Silicon или Intel
(либо Хакинтош). Нужно ~40 ГБ свободного места под сборку образов.

## 1. Инструменты командной строки Xcode

```bash
xcode-select --install
```
Даёт clang, ld, git и базовый тулчейн. Полный Xcode не обязателен.

## 2. Homebrew и пакеты

Поставь Homebrew (https://brew.sh), затем пусть утилита сама скажет, чего не хватает:

```bash
python3 -m halcyon doctor        # обязательные
python3 -m halcyon doctor --all  # + опциональные
```

Готовый набор:

```bash
brew install cmake pkgconf libusb libplist libimobiledevice libirecovery zstd lzfse
# опционально (позже, для EVT3):
brew install idevicerestore                  # откат на сток iOS 15
brew install hudochenkov/sshpass/sshpass     # скриптовый SSH в ramdisk
brew install arm-none-eabi-gcc               # прошивка RP2350
```

`usbmuxd` в macOS встроен — отдельно ставить не нужно. APFS в macOS нативный, поэтому блокер
«сборка APFS под Linux» здесь отсутствует (используем `asr`/`hdiutil`).

IMG4 (раз)упаковка/подпись — через **pyimg4** (как у yigitzra1n), в venv проекта:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pyimg4
```

Homebrew-питон внешне управляется (PEP 668), поэтому ставить pip-пакеты только в venv.
Halcyon запускай из активированного venv (`python -m halcyon ...`).

## 3. Проверка

```bash
python3 -m halcyon doctor          # всё [ok]
python3 -m halcyon device          # с подключённым iPhone 7 Plus
python3 -m halcyon targets
python3 -m halcyon boot-monitor --file docs/samples/verbose-boot-example.log -v
```

## 4. Прошивки (IPSW) — качаешь сам

В репозиторий не кладутся. Положи в `~/halcyon/ipsw/`. Нужны три (см. `docs/FIRMWARE_RESEARCH.md`):
база iPhone 7 Plus iOS 15.8.x, донор iPad 7 iPadOS 16.7.x, донор iPhone 8 Plus iOS 16.7.x.

## 5. EVT1 на macOS

```bash
python3 -m halcyon ipsw ~/halcyon/ipsw/<base_15>.ipsw -c --verify
python3 -m halcyon compat ~/halcyon/ipsw/<base_15>.ipsw ~/halcyon/ipsw/<ipad7_16>.ipsw \
        --donor-board j171ap -o docs/COMPAT_MAP.md
python3 -m halcyon kernel diff <kc_15> <kc_16> -o docs/KEXT_MAP.md
```

> Linux (Fedora) тоже годится для всего EVT1 и диагностики — см. `docs/FEDORA_SETUP.md`.
> На macOS выполняется то, что требует нативного APFS и Apple-тулзов (EVT2+).
