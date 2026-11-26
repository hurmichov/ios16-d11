# Архитектура Halcyon

Утилита состоит из независимых модулей. Каждый можно импортировать и тестировать отдельно.
Связь между ними идёт только через простые структуры данных (`DeviceState`, `IPSW`, `Report`,
`Session`). Глобального состояния нет.

```
           cli.py  (argparse, единый обработчик ошибок, Session на каждый запуск)
              │
 ┌────────────┼─────────────┬──────────────┬───────────────┬──────────────┐
 device.py  firmware.py  compat.py      build.py       bootmon.py    recovery.py
    │          │  img4.py    │ devicetree   │ profiles/     │ serial/file   │ idevicerestore
 transport.py  │             │              │               │               │ idevicebackup2
    │          └─────────────┴──────────────┘               │               │
 libimobiledevice / libirecovery CLI         safety.py ◄────┴───────────────┘
                                             logs.py (все модули)
```

| Модуль из ТЗ | Файл | Что умеет сейчас (EVT0) |
|---|---|---|
| Device Manager | `modules/device.py` | normal (lockdownd), recovery и DFU (irecovery). Сверяет CPID, BDID и ProductType с целями |
| USB Transport | `modules/transport.py` | обёртки над `idevice_id`, `ideviceinfo`, `irecovery`. Подменяемый runner для тестов |
| Firmware Manager | `modules/firmware.py`, `img4.py` | IPSW: BuildManifest, identities, пути компонентов, CRC, извлечение. Разбор DER IM4P |
| Compatibility Analyzer | `modules/compat.py`, `devicetree.py` | карта компонентов 15 → 16, версии XNU, diff узлов DeviceTree и `compatible` |
| Build Engine | `modules/build.py`, `profiles/*.toml` | конвейер по профилю, проверка SHA-256 входов, build-manifest.json. Шаги патчинга пока заглушки |
| Boot Monitor | `modules/bootmon.py` | потоковая классификация лога: этапы iboot → kernel → bsd → launchd → ui и типы сбоев |
| SEP Compatibility | `modules/sep.py` | пассивный разбор SEP-образов из манифестов, сводка ограничений |
| Hardware Diagnostics | `modules/hwdiag.py` | матрица компонентов, скрипт для проверки ioreg на устройстве, батарея через lockdownd |
| Log Manager | `modules/logs.py` | папка на каждый запуск: `halcyon.log` и `events.jsonl`, вложения (`compat.md`, `boot.log`) |
| Recovery Manager | `modules/recovery.py` | бэкап через idevicebackup2, восстановление подписанного iOS 15 через idevicerestore. Защита моделью и dry-run |

## Почему Python, а не C/C++

Оркестрация, разбор plist, DER и DeviceTree, сравнение и отчёты удобнее на Python. На Fedora он
есть из коробки и пакуется как noarch RPM. C/C++ (Clang и CMake) используем там, где без него
не обойтись: прошивка RP2350, будущие патчеры Mach-O и kext-линковщик (EVT2, `tools/` на
базе LLVM), код, который работает на самом устройстве (демоны и заглушки в RootFS, кросс-сборка
`clang -target arm64-apple-ios16.0`).

## Принципы

1. Без проприетарных бинарников. Всё, что приходит от Apple, извлекается на машине пользователя из его IPSW.
2. Сначала dry-run. Запись требует `--no-dry-run --i-understand` и проходит через `safety.py`.
3. Не притворяться. Шаг, который не реализован, падает с `StepNotImplemented`.
4. Воспроизводимость. Профиль, SHA-256 входов и `build-manifest.json` полностью описывают сборку.
