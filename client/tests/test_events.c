/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../src/internal.h"
static void put32(uint8_t *p, uint32_t v) { memcpy(p, &v, sizeof(v)); }
static void put64(uint8_t *p, uint64_t v) { memcpy(p, &v, sizeof(v)); }
int main(void)
{
    struct xav_connection connection;
    uint8_t storage[sizeof(xcb_ge_generic_event_t) + 28];
    xcb_ge_generic_event_t *ge = (xcb_ge_generic_event_t *)storage;
    uint8_t *payload = storage + sizeof(*ge);
    xav_event event;
    memset(&connection, 0, sizeof(connection));
    connection.major_opcode = 0x91;
    memset(storage, 0, sizeof(storage));
    ge->response_type = XCB_GE_GENERIC;
    ge->extension = connection.major_opcode;
    ge->sequence = 0x1234;
    ge->length = 7;
    ge->event_type = XAV_EVENT_ASYNC_ERROR;
    ge->full_sequence = 0x12345678;
    put32(payload + 0, 0x100);
    put32(payload + 4, 3);
    put32(payload + 8, 1);
    put64(payload + 12, UINT64_C(0x1122334455667788));
    put32(payload + 20, 0x200);
    assert(xav_event_decode(&connection, (xcb_generic_event_t *)ge, &event) == XAV_EVENT_DECODE_OK);
    assert(event.type == XAV_EVENT_ASYNC_ERROR);
    assert(event.sequence == 0x1234);
    assert(event.full_sequence == 0x12345678);
    assert(event.data.async_error.device_xid == 0x100);
    assert(event.data.async_error.error_code == 3);
    assert(event.data.async_error.origin == 1);
    assert(event.data.async_error.submission_token == UINT64_C(0x1122334455667788));
    assert(event.data.async_error.resource_xid == 0x200);
    ge->extension++;
    assert(xav_event_decode(&connection, (xcb_generic_event_t *)ge, &event) == XAV_EVENT_DECODE_NOT_XAVERIUS);
    ge->extension = connection.major_opcode;
    ge->event_type = 99;
    ge->length = 1;
    assert(xav_event_decode(&connection, (xcb_generic_event_t *)ge, &event) == XAV_EVENT_DECODE_UNKNOWN);
    assert(event.type == 99 && event.unknown_payload == payload && event.unknown_payload_size == 4);
    ge->event_type = XAV_EVENT_ASYNC_ERROR;
    ge->length = 6;
    assert(xav_event_decode(&connection, (xcb_generic_event_t *)ge, &event) == XAV_EVENT_DECODE_ERROR);
    ge->length = 7;
    put32(payload + 24, 1);
    assert(xav_event_decode(&connection, (xcb_generic_event_t *)ge, &event) == XAV_EVENT_DECODE_ERROR);
    put32(payload + 24, 0);
    ge->pad0[0] = 1;
    assert(xav_event_decode(&connection, (xcb_generic_event_t *)ge, &event) == XAV_EVENT_DECODE_ERROR);
    puts("XGE event decoder tests: PASS");
    return 0;
}
