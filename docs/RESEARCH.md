# EVT1 — исследование прошивки

## Пары для сравнения
| Роль | Устройство | Board | Версия | Файл |
|---|---|---|---|---|
| База | iPhone9,2 / 9,4 | d11ap / d111ap | 15.8.8 (19H422) | `iPhone_5.5_P3_15.8.8_19H422_Restore.ipsw` |
| Донор | iPad7,12 | j172ap | 16.6.1 (20G81) | `iPad_10.2_16.6.1_20G81_Restore.ipsw` |
| Альт. донор | iPad7,6 | j72bap | 16.6.1 | — |

Проверено через `d11ctl fw list` 26.11.2026: в каталоге для iPad7,5/6/11/12 нет сборок 16.7.x. Ветка 16 для T8010 заканчивается на 16.6.1.

## Что сравниваем
| Компонент | Инструмент | Вопрос |
|---|---|---|
| KernelCache / XNU | `d11ctl compat --base-kc --donor-kc` | каких kext'ов iPhone нет в iPad-ядре |
| DeviceTree | `d11ctl compat --base-dt --donor-dt` | какие узлы периферии D11 надо внести в DT |
| SEP | `d11ctl sep` | версии sepOS, см. SEP.md |
| Baseband | `d11ctl sep` | BbChipID, наличие стека у донора |
| dyld shared cache | `ipsw dyld` (blacktop) | iPhone-only фреймворки |
| APFS | разбор rootfs DMG | SSV, раскладка томов |
| Питание | compat → подсистема `power` | PMU, charger, thermal |

Разбор kernelcache и DeviceTree требует blacktop/ipsw. Результаты складываются в `docs/compat/` только в виде текстовых отчётов: списки идентификаторов, без бинарников.
