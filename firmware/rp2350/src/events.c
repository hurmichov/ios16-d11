#include "events.h"

#include <stdio.h>
#include "pico/stdlib.h"
#include "tusb.h"

#define EV_ITF 1
#define RING 4096

static char ring[RING];
static volatile uint32_t head, tail;
static uint32_t dropped;

void events_init(void) { head = tail = dropped = 0; }

static void push(const char *s, int n) {
    for (int i = 0; i < n; i++) {
        uint32_t next = (head + 1) % RING;
        if (next == tail) { dropped++; return; }  // переполнение: событие теряется, но учитывается
        ring[head] = s[i];
        head = next;
    }
}

void events_emit(const char *ev, const char *key, int32_t val) {
    char line[128];
    int n = snprintf(line, sizeof line, "{\"t\":%llu,\"ev\":\"%s\"",
                     (unsigned long long)time_us_64(), ev);
    if (key) n += snprintf(line + n, sizeof line - n, ",\"%s\":%ld", key, (long)val);
    if (dropped) n += snprintf(line + n, sizeof line - n, ",\"dropped\":%lu", (unsigned long)dropped);
    n += snprintf(line + n, sizeof line - n, "}\n");
    dropped = 0;
    push(line, n);
}

void events_task(void) {
    if (!tud_cdc_n_connected(EV_ITF)) return;
    while (tail != head && tud_cdc_n_write_available(EV_ITF)) {
        uint32_t end = head > tail ? head : RING;
        uint32_t len = end - tail;
        uint32_t avail = tud_cdc_n_write_available(EV_ITF);
        if (len > avail) len = avail;
        tud_cdc_n_write(EV_ITF, ring + tail, len);
        tail = (tail + len) % RING;
    }
    tud_cdc_n_write_flush(EV_ITF);
}
