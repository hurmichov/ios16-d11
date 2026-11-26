/*
 * Halcyon diagnostic adapter — firmware for Waveshare RP2350-USB-A.
 *
 * Role: a timestamping UART -> USB-CDC bridge with electrical self-checks.
 *   - UART0 RX on GPIO1 (TX on GPIO0 is disabled by default: listen-only, never drive the target)
 *   - ADC0 on GPIO26: measures the idle level of the target TX line through a divider,
 *     so you can confirm 1.8 V vs 3.3 V signalling BEFORE wiring the RX pin directly.
 *   - every received line goes to the host as:  "<us since boot> <text>\n"
 *   - control lines from host start with '!':  !ping  !stat  !baud <n>  !adc  !tx on|off
 *   - adapter's own messages start with '#', so the host can separate them from target logs.
 *
 * Electrical warning: Lightning debug UART (DCSD) is 1.8 V. RP2350 GPIO is 3.3 V.
 * Use a bidirectional level shifter (e.g. TXS0102/BSS138) and do NOT connect TX until
 * the protocol side is confirmed. See docs/RP2350_DIAG.md.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "hardware/adc.h"
#include "hardware/gpio.h"
#include "hardware/irq.h"
#include "hardware/uart.h"
#include "pico/stdlib.h"

#ifndef HALCYON_DIAG_VERSION
#define HALCYON_DIAG_VERSION "dev"
#endif

#define TGT_UART uart0
#define TGT_TX_PIN 0
#define TGT_RX_PIN 1
#define ADC_PIN 26
#define ADC_DIVIDER 2.0f /* 2:1 resistor divider in front of ADC0 */
#define LED_PIN PICO_DEFAULT_LED_PIN

#define RING_SIZE 8192
static volatile uint8_t ring[RING_SIZE];
static volatile uint32_t r_head, r_tail;
static volatile uint32_t stat_rx_bytes, stat_overflow, stat_uart_err;

static uint32_t baud = 115200;
static bool tx_enabled = false;

static void on_uart_rx(void) {
    while (uart_is_readable(TGT_UART)) {
        uint32_t dr = uart_get_hw(TGT_UART)->dr;
        if (dr & 0xF00) stat_uart_err++; /* framing / parity / break / overrun */
        uint32_t next = (r_head + 1) % RING_SIZE;
        if (next == r_tail) {
            stat_overflow++;
            continue;
        }
        ring[r_head] = (uint8_t)dr;
        r_head = next;
        stat_rx_bytes++;
    }
}

static void uart_setup(void) {
    uart_init(TGT_UART, baud);
    gpio_set_function(TGT_RX_PIN, GPIO_FUNC_UART);
    gpio_pull_up(TGT_RX_PIN); /* idle-high; weak, through the shifter */
    if (tx_enabled) gpio_set_function(TGT_TX_PIN, GPIO_FUNC_UART);
    else gpio_init(TGT_TX_PIN); /* plain input = high impedance */
    uart_set_hw_flow(TGT_UART, false, false);
    uart_set_format(TGT_UART, 8, 1, UART_PARITY_NONE);
    uart_set_fifo_enabled(TGT_UART, true);
    irq_set_exclusive_handler(UART0_IRQ, on_uart_rx);
    irq_set_enabled(UART0_IRQ, true);
    uart_set_irq_enables(TGT_UART, true, false);
}

static float adc_volts(void) {
    adc_select_input(ADC_PIN - 26);
    uint32_t acc = 0;
    for (int i = 0; i < 64; i++) acc += adc_read();
    return (acc / 64.0f) * 3.3f / 4095.0f * ADC_DIVIDER;
}

static void handle_cmd(char *cmd) {
    if (!strcmp(cmd, "ping")) {
        printf("# pong halcyon-diag " HALCYON_DIAG_VERSION "\n");
    } else if (!strcmp(cmd, "stat")) {
        printf("# stat baud=%lu rx=%lu overflow=%lu uart_err=%lu tx=%s\n", (unsigned long)baud,
               (unsigned long)stat_rx_bytes, (unsigned long)stat_overflow, (unsigned long)stat_uart_err,
               tx_enabled ? "on" : "off");
    } else if (!strncmp(cmd, "baud ", 5)) {
        uint32_t b = strtoul(cmd + 5, NULL, 10);
        if (b >= 1200 && b <= 3000000) {
            baud = uart_set_baudrate(TGT_UART, b);
            printf("# baud %lu\n", (unsigned long)baud);
        } else {
            printf("# err baud out of range\n");
        }
    } else if (!strcmp(cmd, "adc")) {
        float v = adc_volts();
        const char *cls = v < 0.3f ? "low/absent" : v < 2.2f ? "1.8V-logic" : "3.3V-logic";
        printf("# adc %.3f V (%s)\n", v, cls);
    } else if (!strcmp(cmd, "tx on")) {
        tx_enabled = true;
        gpio_set_function(TGT_TX_PIN, GPIO_FUNC_UART);
        printf("# tx on (make sure the level shifter is in place)\n");
    } else if (!strcmp(cmd, "tx off")) {
        tx_enabled = false;
        gpio_init(TGT_TX_PIN);
        printf("# tx off\n");
    } else {
        printf("# err unknown command '%s'\n", cmd);
    }
}

int main(void) {
    stdio_init_all();
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    adc_init();
    adc_gpio_init(ADC_PIN);
    uart_setup();

    char line[512];
    size_t n = 0;
    bool at_line_start = true;
    char cmd[64];
    size_t cn = 0;
    absolute_time_t last_beat = get_absolute_time();

    for (;;) {
        /* target -> host */
        while (r_tail != r_head) {
            uint8_t c = ring[r_tail];
            r_tail = (r_tail + 1) % RING_SIZE;
            if (at_line_start) {
                n = (size_t)snprintf(line, sizeof line, "%llu ", (unsigned long long)time_us_64());
                at_line_start = false;
            }
            if (c == '\r') continue;
            if (n < sizeof line - 2) line[n++] = (char)c;
            if (c == '\n' || n >= sizeof line - 2) {
                if (line[n - 1] != '\n') line[n++] = '\n';
                fwrite(line, 1, n, stdout);
                fflush(stdout);
                at_line_start = true;
                gpio_xor_mask(1u << LED_PIN);
            }
        }
        /* host -> adapter commands */
        int ch = getchar_timeout_us(0);
        if (ch >= 0) {
            if (ch == '\n' || ch == '\r') {
                cmd[cn] = 0;
                if (cn > 1 && cmd[0] == '!') handle_cmd(cmd + 1);
                cn = 0;
            } else if (cn < sizeof cmd - 1) {
                cmd[cn++] = (char)ch;
            }
        }
        /* heartbeat every 5 s so the host can tell "adapter alive, target silent" */
        if (absolute_time_diff_us(last_beat, get_absolute_time()) > 5000000) {
            last_beat = get_absolute_time();
            printf("# beat rx=%lu overflow=%lu\n", (unsigned long)stat_rx_bytes, (unsigned long)stat_overflow);
        }
    }
}
