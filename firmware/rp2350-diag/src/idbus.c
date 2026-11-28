#include "idbus.h"
#include "sdq.h"

#include <stdio.h>
#include <string.h>

static int snprintf_hex(char *dst, uint8_t v, int idx);

/* ============================================================================
 * Accessory response table.
 *
 * The phone (bus master) issues short commands on the ID line; the accessory
 * answers with an identifying frame and, for a debug cable, a frame that tells
 * Tristar to mux the internal UART onto the Lightning data pins.
 *
 * The *structure* below is correct SDQ framing (payload + Maxim CRC-8, which this
 * firmware appends automatically). The *exact bytes* of the serial-enable command
 * are the reverse-engineered part. The public reference implementation is
 * stacksmashing's Tamarin Cable (RP2040 PIO). Fill VERIFIED values here after:
 *
 *   1) `!mode sniff` with a genuine DCSD cable (or any accessory) on the phone, OR
 *   2) copying the command/response constants from the Tamarin firmware source.
 *
 * Until then these are PLACEHOLDERS so the state machine compiles and the flow is
 * testable; they are NOT expected to actually flip a phone into serial mode.
 * ==========================================================================*/

/* Commands the master is known to send (first payload byte), for recognition. */
#define CMD_RESET      0x74   /* placeholder: observed-style interrogation opcode */
#define CMD_IDENTIFY   0x75   /* placeholder */
#define CMD_SET_STATE  0x70   /* placeholder: accessory power/pin state */

/* Frames we send back. CRC is appended by send_frame(); do not include it here. */
/* PLACEHOLDER identify payload — replace with a verified accessory ID. */
static const uint8_t RSP_IDENTIFY[] = { 0x01, 0x00, 0x00, 0x00 };
/* PLACEHOLDER "route UART to data pins" payload — the critical one to verify. */
static const uint8_t RSP_SERIAL[]   = { 0x01, 0x00, 0x02 };

static bool g_serial_engaged = false;

static void send_frame(const uint8_t *payload, int len) {
    uint8_t frame[32];
    if (len > (int)sizeof(frame) - 1) return;
    memcpy(frame, payload, len);
    frame[len] = sdq_crc8(payload, len);
    sdq_write_frame(frame, len + 1);
}

static void hexline(idbus_log_fn log, const char *tag, const uint8_t *b, int n, bool crc_ok) {
    char hex[3 * 24 + 1];
    int p = 0;
    for (int i = 0; i < n && p < (int)sizeof(hex) - 3; i++)
        p += snprintf_hex(hex + p, b[i], i);
    hex[p] = 0;
    log("# %s n=%d crc=%s %s\n", tag, n, crc_ok ? "ok" : "BAD", hex);
}

/* tiny helper so we don't pull in full printf formatting in the hot path */
static int snprintf_hex(char *dst, uint8_t v, int idx) {
    static const char H[] = "0123456789abcdef";
    int p = 0;
    if (idx) dst[p++] = ' ';
    dst[p++] = H[v >> 4];
    dst[p++] = H[v & 0xf];
    return p;
}

bool idbus_serial_engaged(void) { return g_serial_engaged; }
void idbus_dcsd_reset(void)     { g_serial_engaged = false; }

void idbus_sniff(idbus_log_fn log) {
    uint8_t buf[24];
    log("# sniff: watching ID line (passive, read-only)\n");
    for (;;) {
        int n = sdq_read_frame(buf, sizeof buf, 50000 /* 50 ms idle */);
        if (n > 0)
            hexline(log, "frame", buf, n, sdq_crc_ok(buf, n));
    }
}

/* One interrogation round: read a command frame, answer per the table. */
bool idbus_dcsd_step(idbus_log_fn log) {
    uint8_t buf[24];
    int n = sdq_read_frame(buf, sizeof buf, 100000 /* 100 ms */);
    if (n <= 0) return false;

    bool ok = sdq_crc_ok(buf, n);
    hexline(log, "rx", buf, n, ok);
    if (!ok) return false;

    switch (buf[0]) {
        case CMD_RESET:
        case CMD_IDENTIFY:
            send_frame(RSP_IDENTIFY, sizeof RSP_IDENTIFY);
            log("# tx identify\n");
            break;
        case CMD_SET_STATE:
            send_frame(RSP_SERIAL, sizeof RSP_SERIAL);
            log("# tx serial-enable (PLACEHOLDER — verify before trusting)\n");
            g_serial_engaged = true;   /* optimistic; confirmed by real UART traffic */
            return true;
        default:
            log("# rx unknown cmd 0x%02x\n", buf[0]);
            break;
    }
    return false;
}
