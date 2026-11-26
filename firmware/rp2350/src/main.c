/*
 * d11diag — диагностический адаптер на RP2350 для d11ctl.
 *
 * USB (к Fedora):
 *   CDC0 /dev/ttyACM0 — прозрачный мост UART iPhone ⇄ ПК (лог iBoot/XNU) → `d11ctl boot monitor`
 *   CDC1 /dev/ttyACM1 — канал событий JSONL (статистика, фронты SDQ, heartbeat)
 */
#include "pico/stdlib.h"
#include "hardware/uart.h"
#include "hardware/gpio.h"
#include "tusb.h"

#include "board.h"
#include "events.h"

#define BRIDGE_ITF 0

static volatile uint32_t sdq_edges;

static void sdq_irq(uint gpio, uint32_t mask) {
    (void)gpio; (void)mask;
    sdq_edges++;
}

static void bridge_task(void) {
    static uint32_t rx_total;
    uint8_t buf[64];
    uint32_t n = 0;

    while (uart_is_readable(D11_UART) && n < sizeof buf)
        buf[n++] = (uint8_t)uart_getc(D11_UART);
    if (n) {
        rx_total += n;
        if (tud_cdc_n_connected(BRIDGE_ITF)) {
            tud_cdc_n_write(BRIDGE_ITF, buf, n);
            tud_cdc_n_write_flush(BRIDGE_ITF);
        }
    }
    /* ПК → iPhone (команды iBoot-консоли, если она доступна) */
    while (tud_cdc_n_available(BRIDGE_ITF)) {
        int c = tud_cdc_n_read_char(BRIDGE_ITF);
        if (c >= 0) uart_putc_raw(D11_UART, (char)c);
    }
    (void)rx_total;
}

/* Хост сменил скорость на CDC0 — повторяем её на физическом UART */
void tud_cdc_line_coding_cb(uint8_t itf, cdc_line_coding_t const *lc) {
    if (itf == BRIDGE_ITF) {
        uart_set_baudrate(D11_UART, lc->bit_rate);
        events_emit("baud", "v", (int32_t)lc->bit_rate);
    }
}

int main(void) {
    uart_init(D11_UART, D11_UART_BAUD);
    gpio_set_function(D11_UART_TX_PIN, GPIO_FUNC_UART);
    gpio_set_function(D11_UART_RX_PIN, GPIO_FUNC_UART);

    gpio_init(D11_SDQ_PIN);
    gpio_set_dir(D11_SDQ_PIN, GPIO_IN);  // только чтение: адаптер ничего не выставляет на ID-линию
    gpio_set_irq_enabled_with_callback(D11_SDQ_PIN, GPIO_IRQ_EDGE_FALL, true, sdq_irq);

    gpio_init(D11_LED_PIN);
    gpio_set_dir(D11_LED_PIN, GPIO_OUT);

    events_init();
    tusb_init();
    events_emit("boot", "fw", 1);

    absolute_time_t next_hb = make_timeout_time_ms(1000);
    while (true) {
        tud_task();
        bridge_task();
        if (time_reached(next_hb)) {
            uint32_t e = sdq_edges;
            sdq_edges = 0;
            events_emit("hb", "sdq_edges", (int32_t)e);
            gpio_xor_mask(1u << D11_LED_PIN);
            next_hb = make_timeout_time_ms(1000);
        }
        events_task();
    }
}
