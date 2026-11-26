# Установка на Fedora: что качать

## 1. Пакеты из репозиториев Fedora

Сначала пусть утилита сама скажет, чего не хватает:

```bash
python3 -m halcyon doctor        # обязательные зависимости
python3 -m halcyon doctor --all  # + опциональные (прошивка RP2350, RPM)
```

Готовая команда для обязательного набора (её же печатает `doctor`):

```bash
sudo dnf install -y \
  git cmake clang lld pkgconf-pkg-config \
  libusb1-devel libplist-devel libimobiledevice-devel libirecovery-devel \
  libimobiledevice-utils libirecovery-utils usbmuxd \
  lzfse
```

Что за что отвечает:

| Пакет | Зачем |
|---|---|
| `libimobiledevice-utils`, `usbmuxd` | `halcyon device` в обычном режиме, бэкап |
| `libirecovery-utils` | `halcyon device` в Recovery/DFU |
| `lzfse` | распаковка kernelcache для `kernel kexts` / `kernel diff` и `compat` |
| `clang`, `lld`, `cmake` | инструменты сборки (патчеры ядра на EVT2) |
| `libplist-devel` и прочие `-devel` | заголовки на будущее для нативных частей |

Опционально:

```bash
# штатный откат на iOS 15 (Recovery Manager)
sudo dnf install -y idevicerestore
# прошивка диагностического адаптера RP2350
sudo dnf install -y arm-none-eabi-gcc-cs arm-none-eabi-newlib
# сборка RPM-пакета
sudo dnf install -y rpm-build pyproject-rpm-macros
```

`apfs-fuse` в репозиториях Fedora нет — если понадобится читать RootFS, собирается из исходников (это уже EVT2, пока не требуется).

## 2. Доступ к устройству без root

Поставь правило udev, чтобы DFU/Recovery и адаптер работали без `sudo`:

```bash
sudo install -m0644 packaging/60-halcyon-diag.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

Проверка: подключи iPhone и запусти `python3 -m halcyon device`.

## 3. Прошивки (IPSW) — качаешь сам

**В репозиторий их класть нельзя** (`.gitignore` блокирует `*.ipsw`). Это официальные образы Apple,
скачиваются с CDN Apple. Положи в `~/halcyon/ipsw/`. Для EVT1 нужны три:

| Роль | Устройство | Версия | Примечание |
|---|---|---|---|
| база | iPhone 7 Plus (`iPhone9,2`/`iPhone9,4`) | iOS 15.8.x | должна быть **подписанной**, если планируешь откат |
| донор SoC | iPad 7 (`iPad7,11`) | iPadOS 16.7.x | тот же процессор A10 |
| донор phone | iPhone 8 Plus (`iPhone10,2`) | iOS 16.7.x | «телефонный» userspace |

Прямые ссылки на CDN и список подписываемых версий удобно смотреть на ipsw.me и theAppleWiki
(ищи по модели). Качать можно обычным `curl`/`wget` по ссылке с `*.cdn-apple.com`.

> Доступность конкретных сборок 16.7.x для iPad 7 проверь по манифесту: скачай кандидата и
> запусти `halcyon ipsw <файл> -c`, убедись что есть identity для нужного board и компонент
> `KernelCache`.

## 4. Проверка, что всё готово к EVT1

```bash
cd ios16-d11

# целостность и состав образов
python3 -m halcyon ipsw ~/halcyon/ipsw/<base_15>.ipsw -c --verify

# карта совместимости компонентов 15 -> 16 (версии XNU, diff DeviceTree)
python3 -m halcyon compat ~/halcyon/ipsw/<base_15>.ipsw \
                          ~/halcyon/ipsw/<donor_ipad_16>.ipsw \
                          --donor-board j171ap -o docs/COMPAT_MAP.md

# инвентаризация ядра и что из драйверов D11 отсутствует в ядре 16
#   (сначала извлеки KernelCache из каждого IPSW — путь берётся из `ipsw -c`)
python3 -m halcyon kernel kexts <kernelcache_из_base_15>
python3 -m halcyon kernel diff  <kernelcache_base_15> <kernelcache_donor_16> -o docs/KEXT_MAP.md
```

`kernel diff` сам подсветит драйверы, совпадающие с матрицей `docs/HARDWARE.md` (например
`AppleMultitouchSPI <- HW:touch`) — это кандидаты на перенос (`kext-relink`, см.
`docs/ARCHITECTURE.md`).

Для извлечения конкретного KernelCache из IPSW можно использовать профиль сборки в dry-run,
он покажет внутренние пути, либо извлечь вручную по пути из `halcyon ipsw -c`.
