/* SPDX-License-Identifier: MIT */
#ifndef XAVERIUS_CLIENT_INTERNAL_H
#define XAVERIUS_CLIENT_INTERNAL_H
#include <stdint.h>
#include <xcb/xcb.h>
#include <xcb/xcbext.h>
#include <xcb/xproto.h>
#include <xaverius.h>
#include "xaverius_client.h"
extern xcb_extension_t xav_extension;
struct xav_connection {
    xcb_connection_t *xcb;
    const xcb_query_extension_reply_t *extension;
    uint8_t major_opcode;
    int xge_negotiated;
    xav_version xge_version;
};
uint16_t xav_get_u16(const struct xav_connection *, const uint8_t *);
uint32_t xav_get_u32(const struct xav_connection *, const uint8_t *);
int xav_reply_envelope_valid(const struct xav_connection *,
                             const xcb_generic_reply_t *, size_t *);
xav_client_status xav_send_reply_request(struct xav_connection *, uint8_t,
                                          xcb_generic_reply_t **,
                                          xcb_generic_error_t **);
#endif
