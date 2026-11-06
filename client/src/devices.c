/* SPDX-License-Identifier: MIT */
#include <stdlib.h>
#include <string.h>
#include "internal.h"

static size_t padded4(size_t n) { return (n + 3u) & ~(size_t)3u; }

void xav_free_physical_devices(xav_physical_device *items, size_t count)
{
    size_t i;
    if (!items) return;
    for (i = 0; i < count; ++i) free(items[i].name);
    free(items);
}

xav_client_status xav_enumerate_physical_devices(xav_connection *c,
    xav_physical_device **devices, size_t *device_count,
    xcb_generic_error_t **error_out)
{
    xcb_generic_reply_t *reply = NULL;
    xav_physical_device *items = NULL;
    size_t total, offset = 32, count = 0, capacity = 0;
    xav_client_status status;
    if (!c || !devices || !device_count) return XAV_CLIENT_ERROR_ARGUMENT;
    *devices = NULL;
    *device_count = 0;
    if (error_out) *error_out = NULL;
    status = xav_send_reply_request(c, XAVERIUS_REQ_ENUMERATE_PHYSICAL_DEVICES,
                                    &reply, error_out);
    if (status != XAV_CLIENT_SUCCESS) return status;
    if (!xav_reply_envelope_valid(c, reply, &total) ||
        reply->response_type != 1 || total < 32) goto malformed;

    while (offset < total) {
        const uint8_t *p = (const uint8_t *)reply + offset;
        xav_physical_device item;
        uint16_t name_len;
        size_t padded, record_len, i;
        if (total - offset < 32) goto malformed;
        name_len = xav_get_u16(c, p + 28);
        padded = padded4(name_len);
        if (padded > SIZE_MAX - 32) goto malformed;
        record_len = 32 + padded;
        if (record_len > total - offset || xav_get_u16(c, p + 30) != 0)
            goto malformed;
        for (i = name_len; i < padded; ++i)
            if (p[32 + i] != 0) goto malformed;

        memset(&item, 0, sizeof(item));
        item.xid = xav_get_u32(c, p + 0);
        item.device_type = xav_get_u32(c, p + 4);
        item.vendor_id = xav_get_u32(c, p + 8);
        item.device_id = xav_get_u32(c, p + 12);
        item.api_version = xav_get_u32(c, p + 16);
        item.driver_version = xav_get_u32(c, p + 20);
        item.compute_queue_family_count = xav_get_u32(c, p + 24);
        item.name = malloc((size_t)name_len + 1);
        if (!item.name) goto no_memory;
        memcpy(item.name, p + 32, name_len);
        item.name[name_len] = '\0';

        if (count == capacity) {
            size_t next = capacity ? capacity * 2 : 4;
            xav_physical_device *grown;
            if (next < capacity || next > SIZE_MAX / sizeof(*items)) {
                free(item.name); goto no_memory;
            }
            grown = realloc(items, next * sizeof(*items));
            if (!grown) { free(item.name); goto no_memory; }
            items = grown;
            capacity = next;
        }
        items[count++] = item;
        offset += record_len;
    }
    free(reply);
    *devices = items;
    *device_count = count;
    return XAV_CLIENT_SUCCESS;

malformed:
    free(reply);
    xav_free_physical_devices(items, count);
    return XAV_CLIENT_ERROR_PROTOCOL;
no_memory:
    free(reply);
    xav_free_physical_devices(items, count);
    return XAV_CLIENT_ERROR_NO_MEMORY;
}
