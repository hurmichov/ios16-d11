#pragma once
/*
 * Назначение пинов. ПРОВЕРИТЬ по схеме Waveshare RP2350-USB-A перед подключением.
 *
 * ВНИМАНИЕ: GPIO RP2350 работают на 3.3 В. Уровни отладочного UART на Lightning
 * у iPhone по открытым данным ниже (около 1.8 В) — подключать ТОЛЬКО через
 * двунаправленный преобразователь уровней и после замера мультиметром/осциллографом.
 * Прямое подключение может повредить Tristar/Hydra в iPhone.
 */
#define D11_UART          uart0
#define D11_UART_TX_PIN   0
#define D11_UART_RX_PIN   1
#define D11_UART_BAUD     115200

/* Линия ID (SDQ) Lightning — только мониторинг фронтов на EVT0.
 * Активное согласование SDQ (как в Tamarin Cable) — отдельная задача, см. docs/HARDWARE.md */
#define D11_SDQ_PIN       2

#define D11_LED_PIN       25
