/*
 * sdq.h — single-wire IDBUS / SDQ physical layer for Lightning accessory ID line.
 *
 * SDQ is the open-drain, pulled-high, LSB-first one-wire bus Apple uses on the
 * Lightning ID pin to interrogate accessories. It resembles Dallas 1-Wire but with
 * its own timing and an 8-bit Maxim/Dallas CRC (poly 0x31 reflected, i.e. 0x8C).
 *
 * This driver bit-bangs the line on a single GPIO and counts CPU cycles for timing,
 * so it must run with interrupts disabled on a dedicated core. All timings are named
 * constants in sdq.c and are meant to be tuned against a real capture (see sniffer).
 *
 * ELECTRICAL: the Lightning ID line is 1.8 V. The RP2350 is 3.3 V. A bidirectional
 * level shifter is mandatory. Never wire the ID pin directly.
 */
#ifndef HALCYON_SDQ_H
#define HALCYON_SDQ_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

/* Tunable line timing (nanoseconds). Defaults in sdq.c are public-reversing
 * starting points; adjust against a sniff capture via the firmware's `!tmg`. */
typedef struct {
    uint32_t bit_cell, low_one, low_zero, sample, break_min, stop;
} sdq_timing_t;
extern sdq_timing_t sdq_tmg;

void sdq_init(unsigned gpio);

/* Maxim/Dallas CRC-8 (poly 0x8C reflected), init 0x00 — used by IDBUS framing. */
uint8_t sdq_crc8(const uint8_t *data, size_t len);
bool sdq_crc_ok(const uint8_t *frame, size_t len); /* last byte is the CRC */

/* --- master-side (we drive the bus; used only for bench tests, not against a phone) --- */
void sdq_reset(void);
void sdq_write_byte(uint8_t b);
int sdq_read_byte(uint32_t timeout_us); /* -1 on timeout */

/* --- slave/monitor side (the phone is the master) --- */

/* Wait for the next bus event. Returns:
 *   SDQ_EV_BIT    one data bit read into *bit
 *   SDQ_EV_BREAK  a break/reset low pulse was seen (frame boundary)
 *   SDQ_EV_IDLE   line stayed high past timeout
 */
enum { SDQ_EV_BIT, SDQ_EV_BREAK, SDQ_EV_IDLE };
int sdq_wait_event(int *bit, uint32_t timeout_us);

/* Read a whole frame the master is sending (after a break). Fills buf up to max,
 * returns number of bytes, or -1 on framing error. Stops on the next break/idle. */
int sdq_read_frame(uint8_t *buf, int max, uint32_t idle_us);

/* Respond to the master by driving data bits at the moment it reads them.
 * Returns true if the whole frame was clocked out before the window closed. */
bool sdq_write_frame(const uint8_t *buf, int len);

/* line primitives (exposed for the responder's precise timing windows) */
void sdq_drive_low(void);
void sdq_release(void);
bool sdq_level(void);

#endif
