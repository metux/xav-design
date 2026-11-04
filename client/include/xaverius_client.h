/* SPDX-License-Identifier: MIT */
#ifndef XAVERIUS_CLIENT_H
#define XAVERIUS_CLIENT_H
#include <stddef.h>
#include <stdint.h>
#include <xcb/xcb.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct xav_connection xav_connection;
typedef enum xav_client_status {
 XAV_CLIENT_SUCCESS=0, XAV_CLIENT_ERROR_ARGUMENT, XAV_CLIENT_ERROR_CONNECTION,
 XAV_CLIENT_ERROR_EXTENSION_MISSING, XAV_CLIENT_ERROR_VERSION,
 XAV_CLIENT_ERROR_PROTOCOL, XAV_CLIENT_ERROR_NO_MEMORY, XAV_CLIENT_ERROR_X11
} xav_client_status;
typedef struct xav_version { uint16_t major, minor; } xav_version;
typedef struct xav_physical_device {
 uint32_t xid, device_type, vendor_id, device_id, api_version, driver_version;
 uint32_t compute_queue_family_count;
 char *name;
} xav_physical_device;
xav_client_status xav_connection_create(xcb_connection_t *, xav_connection **,
 xav_version *, xcb_generic_error_t **);
xav_client_status xav_connection_negotiate_xge(xav_connection *, xav_version *, xcb_generic_error_t **);
void xav_connection_destroy(xav_connection *);
uint8_t xav_connection_major_opcode(const xav_connection *);
xav_client_status xav_enumerate_physical_devices(xav_connection *,
 xav_physical_device **, size_t *, xcb_generic_error_t **);
void xav_free_physical_devices(xav_physical_device *, size_t);
void xav_free(void *);
const char *xav_client_status_string(xav_client_status);
#ifdef __cplusplus
}
#endif
#endif
