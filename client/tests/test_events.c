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
    uint8_t storage[sizeof(xcb_ge_generic_event_t) + 32];
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
    ge->pad0[0] = 0;

    /* Every registered event type has its own fixed payload layout. */
    memset(storage, 0, sizeof(storage));
    ge->response_type = XCB_GE_GENERIC;
    ge->extension = connection.major_opcode;
    ge->event_type = XAV_EVENT_DEVICE_LOST;
    ge->length = 4;
    put32(payload + 0, 0x101);
    put32(payload + 4, 5);
    put64(payload + 8, UINT64_C(0x0102030405060708));
    assert(xav_event_decode(&connection, (xcb_generic_event_t *)ge, &event) == XAV_EVENT_DECODE_OK);
    assert(event.data.device_lost.device_generation == UINT64_C(0x0102030405060708));

    memset(storage, 0, sizeof(storage));
    ge->response_type = XCB_GE_GENERIC; ge->extension = connection.major_opcode;
    ge->event_type = XAV_EVENT_DEVICE_STATUS_CHANGED; ge->length = 4;
    put32(payload + 0, 0x102); put32(payload + 4, 2); put32(payload + 8, 7);
    assert(xav_event_decode(&connection, (xcb_generic_event_t *)ge, &event) == XAV_EVENT_DECODE_OK);
    assert(event.data.device_status_changed.physical_device_xid == 0x102);

    memset(storage, 0, sizeof(storage));
    ge->response_type = XCB_GE_GENERIC; ge->extension = connection.major_opcode;
    ge->event_type = XAV_EVENT_DEVICE_MEMORY_PRESSURE; ge->length = 4;
    put32(payload + 0, 0x103); put32(payload + 4, 1); put32(payload + 8, 2);
    assert(xav_event_decode(&connection, (xcb_generic_event_t *)ge, &event) == XAV_EVENT_DECODE_OK);
    assert(event.data.device_memory_pressure.pressure_level == 2);

    memset(storage, 0, sizeof(storage));
    ge->response_type = XCB_GE_GENERIC; ge->extension = connection.major_opcode;
    ge->event_type = XAV_EVENT_DEVICE_IDLE; ge->length = 4;
    put32(payload + 0, 0x104); put32(payload + 4, 3);
    put64(payload + 8, UINT64_C(0x1112131415161718));
    assert(xav_event_decode(&connection, (xcb_generic_event_t *)ge, &event) == XAV_EVENT_DECODE_OK);
    assert(event.data.device_idle.device_generation == UINT64_C(0x1112131415161718));

    memset(storage, 0, sizeof(storage));
    ge->response_type = XCB_GE_GENERIC; ge->extension = connection.major_opcode;
    ge->event_type = XAV_EVENT_SUBMISSION_COMPLETE; ge->length = 6;
    put32(payload + 0, 0x105); put32(payload + 4, 2); put32(payload + 8, 1);
    put64(payload + 16, UINT64_C(0x2122232425262728));
    assert(xav_event_decode(&connection, (xcb_generic_event_t *)ge, &event) == XAV_EVENT_DECODE_OK);
    assert(event.data.submission_complete.submission_token == UINT64_C(0x2122232425262728));

    memset(storage, 0, sizeof(storage));
    ge->response_type = XCB_GE_GENERIC; ge->extension = connection.major_opcode;
    ge->event_type = XAV_EVENT_SUBMISSION_FAILED; ge->length = 6;
    put32(payload + 0, 0x106); put32(payload + 4, 2); put32(payload + 8, 1);
    put32(payload + 12, 1); put64(payload + 16, UINT64_C(0x3132333435363738));
    assert(xav_event_decode(&connection, (xcb_generic_event_t *)ge, &event) == XAV_EVENT_DECODE_OK);
    assert(event.data.submission_failed.failure_class == 1);

    memset(storage, 0, sizeof(storage));
    ge->response_type = XCB_GE_GENERIC; ge->extension = connection.major_opcode;
    ge->event_type = XAV_EVENT_IMAGE_RELEASED; ge->length = 8;
    put32(payload + 0, 0x107); put32(payload + 4, 2); put32(payload + 8, 1);
    put32(payload + 12, 0x300); put32(payload + 16, 4);
    put64(payload + 24, UINT64_C(0x4142434445464748));
    assert(xav_event_decode(&connection, (xcb_generic_event_t *)ge, &event) == XAV_EVENT_DECODE_OK);
    assert(event.data.image_released.presentation_token == UINT64_C(0x4142434445464748));

    memset(storage, 0, sizeof(storage));
    ge->response_type = XCB_GE_GENERIC; ge->extension = connection.major_opcode;
    ge->event_type = XAV_EVENT_PRESENTATION_COMPLETE; ge->length = 8;
    put32(payload + 0, 0x108); put32(payload + 4, 2); put32(payload + 8, 1);
    put32(payload + 12, 0x301); put32(payload + 16, 5); put32(payload + 20, 4);
    put64(payload + 24, UINT64_C(0x5152535455565758));
    assert(xav_event_decode(&connection, (xcb_generic_event_t *)ge, &event) == XAV_EVENT_DECODE_OK);
    assert(event.data.presentation_complete.status == 4);
    assert(event.data.presentation_complete.presentation_token == UINT64_C(0x5152535455565758));

    puts("XGE event decoder tests: PASS");
    return 0;
}
