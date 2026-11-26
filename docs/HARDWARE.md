# Диагностический адаптер на RP2350 (d11diag)

Плата: **Waveshare RP2350-USB-A**. Прошивка: `firmware/rp2350`.

## Что делает прошивка (EVT0)
- USB-устройство к Fedora с двумя CDC-портами (VID:PID `1209:d110`, тестовый pid.codes):
  - `/dev/d11diag-uart` (CDC0) — прозрачный мост UART ⇄ ПК; скорость задаётся хостом;
  - `/dev/d11diag-events` (CDC1) — JSONL-события: `boot`, `hb` (раз в секунду, число фронтов на ID-линии), `baud`, счётчик потерь.
- ID-линия Lightning только **читается**: адаптер ничего не выставляет.

```bash
PICO_SDK_PATH=~/pico-sdk ./scripts/build-firmware.sh
sudo cp firmware/rp2350/60-d11diag.rules /etc/udev/rules.d/ && sudo udevadm control --reload
d11ctl boot monitor /dev/d11diag-uart
cat /dev/d11diag-events
```

## Чего не хватает до DCSD-совместимости
Сама плата Lightning не понимает. DCSD-кабель работает так: аксессуар по однопроводной шине **SDQ** на ID-пине Lightning сообщает чипу Tristar/Hydra в iPhone, что нужно вывести на пины отладочный UART. Без этого согласования UART на разъёме не появляется.

Нужно:
1. **Lightning-штекер-breakout** с выведенными ID0/ID1, L0/L1 и GND.
2. **Преобразователь уровней.** GPIO RP2350 работает на 3.3 В, уровни на Lightning ниже. До подключения замерить мультиметром или осциллографом.
3. **Реализация SDQ** на PIO RP2350. Открытый референс — *Tamarin Cable* (stacksmashing), сделан на RP2040 и умеет выводить UART и SWD через Lightning. Изучать как референс, учитывая его лицензию.

| Проверка | Статус |
|---|---|
| Сборка прошивки | ✅ |
| Энумерация на Fedora, два ttyACM | ⬜ (нужна плата) |
| Электрические уровни Lightning | ⬜ |
| Согласование SDQ, появление UART | ⬜ |
| **Совместимость с DCSD** | ⬜ подтверждается отдельно |
