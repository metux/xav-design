/* SPDX-License-Identifier: MIT */
#include <stdlib.h>
#include <string.h>
#include "internal.h"
_Static_assert(sizeof(xcb_ge_generic_event_t) == 36,
               "XCB GE event includes full_sequence after the 32-byte wire header");
static uint64_t get_u64(const uint8_t *p)
{
    uint64_t value;
    memcpy(&value, p, sizeof(value));
    return value;
}
static int zero_bytes(const uint8_t *p, size_t length)
{
    size_t i;
    for (i = 0; i < length; ++i) if (p[i] != 0) return 0;
    return 1;
}
static int expected_payload_words(uint16_t type, uint32_t *words)
{
    switch (type) {
    case XAVERIUS_EVENT_ASYNC_ERROR: *words = 7; return 1;
    case XAVERIUS_EVENT_DEVICE_LOST: *words = 4; return 1;
    case XAVERIUS_EVENT_DEVICE_STATUS_CHANGED: *words = 4; return 1;
    case XAVERIUS_EVENT_DEVICE_MEMORY_PRESSURE: *words = 4; return 1;
    case XAVERIUS_EVENT_DEVICE_IDLE: *words = 4; return 1;
    case XAVERIUS_EVENT_SUBMISSION_COMPLETE: *words = 6; return 1;
    case XAVERIUS_EVENT_SUBMISSION_FAILED: *words = 6; return 1;
    case XAVERIUS_EVENT_IMAGE_RELEASED: *words = 8; return 1;
    case XAVERIUS_EVENT_PRESENTATION_COMPLETE: *words = 8; return 1;
    default: return 0;
    }
}
xav_event_decode_result
xav_event_decode(const xav_connection *c, const xcb_generic_event_t *generic,
                 xav_event *out)
{
    const xcb_ge_generic_event_t *ge;
    const uint8_t *bytes, *payload;
    uint64_t payload_bytes;
    uint32_t expected_words;
    xav_event decoded;
    if (!c || !generic || !out) return XAV_EVENT_DECODE_ERROR;
    if ((generic->response_type & 0x7fU) != XCB_GE_GENERIC)
        return XAV_EVENT_DECODE_NOT_XAVERIUS;
    ge = (const xcb_ge_generic_event_t *)generic;
    if (ge->extension != c->major_opcode)
        return XAV_EVENT_DECODE_NOT_XAVERIUS;
    bytes = (const uint8_t *)generic;
    if (!zero_bytes(ge->pad0, sizeof(ge->pad0)))
        return XAV_EVENT_DECODE_ERROR;
    payload_bytes = (uint64_t)ge->length * UINT64_C(4);
    if (payload_bytes > (uint64_t)(SIZE_MAX - sizeof(*ge)))
        return XAV_EVENT_DECODE_ERROR;
    memset(&decoded, 0, sizeof(decoded));
    decoded.type = ge->event_type;
    decoded.sequence = ge->sequence;
    decoded.full_sequence = ge->full_sequence;
    if (!expected_payload_words(ge->event_type, &expected_words)) {
        decoded.unknown_payload = bytes + sizeof(*ge);
        decoded.unknown_payload_size = (size_t)payload_bytes;
        *out = decoded;
        return XAV_EVENT_DECODE_UNKNOWN;
    }
    if (ge->length != expected_words) return XAV_EVENT_DECODE_ERROR;
    /* XCB inserts full_sequence at byte 32; event payload starts at byte 36. */
    payload = bytes + sizeof(*ge);
#define U32(off) xav_get_u32(c, payload + (off))
    switch (ge->event_type) {
    case XAVERIUS_EVENT_ASYNC_ERROR:
        if (U32(24) != 0) return XAV_EVENT_DECODE_ERROR;
        decoded.data.async_error.device_xid = U32(0);
        decoded.data.async_error.error_code = U32(4);
        decoded.data.async_error.origin = U32(8);
        decoded.data.async_error.submission_token = get_u64(payload + 12);
        decoded.data.async_error.resource_xid = U32(20);
        break;
    case XAVERIUS_EVENT_DEVICE_LOST:
        decoded.data.device_lost.device_xid = U32(0);
        decoded.data.device_lost.reason_code = U32(4);
        decoded.data.device_lost.device_generation = get_u64(payload + 8);
        break;
    case XAVERIUS_EVENT_DEVICE_STATUS_CHANGED:
        if (U32(12) != 0) return XAV_EVENT_DECODE_ERROR;
        decoded.data.device_status_changed.physical_device_xid = U32(0);
        decoded.data.device_status_changed.new_status = U32(4);
        decoded.data.device_status_changed.reason_code = U32(8);
        break;
    case XAVERIUS_EVENT_DEVICE_MEMORY_PRESSURE:
        if (U32(12) != 0) return XAV_EVENT_DECODE_ERROR;
        decoded.data.device_memory_pressure.device_xid = U32(0);
        decoded.data.device_memory_pressure.heap_index = U32(4);
        decoded.data.device_memory_pressure.pressure_level = U32(8);
        break;
    case XAVERIUS_EVENT_DEVICE_IDLE:
        decoded.data.device_idle.device_xid = U32(0);
        decoded.data.device_idle.idle_reason = U32(4);
        decoded.data.device_idle.device_generation = get_u64(payload + 8);
        break;
    case XAVERIUS_EVENT_SUBMISSION_COMPLETE:
        if (U32(12) != 0) return XAV_EVENT_DECODE_ERROR;
        decoded.data.submission_complete.device_xid = U32(0);
        decoded.data.submission_complete.queue_family_index = U32(4);
        decoded.data.submission_complete.queue_index = U32(8);
        decoded.data.submission_complete.submission_token = get_u64(payload + 16);
        break;
    case XAVERIUS_EVENT_SUBMISSION_FAILED:
        decoded.data.submission_failed.device_xid = U32(0);
        decoded.data.submission_failed.queue_family_index = U32(4);
        decoded.data.submission_failed.queue_index = U32(8);
        decoded.data.submission_failed.failure_class = U32(12);
        decoded.data.submission_failed.submission_token = get_u64(payload + 16);
        break;
    case XAVERIUS_EVENT_IMAGE_RELEASED:
        if (U32(20) != 0) return XAV_EVENT_DECODE_ERROR;
        decoded.data.image_released.device_xid = U32(0);
        decoded.data.image_released.queue_family_index = U32(4);
        decoded.data.image_released.queue_index = U32(8);
        decoded.data.image_released.swapchain_xid = U32(12);
        decoded.data.image_released.image_index = U32(16);
        decoded.data.image_released.presentation_token = get_u64(payload + 24);
        break;
    case XAVERIUS_EVENT_PRESENTATION_COMPLETE:
        decoded.data.presentation_complete.device_xid = U32(0);
        decoded.data.presentation_complete.queue_family_index = U32(4);
        decoded.data.presentation_complete.queue_index = U32(8);
        decoded.data.presentation_complete.swapchain_xid = U32(12);
        decoded.data.presentation_complete.image_index = U32(16);
        decoded.data.presentation_complete.status = U32(20);
        decoded.data.presentation_complete.presentation_token = get_u64(payload + 24);
        break;
    default: return XAV_EVENT_DECODE_ERROR;
    }
#undef U32
    *out = decoded;
    return XAV_EVENT_DECODE_OK;
}
xav_client_status
xav_connection_select_events(xav_connection *c, xav_event_scope scope,
                             uint32_t device_xid, uint32_t queue_family_index,
                             uint32_t queue_index, uint32_t event_mask,
                             xcb_generic_error_t **error_out)
{
    static const xcb_protocol_request_t request = { 2, &xav_extension, 0, 1 };
    uint8_t body[28] = { XAVERIUS_REQ_SELECT_EVENTS, 0, 0, 0 };
    uint32_t fields[6];
    struct iovec parts[4];
    unsigned int sequence;
    xcb_void_cookie_t cookie;
    xcb_generic_error_t *error;
    if (!c) return XAV_CLIENT_ERROR_ARGUMENT;
    if (error_out) *error_out = NULL;
    if (!c->xge_negotiated) return XAV_CLIENT_ERROR_XGE_REQUIRED;
    if (xcb_connection_has_error(c->xcb)) return XAV_CLIENT_ERROR_CONNECTION;
    fields[0] = (uint32_t)scope;
    fields[1] = device_xid;
    fields[2] = queue_family_index;
    fields[3] = queue_index;
    fields[4] = event_mask;
    fields[5] = 0;
    memcpy(body + 4, fields, sizeof(fields));
    memset(parts, 0, sizeof(parts));
    parts[2].iov_base = body;
    parts[2].iov_len = sizeof(body);
    sequence = xcb_send_request(c->xcb, XCB_REQUEST_CHECKED, parts + 2, &request);
    if (!sequence) return XAV_CLIENT_ERROR_CONNECTION;
    cookie.sequence = sequence;
    error = xcb_request_check(c->xcb, cookie);
    if (error) {
        if (error_out) *error_out = error;
        else free(error);
        return XAV_CLIENT_ERROR_X11;
    }
    return xcb_connection_has_error(c->xcb) ?
        XAV_CLIENT_ERROR_CONNECTION : XAV_CLIENT_SUCCESS;
}
