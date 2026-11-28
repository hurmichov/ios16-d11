/*
 * Halcyon diagnostic adapter — firmware for Waveshare RP2350-USB-A.
 *
 * Modes (set over USB-CDC with `!mode <name>`):
 *   uart   (default) listen-only UART bridge: timestamps every line from the
 *                    target debug serial and forwards it to the host.
 *   sniff            passive IDBUS/SDQ sniffer on the Lightning ID line — decode
 *                    and print every accessory<->phone frame with CRC status.
 *   dcsd             act as a debug (DCSD-style) accessory: answer the phone's
 *                    ID-line interrogation so it exposes its factory UART, then
 *                    fall through to the uart bridge automatically.
 *
 * This selects the phone's OWN factory debug UART, like an Apple DCSD cable. It is
 * not an exploit: it does not touch code signing, SEP, or user data.
 *
 * Pins (through a mandatory 1.8V<->3.3V bidirectional level shifter):
 *   GPIO1  UART0 RX  (target debug TX)        GPIO0  UART0 TX (held hi-Z until `!tx on`)
 *   GPIO2  SDQ / ID line (open-drain)         GPIO26 ADC0 via 2:1 divider (level check)
 *
 * Control commands (lines starting with '!'):
 *   !ping  !stat  !mode uart|sniff|dcsd  !baud <n>  !adc  !tx on|off  !tmg [k=v]
 * Adapter messages start with '#'; target serial lines start with a timestamp.
 */
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>

#include "hardware/adc.h"
#include "hardware/gpio.h"
#include "hardware/irq.h"
#include "hardware/uart.h"
#include "pico/stdlib.h"

#include "idbus.h"
#include "sdq.h"

#ifndef HALCYON_DIAG_VERSION
#define HALCYON_DIAG_VERSION "dev"
#endif

#define TGT_UART uart0
#define TGT_TX_PIN 0
#define TGT_RX_PIN 1
#define SDQ_PIN 2
#define ADC_PIN 26
#define ADC_DIVIDER 2.0f
#define LED_PIN PICO_DEFAULT_LED_PIN

enum { MODE_UART, MODE_SNIFF, MODE_DCSD };
static volatile int mode = MODE_UART;

static uint32_t baud = 115200;
static bool tx_enabled = false;

#define RING_SIZE 8192
static volatile uint8_t ring[RING_SIZE];
static volatile uint32_t r_head, r_tail;
static volatile uint32_t stat_rx_bytes, stat_overflow, stat_uart_err;

/* printf-style logger passed to the IDBUS code (adapter lines start with '#'). */
static void ulog(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
    fflush(stdout);
}

/* ---------------- UART bridge ---------------- */
static void on_uart_rx(void) {
    while (uart_is_readable(TGT_UART)) {
        uint32_t dr = uart_get_hw(TGT_UART)->dr;
        if (dr & 0xF00) stat_uart_err++;
        uint32_t next = (r_head + 1) % RING_SIZE;
        if (next == r_tail) { stat_overflow++; continue; }
        ring[r_head] = (uint8_t)dr;
        r_head = next;
        stat_rx_bytes++;
    }
}

static void uart_setup(void) {
    uart_init(TGT_UART, baud);
    gpio_set_function(TGT_RX_PIN, GPIO_FUNC_UART);
    gpio_pull_up(TGT_RX_PIN);
    if (tx_enabled) gpio_set_function(TGT_TX_PIN, GPIO_FUNC_UART);
    else gpio_init(TGT_TX_PIN);
    uart_set_hw_flow(TGT_UART, false, false);
    uart_set_format(TGT_UART, 8, 1, UART_PARITY_NONE);
    uart_set_fifo_enabled(TGT_UART, true);
    irq_set_exclusive_handler(UART0_IRQ, on_uart_rx);
    irq_set_enabled(UART0_IRQ, true);
    uart_set_irq_enables(TGT_UART, true, false);
}

static void pump_uart(void) {
    static char line[512];
    static size_t n = 0;
    static bool at_start = true;
    while (r_tail != r_head) {
        uint8_t c = ring[r_tail];
        r_tail = (r_tail + 1) % RING_SIZE;
        if (at_start) { n = (size_t)snprintf(line, sizeof line, "%llu ",
                        (unsigned long long)time_us_64()); at_start = false; }
        if (c == '\r') continue;
        if (n < sizeof line - 2) line[n++] = (char)c;
        if (c == '\n' || n >= sizeof line - 2) {
            if (line[n - 1] != '\n') line[n++] = '\n';
            fwrite(line, 1, n, stdout);
            fflush(stdout);
            at_start = true;
            gpio_xor_mask(1u << LED_PIN);
        }
    }
}

/* ---------------- ADC level check ---------------- */
static float adc_volts(void) {
    adc_select_input(ADC_PIN - 26);
    uint32_t acc = 0;
    for (int i = 0; i < 64; i++) acc += adc_read();
    return (acc / 64.0f) * 3.3f / 4095.0f * ADC_DIVIDER;
}

/* ---------------- commands ---------------- */
static void set_mode(int m) {
    mode = m;
    if (m == MODE_DCSD) idbus_dcsd_reset();
    ulog("# mode %s\n", m == MODE_UART ? "uart" : m == MODE_SNIFF ? "sniff" : "dcsd");
}

