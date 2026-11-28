# Исследование прошивки (план EVT1)

## Образы

| Роль | Устройство | Версия | Зачем |
|---|---|---|---|
| база | iPhone 7 Plus (D11/D111) | 15.8.x (подписана) | bootchain, SEP, Baseband, прошивки периферии, драйверы iPhone |
| донор SoC | iPad 7 (J171/J172), iPad 6 (J71b/J72b) | iPadOS 16.7.x | kernelcache и kext T8010 под iOS 16, DeviceTree того же SoC |
| донор phone | iPhone 8 Plus (D21/D211) | 16.7.x | userspace с идиомой телефона (SpringBoard, Telephony, Camera) |

Доступность конкретных сборок 16.7.x для iPad 6 и 7 проверить по манифестам (в `devices.py` отмечено `verify=True`).

## Что сравниваем и чем

| Объект | Инструмент Halcyon | Внешнее |
|---|---|---|
| BuildManifest / состав | `halcyon ipsw -c`, `halcyon compat` | — |
| KernelCache / XNU | `compat` (строка версии; для lzfse нужна утилита `lzfse`) | LLVM `llvm-objdump --macho`, свои инструменты EVT2 |
| DeviceTree | `devicetree.py`: diff узлов и `compatible` | — |
| kext | EVT2: разбор `__PRELINK_INFO` | — |
| dyld shared cache | EVT1: список образов | `dyld-shared-cache-extractor` (сборка под Linux) |
| APFS / RootFS | — | `apfs-fuse` (только чтение) |
| SEP | `halcyon sep` | — |
| Baseband | компонент `BasebandFirmware` в `compat` | — |
| Питание | DT `pmu`, `charger`, `aop` и kext PMU | — |

## Ключевые вопросы

1. Есть ли в kernelcache iPadOS 16 для J171 все драйверы, нужные D11? Чего не хватает и можно ли перелинковать это из 15 (как сделано в yigitzra1n)?
2. Подойдёт ли DeviceTree D11 из iOS 15 к ядру 16, или нужно слияние (merge) DT J171 + D11?
3. Чем отличаются протоколы SEP 15 ↔ 16 в AppleSEPManager (см. SEP.md)?
4. Можно ли собрать гибридную RootFS (userspace 16 от D21 + прошивки D11) и подписать trustcache?
