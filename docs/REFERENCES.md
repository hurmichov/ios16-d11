# Референсы и лицензии

## yigitzra1n — https://github.com/yigitocak0-sys/yigitzra1n

Порт iOS/iPadOS 16.7.x на iPhone 6s (A9, N71m), лицензия MIT. Ниже его устройство по README (код не проверялся):

- вход: bash CLI `yigitzra1n.sh` с командами `prepare | install | boot | uninstall | ...`; хост только macOS
- три IPSW: база iPhone 6s 15.8.8, донор iPad 5 16.7.x, донор iPhone 8 16.7.x
- KernelCache: 23 патча; из 15 перелинкованы драйверы мультитача, аудио (CS35L19, CS42L71) и ARMPMU
- DeviceTree: исправления для сенсора, Wi-Fi, BT, камеры и аудио, флаги для работы без SEP
- RootFS: гибридная, плюс свои демоны (`sn2400_charger_daemon`, `sleepd_stub`, `soft_aks`)
- загрузка: checkm8, затем PongoOS, tethered
- не работает: SEP, Touch ID, код-пароль, мобильная связь
- **телеметрия включена по умолчанию**; в Halcyon её нет совсем

Что берём как идею: схема с тремя IPSW (база + донор SoC + донор phone), перелинковка kext из 15,
модульная структура скриптов, честная таблица совместимости.

Чем Halcyon отличается: нативная работа под Linux, профили вместо bash-флагов, dry-run и
проверка модели, без телеметрии, без автообновления при запуске.

## turdus merula

Референс для утилиты восстановления: работа с устройством в DFU, обработка IPSW, структура
пользовательского интерфейса. Halcyon не включает и не копирует его код. Если понадобится
что-то из него переиспользовать, сначала проверяем лицензию конкретного компонента.

## Прочее

- libimobiledevice, libirecovery, libplist, idevicerestore: LGPL-2.1. Halcyon вызывает их CLI, не линкуется
- Pico SDK: BSD-3-Clause
- Tamarin Cable (stacksmashing): референс эмуляции IDBUS, см. RP2350_DIAG.md
