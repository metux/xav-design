/* SPDX-License-Identifier: MIT */
#include <stdlib.h>
#include <string.h>
#include "internal.h"

static xcb_extension_t ge_extension = { "Generic Event Extension", 0 };

xav_client_status
xav_connection_negotiate_xge(xav_connection *c, xav_version *version,
                             xcb_generic_error_t **error_out)
{
    static const xcb_protocol_request_t request = { 2, &ge_extension, 0, 0 };
    uint16_t requested_major = 1, requested_minor = 0;
    uint8_t body[4];
    struct iovec parts[4];
    const xcb_query_extension_reply_t *ext;
    xcb_generic_reply_t *reply;
    xcb_generic_error_t *error = NULL;
    unsigned int sequence;
    size_t i;

    if (!c)
        return XAV_CLIENT_ERROR_ARGUMENT;
    if (version)
        memset(version, 0, sizeof(*version));
    if (error_out)
        *error_out = NULL;
    if (c->xge_negotiated) {
        if (version)
            *version = c->xge_version;
        return XAV_CLIENT_SUCCESS;
    }
    if (xcb_connection_has_error(c->xcb))
        return XAV_CLIENT_ERROR_CONNECTION;
    ext = xcb_get_extension_data(c->xcb, &ge_extension);
    if (!ext || !ext->present)
        return XAV_CLIENT_ERROR_EXTENSION_MISSING;

    memcpy(body, &requested_major, sizeof(requested_major));
    memcpy(body + 2, &requested_minor, sizeof(requested_minor));
    memset(parts, 0, sizeof(parts));
    parts[2].iov_base = body;
    parts[2].iov_len = sizeof(body);
    sequence = xcb_send_request(c->xcb, 0, parts + 2, &request);
    if (!sequence)
        return XAV_CLIENT_ERROR_CONNECTION;
    reply = xcb_wait_for_reply(c->xcb, sequence, &error);
    if (error) {
        if (error_out)
            *error_out = error;
        else
            free(error);
        return XAV_CLIENT_ERROR_X11;
    }
    if (!reply)
        return XAV_CLIENT_ERROR_CONNECTION;
    if (reply->response_type != 1 || ((const uint8_t *)reply)[1] != 0 || reply->length != 0) {
        free(reply);
        return XAV_CLIENT_ERROR_PROTOCOL;
    }
    {
        const uint8_t *bytes = (const uint8_t *)reply;
        uint16_t major, minor;
        memcpy(&major, bytes + 8, sizeof(major));
        memcpy(&minor, bytes + 10, sizeof(minor));
        for (i = 12; i < 32; ++i) {
            if (bytes[i] != 0) {
                free(reply);
                return XAV_CLIENT_ERROR_PROTOCOL;
            }
        }
        free(reply);
        if (major < 1)
            return XAV_CLIENT_ERROR_VERSION;
        c->xge_version.major = major;
        c->xge_version.minor = minor;
    }
    c->xge_negotiated = 1;
    if (version)
        *version = c->xge_version;
    return XAV_CLIENT_SUCCESS;
}
