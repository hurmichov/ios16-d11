# Безопасность и восстановление

| Требование ТЗ | Как выполнено |
|---|---|
| Резервное копирование | `halcyon backup <dir>` (idevicebackup2, полный бэкап). Обязателен перед любой записью |
| Проверка модели | `safety.require_target`: совпадают CPID 0x8010, BDID и ProductType D11/D111. Иначе отказ |
| Проверка соответствия IPSW | `safety.require_ipsw_matches`: SupportedProductTypes, наличие BuildIdentity, CRC всех файлов |
| Целостность образов | CRC zip, SHA-256 входов в профиле, SHA-256 каждого извлечённого компонента в `build-manifest.json` |
| Dry-run | включён по умолчанию; для записи нужно `--no-dry-run --i-understand` |
| Логи | на каждый запуск своя папка с `halcyon.log` и `events.jsonl` |
| Откат на iOS 15 | `halcyon restore <15.x.ipsw> [--erase]`: только подписанный стоковый restore через idevicerestore |
| Защита данных | без SEP работать можно только по явному выбору (SEP.md); ключи не извлекаем |
| Без бинарников Apple | `.gitignore` блокирует `*.ipsw`, `*.im4p`, `kernelcache*` и т.д.; тесты на синтетике |

## Процедура «всё сломалось»

1. Ввести устройство в DFU: Vol− + Side на 8 с, потом отпустить Side и держать Vol− ещё 5 с.
2. `halcyon device`: должен показать `mode: dfu`, `target: YES`.
3. `halcyon restore ~/halcyon/ipsw/<iOS 15.8.x>.ipsw --erase --no-dry-run --i-understand`
4. Восстановить данные: `idevicebackup2 restore ~/halcyon/backup`.

Пока Apple подписывает iOS 15.8.x для iPhone 7 Plus, этот путь всегда доступен. Состояние
подписи нужно проверять перед каждым экспериментом.
