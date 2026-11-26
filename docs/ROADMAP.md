# Дорожная карта

Каждый этап закрывается только после выполнения критериев выхода (Exit criteria).

> Подход: база yigitzra1n, хост macOS — см. [APPROACH.md](APPROACH.md).

## EVT0 — Environment ← текущий

- [x] структура репозитория, лицензия, `.gitignore`, который не пропускает файлы Apple
- [x] Halcyon: 10 модулей, CLI, логи, dry-run, проверка модели
- [x] `halcyon doctor`: платформенная проверка зависимостей (brew на macOS, dnf на Linux)
- [ ] настроен macOS-хост (Xcode CLT + Homebrew) — см. [MACOS_SETUP.md](MACOS_SETUP.md)
- [x] RPM spec и правила udev
- [x] прошивка RP2350: мост UART → USB-CDC с метками времени, измерение уровня сигнала через ADC
- [x] тесты на синтетических IPSW
- [ ] проверено на реальной Fedora и реальном iPhone 7 Plus (`halcyon device` в normal, recovery и DFU)
- [ ] прошивка RP2350 собрана и проверена на плате

**Exit:** `halcyon doctor` зелёный, `halcyon device` правильно определяет D11 во всех трёх режимах,
`make rpm` собирается.

## EVT1 — Firmware Research

- скачать: iOS 15.8.x для iPhone 7 Plus, iPadOS 16.7.x для iPad 7 (j171/j172), iOS 16.7.x для iPhone 8 Plus
- `halcyon compat` для пар (D11 15 ↔ J171 16) и (D11 15 ↔ D21 16), заполнить `docs/COMPAT_MAP.md`
- снять ioreg стоковой iOS 15 с устройства (`halcyon hw probe-script`) и подтвердить имена классов
- сравнить kext: какие драйверы D11 есть в kernelcache J171 16, каких нет (камеры, Taptic, Home, Mesa, Baseband)
- dyld shared cache: идиома phone и iPad, отсутствующие фреймворки (Telephony и др.)
- оценить вариант yigitzra1n: гибридная RootFS (донорская ОС + прошивки базы)

**Exit:** карта совместимости по каждому пункту HARDWARE.md с оценкой «есть / нужен порт / блокер».

## EVT2 — Build System (на macOS)

- `kernel-patch`, `kext-relink`, `dt-merge`, `trustcache`, `ramdisk`, `rootfs-assemble` (сейчас заглушки)
- инструменты C/C++: патчер Mach-O, линковщик kext (на базе LLVM libObject), сборщик trustcache
- **APFS/RootFS — нативными средствами macOS** (`asr`, `hdiutil`), img4 через `img4tool`.
  Это снимает прежний блокер «запись APFS под Linux»
- воспроизводимость: два запуска с одинаковым профилем дают одинаковый `build-manifest.json`

**Exit:** образ собирается целиком на macOS и описан build-manifest.json.

## EVT3 — Boot Validation

- tethered-загрузка через checkm8 (A10 подвержен уязвимости). Готовые инструменты подключаются
  как внешние и необязательные, Halcyon эксплойты не содержит
- первая цель: загрузка ядра iOS 16 до `BSD root` с RAM-диском
- `halcyon boot-monitor`: классификация каждого сбоя, база известных паник
- `halcyon panic`: разбор паник-логов с диска, когда живого лога нет

### Каналы диагностики без DCSD (стартуем так)

DCSD (serial по Lightning) — **рекомендуется, но не обязателен** для старта. Начинаем на том,
что доступно без спец-железа, и добавляем serial только при «тихом» зависании:

| Канал | Чем снять | Halcyon |
|---|---|---|
| консоль pongoOS по USB | загрузчик checkm8/pongoOS пишет в USB | `boot-monitor` (stdin/файл) |
| паник-логи на диске | restore-ramdisk / SSH, затем файл | `panic <file>` |
| verbose boot на экране | boot-arg `-v`, снять камерой | — (визуально) |
| serial по Lightning (DCSD) | адаптер RP2350 | `boot-monitor --serial` |

Единственный случай, где DCSD фактически незаменим: ранний зависон до поднятия USB-гаджета и
фреймбуфера, без записи паники. Все остальные шаги EVT3 от него не зависят.

Как выглядит такой первый бут — иллюстративный (синтетический) лог в
[`docs/samples/verbose-boot-example.log`](samples/verbose-boot-example.log):
`checkm8 → pongoOS → ядро 16 без SEP → дисплей поднялся → падение на root device`.
Прогнать: `halcyon boot-monitor --file docs/samples/verbose-boot-example.log -v`.

**Exit:** ядро стабильно доходит до launchd; каждый сбой классифицирован (через любой из каналов).

## EVT4 — Userspace

- launchd → SpringBoard, графика (AGX), сенсор, ввод
- без SEP (если иначе не получится, режим включается явно, см. SEP.md)

**Exit:** SpringBoard, работают касания, есть SSH.

## Alpha / Beta / Release

- **Alpha:** дисплей, сенсор, Wi-Fi, звук, зарядка, стабильная загрузка
- **Beta:** камеры, Taptic, BT, сон, управление питанием; стабильность (24 ч без паник)
- **Release:** документированная утилита, RPM, воспроизводимая сборка, честный список того, что работает
