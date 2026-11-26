# План работ

Статусы: ✅ готово · 🟡 в работе · ⬜ не начато · 🔬 исследование без гарантий

## EVT0 — Environment ✅
- ✅ структура проекта, `d11ctl` с 10 модулями ТЗ
- ✅ проверка зависимостей Fedora (`d11ctl env check`), установка через DNF
- ✅ dry-run по умолчанию, проверка модели перед записью, JSONL-журналы сессий
- ✅ RPM `.spec`, скрипты bootstrap/SRPM
- ✅ прошивка адаптера RP2350 (мост UART + канал событий) — собирается
- ✅ CI: тесты на Fedora, сборка прошивки

## EVT1 — Firmware Research 🟡
- ✅ донор определён: iPadOS 16.6.1 / J172 (16.7.x для T8010 не существует)
- ⬜ скачать 15.8.8 D11 и 16.6.1 J172, извлечь компоненты
- ⬜ `d11ctl compat` → карта kext'ов по подсистемам (docs/compat/)
- ⬜ сравнение DeviceTree D11 ↔ J172: какие узлы периферии iPhone отсутствуют
- ⬜ dyld shared cache: наличие фреймворков iPhone-only (Telephony, CoreTelephony UI, Camera)
- ⬜ APFS: формат томов, sealed system volume (SSV) в 16 против 15
- ⬜ SEP/Baseband: версии, BbChipID (см. SEP.md)
- ⬜ питание: PMU/charger kext'ы, узлы DT

## EVT2 — Build System ⬜
- рецепт: слияние DeviceTree, патчи kernelcache, сборка rootfs из донора
- build-lock.json с SHA-256 всех выходов, проверка воспроизводимости
- всё локально, артефакты не публикуются

## EVT3 — Boot Validation ⬜
- tethered-загрузка через checkm8 (gaster/ipwndfu-совместимый путь)
- `d11ctl boot monitor` через адаптер RP2350 или serial-лог
- классификация ошибок: iBoot → XNU → root → launchd

## EVT4 — Userspace ⬜
- запуск launchd, backboardd, SpringBoard; дисплей и тач в первую очередь

## Alpha / Beta / Release ⬜
- Alpha: загрузка до SpringBoard, дисплей, тач, Wi-Fi
- Beta: звук, камеры 🔬, Taptic/Home 🔬, Bluetooth, зарядка/сон
- Отдельно 🔬: Touch ID, SEP, Baseband/связь
- Release: документированная утилита, воспроизводимая сборка, таблица функций
