/*
 * idbus.h — IDBUS/SDQ accessory protocol state machine on top of sdq.c.
 *
 * Two useful roles for porting work:
 *
 *   SNIFF  — passively watch the ID line while a KNOWN accessory (a real DCSD cable,
 *            or any Lightning accessory) talks to the phone, and print every decoded
 *            frame + CRC status over USB. This is how you capture ground-truth bytes
 *            for your own iPhone 7 Plus (D11), rather than trusting guessed values.
 *
 *   DCSD   — act as the accessory: answer the phone's interrogation so Tristar routes
 *            the debug UART onto the Lightning data pins. The response table lives in
 *            idbus.c; the serial-enable payload is the part that MUST be verified from
 *            a sniff capture or the public Tamarin Cable source before it will work.
 *
 * Nothing here is an exploit: it only selects the phone's own factory debug UART,
 * exactly like an Apple DCSD cable. It does not touch code signing, SEP or user data.
 */
#ifndef HALCYON_IDBUS_H
#define HALCYON_IDBUS_H

#include <stdbool.h>
#include <stdint.h>

typedef void (*idbus_log_fn)(const char *fmt, ...);

void idbus_sniff(idbus_log_fn log);           /* never returns; prints frames */
bool idbus_dcsd_step(idbus_log_fn log);        /* one poll/response; true once serial engaged */
void idbus_dcsd_reset(void);

/* true once the phone has (apparently) switched the data pins to UART */
bool idbus_serial_engaged(void);

#endif
