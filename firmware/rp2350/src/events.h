#pragma once
#include <stdint.h>

/* Канал событий (CDC1): строки JSON, по одной на событие.
 * {"t":123456,"ev":"uart_rx","n":64}
 */
void events_init(void);
void events_emit(const char *ev, const char *key, int32_t val);
void events_task(void);