static void handle_cmd(char *cmd) {
    if (!strcmp(cmd, "ping")) {
        ulog("# pong halcyon-diag " HALCYON_DIAG_VERSION "\n");
    } else if (!strcmp(cmd, "stat")) {
        ulog("# stat mode=%d baud=%lu rx=%lu overflow=%lu uart_err=%lu tx=%s serial=%d\n",
             mode, (unsigned long)baud, (unsigned long)stat_rx_bytes,
             (unsigned long)stat_overflow, (unsigned long)stat_uart_err,
             tx_enabled ? "on" : "off", idbus_serial_engaged());
    } else if (!strcmp(cmd, "mode uart"))  { set_mode(MODE_UART);
    } else if (!strcmp(cmd, "mode sniff")) { set_mode(MODE_SNIFF);
    } else if (!strcmp(cmd, "mode dcsd"))  { set_mode(MODE_DCSD);
    } else if (!strncmp(cmd, "baud ", 5)) {
        uint32_t b = strtoul(cmd + 5, NULL, 10);
        if (b >= 1200 && b <= 3000000) { baud = uart_set_baudrate(TGT_UART, b); ulog("# baud %lu\n", (unsigned long)baud); }
        else ulog("# err baud out of range\n");
    } else if (!strcmp(cmd, "adc")) {
        float v = adc_volts();
        const char *cls = v < 0.3f ? "low/absent" : v < 2.2f ? "1.8V-logic" : "3.3V-logic";
        ulog("# adc %.3f V (%s)\n", v, cls);
    } else if (!strcmp(cmd, "tx on"))  { tx_enabled = true;  gpio_set_function(TGT_TX_PIN, GPIO_FUNC_UART); ulog("# tx on (level shifter required)\n");
    } else if (!strcmp(cmd, "tx off")) { tx_enabled = false; gpio_init(TGT_TX_PIN); ulog("# tx off\n");
    } else if (!strncmp(cmd, "tmg", 3)) {
        char *eq = strchr(cmd, '=');
        if (eq) {
            uint32_t v = strtoul(eq + 1, NULL, 10);
            char *k = cmd + 4;
            if (!strncmp(k, "bit_cell", 8)) sdq_tmg.bit_cell = v;
            else if (!strncmp(k, "low_one", 7)) sdq_tmg.low_one = v;
            else if (!strncmp(k, "low_zero", 8)) sdq_tmg.low_zero = v;
            else if (!strncmp(k, "sample", 6)) sdq_tmg.sample = v;
            else if (!strncmp(k, "break_min", 9)) sdq_tmg.break_min = v;
            else if (!strncmp(k, "stop", 4)) sdq_tmg.stop = v;
            else { ulog("# err unknown tmg key\n"); return; }
        }
        ulog("# tmg bit_cell=%lu low_one=%lu low_zero=%lu sample=%lu break_min=%lu stop=%lu (ns)\n",
             (unsigned long)sdq_tmg.bit_cell, (unsigned long)sdq_tmg.low_one,
             (unsigned long)sdq_tmg.low_zero, (unsigned long)sdq_tmg.sample,
             (unsigned long)sdq_tmg.break_min, (unsigned long)sdq_tmg.stop);
    } else {
        ulog("# err unknown command '%s'\n", cmd);
    }
}

static void poll_host(void) {
    static char cmd[64];
    static size_t cn = 0;
    int ch = getchar_timeout_us(0);
    while (ch >= 0) {
        if (ch == '\n' || ch == '\r') {
            cmd[cn] = 0;
            if (cn >= 1 && cmd[0] == '!') handle_cmd(cmd + 1);
            cn = 0;
        } else if (cn < sizeof cmd - 1) {
            cmd[cn++] = (char)ch;
        }
        ch = getchar_timeout_us(0);
    }
}

int main(void) {
    stdio_init_all();
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    adc_init();
    adc_gpio_init(ADC_PIN);
    uart_setup();
    sdq_init(SDQ_PIN);

    absolute_time_t last_beat = get_absolute_time();

    for (;;) {
        poll_host();

        if (mode == MODE_SNIFF) {
            uint8_t buf[24];
            int n = sdq_read_frame(buf, sizeof buf, 20000);
            if (n > 0) {
                char hex[80]; int p = 0;
                for (int i = 0; i < n && p < (int)sizeof hex - 3; i++)
                    p += snprintf(hex + p, sizeof hex - p, i ? " %02x" : "%02x", buf[i]);
                ulog("# frame n=%d crc=%s %s\n", n, sdq_crc_ok(buf, n) ? "ok" : "BAD", hex);
            }
        } else if (mode == MODE_DCSD) {
            if (idbus_dcsd_step(ulog) && idbus_serial_engaged()) {
                ulog("# serial-enable sent; switching to uart bridge\n");
                set_mode(MODE_UART);
            }
        } else { /* MODE_UART */
            pump_uart();
        }

        if (absolute_time_diff_us(last_beat, get_absolute_time()) > 5000000) {
            last_beat = get_absolute_time();
            ulog("# beat mode=%d rx=%lu overflow=%lu\n", mode,
                 (unsigned long)stat_rx_bytes, (unsigned long)stat_overflow);
        }
    }
}
