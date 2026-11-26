#include "sdq.h"

#include "hardware/clocks.h"
#include "hardware/gpio.h"
#include "hardware/sync.h"
#include "pico/platform.h"

/* ---- timing (nanoseconds) --------------------------------------------------
 * Lightning SDQ bit cell is ~10 us. A bit is signalled by a low pulse at the
 * start of the cell: a short low = '1', a long low = '0' (write), and the
 * master samples ~2-3 us into the cell (read). A break is a much longer low.
 *
 * These are the commonly cited values from public Lightning reversing. They are
 * STARTING POINTS. Capture a real exchange with `!mode sniff` and tune them;
 * `!tmg` prints the current set and `!tmg k=v` adjusts one at runtime.
 *   bit_cell  total bit period        low_one  low time for '1'
 *   low_zero  low time for '0'        sample   sample offset from falling edge
 *   break_min low>=this is a break    stop     recovery high after a byte
 */
sdq_timing_t sdq_tmg = {
    .bit_cell  = 10000,
    .low_one   = 1200,
    .low_zero  = 7200,
    .sample    = 2600,
    .break_min = 12000,
    .stop      = 2000,
};

static unsigned PIN;
static uint32_t CYC_PER_US;

static inline void delay_ns(uint32_t ns) {
    /* cycles = ns * MHz / 1000; MHz == CYC_PER_US */
    busy_wait_at_least_cycles((uint32_t)(((uint64_t)ns * CYC_PER_US) / 1000u));
}

void sdq_drive_low(void) { gpio_set_dir(PIN, GPIO_OUT); gpio_put(PIN, 0); }
void sdq_release(void)   { gpio_set_dir(PIN, GPIO_IN); }
bool sdq_level(void)     { return gpio_get(PIN); }

void sdq_init(unsigned gpio) {
    PIN = gpio;
    CYC_PER_US = clock_get_hz(clk_sys) / 1000000u;
    gpio_init(PIN);
    gpio_pull_up(PIN);       /* weak; the external shifter/line sets the real idle */
    sdq_release();
}

/* ---- CRC-8 (Maxim/Dallas, reflected poly 0x8C, init 0x00) ------------------ */
uint8_t sdq_crc8(const uint8_t *data, size_t len) {
    uint8_t crc = 0;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int b = 0; b < 8; b++)
            crc = (crc & 1) ? (uint8_t)((crc >> 1) ^ 0x8C) : (uint8_t)(crc >> 1);
    }
    return crc;
}
bool sdq_crc_ok(const uint8_t *frame, size_t len) {
    return len >= 1 && sdq_crc8(frame, len - 1) == frame[len - 1];
}

/* ---- busy-wait edge helpers ------------------------------------------------ */
/* wait while level == want, up to timeout_ns; return ns actually waited, or -1. */
static int32_t wait_level(bool want, uint32_t timeout_ns) {
    uint32_t waited = 0, step = 100;
    while (sdq_level() == want) {
        if (waited >= timeout_ns) return -1;
        delay_ns(step);
        waited += step;
    }
    return (int32_t)waited;
}

/* ---- master side (bench only) --------------------------------------------- */
void sdq_reset(void) {
    sdq_drive_low();
    delay_ns(sdq_tmg.break_min + 2000);
    sdq_release();
    delay_ns(sdq_tmg.stop);
}

static void write_bit(int bit) {
    sdq_drive_low();
    delay_ns(bit ? sdq_tmg.low_one : sdq_tmg.low_zero);
    sdq_release();
    uint32_t rest = sdq_tmg.bit_cell - (bit ? sdq_tmg.low_one : sdq_tmg.low_zero);
    delay_ns(rest);
}

void sdq_write_byte(uint8_t b) {
    uint32_t save = save_and_disable_interrupts();
    for (int i = 0; i < 8; i++) { write_bit(b & 1); b >>= 1; }
    restore_interrupts(save);
}

int sdq_read_byte(uint32_t timeout_us) {
    uint32_t save = save_and_disable_interrupts();
    uint8_t v = 0;
    for (int i = 0; i < 8; i++) {
        if (wait_level(true, timeout_us * 1000) < 0) { restore_interrupts(save); return -1; }
        delay_ns(sdq_tmg.sample);
        if (sdq_level()) v |= (1u << i);
        wait_level(false, sdq_tmg.bit_cell * 2); /* ride out the rest of the low */
    }
    restore_interrupts(save);
    return v;
}

/* ---- slave / monitor side -------------------------------------------------- */
int sdq_wait_event(int *bit, uint32_t timeout_us) {
    /* wait for a falling edge (line goes low) */
    if (wait_level(true, timeout_us * 1000) < 0) return SDQ_EV_IDLE;
    /* measure the low pulse */
    int32_t low = wait_level(false, sdq_tmg.break_min * 2);
    if (low < 0 || (uint32_t)low >= sdq_tmg.break_min) return SDQ_EV_BREAK;
    /* classify by low duration: closer to low_one => 1, else 0 */
    uint32_t mid = (sdq_tmg.low_one + sdq_tmg.low_zero) / 2;
    *bit = ((uint32_t)low < mid) ? 1 : 0;
    return SDQ_EV_BIT;
}

int sdq_read_frame(uint8_t *buf, int max, uint32_t idle_us) {
    int nbytes = 0, nbits = 0, bit;
    uint8_t cur = 0;
    for (;;) {
        int ev = sdq_wait_event(&bit, idle_us);
        if (ev == SDQ_EV_IDLE) break;
        if (ev == SDQ_EV_BREAK) { if (nbytes || nbits) break; else continue; }
        cur |= (bit & 1) << nbits;
        if (++nbits == 8) {
            if (nbytes >= max) return -1;
            buf[nbytes++] = cur;
            cur = 0; nbits = 0;
        }
    }
    return (nbits == 0) ? nbytes : -1;
}

bool sdq_write_frame(const uint8_t *buf, int len) {
    uint32_t save = save_and_disable_interrupts();
    for (int i = 0; i < len; i++)
        for (int b = 0; b < 8; b++) write_bit((buf[i] >> b) & 1);
    restore_interrupts(save);
    return true;
}
