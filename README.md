# ios16-d11

Экспериментальный порт **iOS 16** на **iPhone 7 Plus** (iPhone9,2 / iPhone9,4 · D11AP / D111AP · Apple A10 Fusion, T8010) и Linux-утилита `d11ctl` для сборки, диагностики и восстановления.

> Это исследовательский проект. Загрузка порта **всегда tethered** (через checkm8 из DFU с ПК). Touch ID, SEP и связь — отдельные направления, работоспособность не гарантирована. Перед экспериментами прочитай [docs/SAFETY.md](docs/SAFETY.md).

## Ключевые факты

| | |
|---|---|
| Точка входа | checkm8 (BootROM T8010) — неисправляемая уязвимость, позволяет грузить неподписанную цепочку |
| База | iOS 15.8.8 (19H422, подписана) / 15.6.1 — периферия, DeviceTree, драйверы iPhone |
| Донор iOS 16 | **iPadOS 16.6.1 (20G81)** для iPad 7 Cellular (iPad7,12, J172AP, T8010) |
| Почему не 16.7.x | ни одно устройство на T8010 не получило 16.7.x: iPad 6/7 перешли на iPadOS 17 |
| Бонус | для T8010 существует iPadOS 17 — потенциальная следующая цель |

## Структура

```
tool/            d11ctl — Python 3, без внешних зависимостей
  d11ctl/core    конфигурация, журналирование, dry-run, проверки безопасности
  d11ctl/modules 10 модулей из ТЗ (см. ниже) + env
  recipes/       рецепты Build Engine
  tests/         pytest
firmware/rp2350  d11diag — прошивка диагностического адаптера (pico-sdk, TinyUSB)
packaging/rpm    d11ctl.spec
scripts/         bootstrap Fedora, сборка RPM и прошивки
docs/            план, исследование, безопасность, SEP, железо
```

| Модуль ТЗ | Файл | Команда |
|---|---|---|
| Device Manager | `modules/device.py` | `d11ctl device` |
| USB Transport | `modules/usb.py` | `d11ctl device usb` |
| Firmware Manager | `modules/firmware.py` | `d11ctl fw list/download/info/extract` |
| Build Engine | `modules/build.py` | `d11ctl build plan/run` |
| Compatibility Analyzer | `modules/compat.py` | `d11ctl compat` |
| Boot Monitor | `modules/bootmon.py` | `d11ctl boot monitor/analyze` |
| SEP Compatibility | `modules/sep.py` | `d11ctl sep` |
| Hardware Diagnostics | `modules/hwdiag.py` | `d11ctl diag` |
| Log Manager | `modules/logs.py`, `core/log.py` | `d11ctl logs` |
| Recovery Manager | `modules/recovery.py` | `d11ctl recovery backup/signed/restore` |

## Быстрый старт (Fedora)

```bash
./scripts/bootstrap-fedora.sh            # покажет, что поставит
./scripts/bootstrap-fedora.sh --execute  # поставит через dnf
d11ctl env check
d11ctl device                            # модель + проверка «это iPhone 7 Plus?»
d11ctl fw list iPhone9,2
d11ctl fw list iPad7,12
d11ctl --execute fw download iPhone9,2 15.8.8
d11ctl --execute fw download iPad7,12 16.6.1
d11ctl fw extract ~/.local/share/d11ctl/cache/<ipsw> d11ap KernelCache DeviceTree SEP
d11ctl compat --base-kc base/kernelcache... --donor-kc donor/kernelcache... --report compat.md
```

**По умолчанию всё работает в dry-run.** Изменения на устройстве и диске — только с `--execute`, после проверки модели и явного подтверждения.

Данные утилиты: `~/.local/share/d11ctl/{cache,work,logs,backups}` (переопределяется `D11CTL_HOME`).

## Этапы

См. [docs/ROADMAP.md](docs/ROADMAP.md). Текущий: **EVT0 — Environment** (готов), начат **EVT1**.

## Что не попадает в репозиторий

Никаких проприетарных бинарников Apple: IPSW, kernelcache, DeviceTree, SEP, baseband, dyld cache. Они скачиваются с серверов Apple на машине пользователя и патчатся локально; `.gitignore` блокирует типичные имена. В репозитории — только код, рецепты, патчи в виде описаний/скриптов и документация.

## Лицензия

GPL-3.0-or-later. Референсы (Turdus Merula и др.) изучаются архитектурно; их код не копируется.
