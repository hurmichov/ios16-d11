# SEP, Touch ID, Baseband — исследовательские направления

Статус: 🔬. Ничего не гарантируется, записи — гипотезы с указанием проверки.

## SEP
- SEP на A10 загружает sepOS, подписанную под конкретное устройство. На iPhone 7 Plus Apple подписывает только SEP из актуальной iOS 15.8.x.
- iOS 16 (донор) ожидает свою версию протокола SEP. Совместимость SEPOS 15 с userspace/ядром 16 **не подтверждена**.
- Известный подход сообщества для tethered-загрузок: старт без полноценного SEP. Последствия: нет keybag Data Protection, нет Touch ID, возможны проблемы с паролем и Keychain.

| # | Гипотеза | Как проверить | Статус |
|---|---|---|---|
| S1 | ядро 16 стартует с SEP 15 | boot log: нет `SEP_PANIC`, AppleSEPManager поднялся | ⬜ |
| S2 | AppleKeyStore работает с SEP 15 | userspace: `keybagd` без ошибок | ⬜ |
| S3 | Touch ID (Mesa) | kext AppleMesa из 15 vs 16, спаривание датчика с SEP | ⬜ |

## Touch ID
Датчик спарен с SEP конкретного устройства. Работа Touch ID возможна, только если работает SEP (S1+S2). Отдельно: наличие драйвера Mesa в iPad-ядре J172 (у iPad 7 есть Touch ID, так что драйвер есть — версия может отличаться).

## Baseband
- `d11ctl sep base.ipsw --donor-ipsw donor.ipsw` показывает BasebandFirmware и BbChipID.
- Модем iPhone 7 Plus зависит от модели (Qualcomm или Intel). Проверить по `ideviceinfo -k BasebandVersion` и BbChipID.
- Донор J172 (iPad 7 Cellular) содержит baseband-стек iOS 16, но для своего модема. Совпадение модемов — вопрос EVT1.
