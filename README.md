# ios16-d11 · Halcyon

Экспериментальный исследовательский порт **iOS 16** на **iPhone 7 Plus** (A10 Fusion, T8010,
`iPhone9,2` D11AP / `iPhone9,4` D111AP) и собственная утилита **Halcyon** для сборки,
диагностики и восстановления.

> **Подход:** на базе yigitzra1n, хост — **macOS** (нативный APFS, Apple-тулзы). Аналитика и
> диагностика Halcyon кросс-платформенны (работают и на Fedora). Решение и его обоснование —
> [docs/APPROACH.md](docs/APPROACH.md).

> Статус: **EVT0 — Environment.** Есть каркас утилиты, анализ прошивок и система сборки в режиме
> dry-run. Шаги, которые реально патчат образы, пока не реализованы: они явно падают, а не
> притворяются рабочими. Загружаемого образа iOS 16 пока нет.

## Быстрый старт (Fedora)

```bash
git clone https://github.com/hurmichov/ios16-d11 && cd ios16-d11
python3 -m halcyon doctor          # проверка зависимостей, печатает готовую команду dnf
sudo dnf install -y ...            # то, что попросил doctor
python3 -m halcyon device          # модель, режим (normal / recovery / DFU), ECID
python3 -m halcyon targets         # целевые устройства и доноры
```

Прошивки (IPSW) **не входят в репозиторий**. Скачай их сам с CDN Apple в `~/halcyon/ipsw/`.

```bash
halcyon ipsw  iPhone_5.5_P3_15.8.x_Restore.ipsw -c --verify     # BuildManifest + целостность
halcyon compat iPhone_5.5_P3_15.8.x_Restore.ipsw iPad_64bit_TouchID_ASTC_16.7.x_Restore.ipsw \
               --donor-board j171ap -o docs/COMPAT_MAP.md        # карта совместимости
halcyon kernel kexts kernelcache.release.iphone9              # список kext в ядре
halcyon kernel diff  kc_d11_15  kc_ipad7_16 -o docs/KEXT_MAP.md  # каких драйверов D11 нет в ядре 16
halcyon build profiles/d11-ios16.toml                            # план сборки (dry-run)
pongo_console_tool | halcyon boot-monitor                        # логи pongoOS по USB (без DCSD)
halcyon panic ~/panic-full.ips                                   # разбор паник-лога с диска
halcyon boot-monitor --serial /dev/halcyon-diag                  # логи загрузки по serial (DCSD, опционально)
halcyon backup ~/halcyon/backup --no-dry-run                     # резервная копия данных
halcyon restore iPhone_5.5_P3_15.8.x_Restore.ipsw                # штатный откат (dry-run)
```

Все команды, которые что-то записывают, по умолчанию работают в **dry-run**. Для реального
выполнения нужно передать и `--no-dry-run`, и `--i-understand`. Логи каждого запуска лежат в
`~/.local/share/halcyon/logs/<время>-<команда>/` (`halcyon.log` и `events.jsonl`).

## Структура

| Путь | Что там |
|---|---|
| `halcyon/` | утилита (Python 3.11+, без внешних зависимостей) |
| `halcyon/modules/` | 10 модулей из ТЗ, см. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| `profiles/` | профили сборки (TOML) |
| `firmware/rp2350-diag/` | прошивка диагностического адаптера на Waveshare RP2350-USB-A |
| `packaging/` | RPM spec и правила udev |
| `docs/` | исследования, дорожная карта, оборудование, безопасность |
| `tests/` | pytest на синтетических IPSW (без файлов Apple) |

Сборка: `make test`, `make rpm`, `make firmware` (нужен `PICO_SDK_PATH`).

## Документы

- [APPROACH](docs/APPROACH.md): почему база yigitzra1n и macOS-хост (решение)
- [MACOS_SETUP](docs/MACOS_SETUP.md): настройка основного macOS-хоста и какие IPSW качать
- [FEDORA_SETUP](docs/FEDORA_SETUP.md): Linux для аналитики/диагностики (подмножество EVT1)
- [ROADMAP](docs/ROADMAP.md): этапы EVT0 → Release и критерии выхода из каждого
- [HARDWARE](docs/HARDWARE.md): матрица оборудования и реалистичные ожидания
- [FIRMWARE_RESEARCH](docs/FIRMWARE_RESEARCH.md): план сравнения iOS 15 и 16, выбор доноров
- [SEP](docs/SEP.md): Secure Enclave, Touch ID, защита данных
- [RP2350_DIAG](docs/RP2350_DIAG.md): диагностический адаптер и вопрос совместимости с DCSD
- [SAFETY](docs/SAFETY.md): правила безопасности и восстановления
- [REFERENCES](docs/REFERENCES.md): yigitzra1n, turdus merula, лицензии

## Лицензия

MIT, см. [LICENSE](LICENSE). Репозиторий не содержит прошивок и бинарников Apple.
