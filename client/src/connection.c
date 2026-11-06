/* SPDX-License-Identifier: MIT */
#include <stdlib.h>
#include <string.h>
#include "internal.h"

xcb_extension_t xav_extension = { "XAVERIUS", 0 };

uint16_t xav_get_u16(const struct xav_connection *c, const uint8_t *p)
{
    uint16_t value;
    (void)c;
    memcpy(&value, p, sizeof(value));
    return value;
}
uint32_t xav_get_u32(const struct xav_connection *c, const uint8_t *p)
{
    uint32_t value;
    (void)c;
    memcpy(&value, p, sizeof(value));
    return value;
}
int xav_reply_envelope_valid(const struct xav_connection *c,
                             const xcb_generic_reply_t *reply, size_t *total)
{
    (void)c;
    uint64_t bytes;
    if (!reply || !total)
        return 0;
    bytes = UINT64_C(32) + (uint64_t)reply->length * UINT64_C(4);
    if (bytes > (uint64_t)SIZE_MAX)
        return 0;
    *total = (size_t)bytes;
    return 1;
}
xav_client_status xav_send_reply_request(struct xav_connection *c, uint8_t sub,
                                          xcb_generic_reply_t **reply,
                                          xcb_generic_error_t **error_out)
{
    /* XAverius uses X11 data=0; its subopcode is body byte zero at offset 4. */
    static const xcb_protocol_request_t req = { 2, &xav_extension, 0, 0 };
    uint8_t body[4] = { sub, 0, 0, 0 };
    struct iovec parts[4];
    unsigned int sequence;
    xcb_generic_error_t *local_error = NULL;
    if (!c || !reply) return XAV_CLIENT_ERROR_ARGUMENT;
    *reply = NULL;
    if (error_out) *error_out = NULL;
    memset(parts, 0, sizeof(parts));
    parts[2].iov_base = body;
    parts[2].iov_len = sizeof(body);
    sequence = xcb_send_request(c->xcb, 0, parts + 2, &req);
    if (!sequence) return XAV_CLIENT_ERROR_CONNECTION;
    *reply = xcb_wait_for_reply(c->xcb, sequence, &local_error);
    if (local_error) {
        if (error_out)
            *error_out = local_error;
        else
            free(local_error);
        return XAV_CLIENT_ERROR_X11;
    }
    return *reply ? XAV_CLIENT_SUCCESS : XAV_CLIENT_ERROR_CONNECTION;
}
xav_client_status xav_connection_create(xcb_connection_t *xcb, xav_connection **out,
                                         xav_version *version,
                                         xcb_generic_error_t **error_out)
{
    const xcb_query_extension_reply_t *ext;
    xav_connection *c;
    xcb_generic_reply_t *reply = NULL;
    xav_client_status status;
    size_t total;
    if (!xcb || !out) return XAV_CLIENT_ERROR_ARGUMENT;
    *out = NULL;
    if (version) memset(version, 0, sizeof(*version));
    if (error_out) *error_out = NULL;
    if (xcb_connection_has_error(xcb)) return XAV_CLIENT_ERROR_CONNECTION;
    ext = xcb_get_extension_data(xcb, &xav_extension);
    if (!ext || !ext->present) return XAV_CLIENT_ERROR_EXTENSION_MISSING;
    c = calloc(1, sizeof(*c));
    if (!c) return XAV_CLIENT_ERROR_NO_MEMORY;
    c->xcb = xcb;
    c->extension = ext;
    c->major_opcode = ext->major_opcode;
    status = xav_send_reply_request(c, XAVERIUS_REQ_QUERY_VERSION, &reply, error_out);
    if (status != XAV_CLIENT_SUCCESS) { free(c); return status; }
    if (!xav_reply_envelope_valid(c, reply, &total) || total != 32 ||
        reply->response_type != 1 || xav_get_u32(c, (uint8_t *)reply + 4) != 0) {
        free(reply); free(c); return XAV_CLIENT_ERROR_PROTOCOL;
    }
    {
        const uint8_t *bytes = (const uint8_t *)reply;
        uint16_t major = xav_get_u16(c, bytes + 8);
        uint16_t minor = xav_get_u16(c, bytes + 10);
        size_t i;
        for (i = 12; i < 32; ++i) {
            if (bytes[i] != 0) {
                free(reply);
                free(c);
                return XAV_CLIENT_ERROR_PROTOCOL;
            }
        }
        if (version) { version->major = major; version->minor = minor; }
        free(reply);
        if (major != XAVERIUS_MAJOR_VERSION || minor < XAVERIUS_MINOR_VERSION) {
            free(c); return XAV_CLIENT_ERROR_VERSION;
        }
    }
    *out = c;
    return XAV_CLIENT_SUCCESS;
}
void xav_connection_destroy(xav_connection *c) { free(c); }
uint8_t xav_connection_major_opcode(const xav_connection *c) { return c ? c->major_opcode : 0; }
void xav_free(void *p) { free(p); }
const char *xav_client_status_string(xav_client_status s)
{
    static const char *const names[] = {
        "success", "invalid argument", "X connection error",
        "XAverius extension unavailable", "incompatible XAverius version",
        "malformed XAverius reply", "out of memory", "X11 request error",
        "XGE 1.0 negotiation required"
    };
    return (unsigned)s < sizeof(names) / sizeof(names[0]) ? names[s] : "unknown client status";
}
