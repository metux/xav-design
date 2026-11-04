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
    XAV_CLIENT_SUCCESS = 0, XAV_CLIENT_ERROR_ARGUMENT, XAV_CLIENT_ERROR_CONNECTION,
    XAV_CLIENT_ERROR_EXTENSION_MISSING, XAV_CLIENT_ERROR_VERSION,
    XAV_CLIENT_ERROR_PROTOCOL, XAV_CLIENT_ERROR_NO_MEMORY, XAV_CLIENT_ERROR_X11,
    XAV_CLIENT_ERROR_XGE_REQUIRED
} xav_client_status;
typedef struct xav_version { uint16_t major, minor; } xav_version;
typedef struct xav_physical_device {
    uint32_t xid, device_type, vendor_id, device_id, api_version, driver_version;
    uint32_t compute_queue_family_count;
    char *name;
} xav_physical_device;
typedef enum xav_event_scope {
    XAV_EVENT_SCOPE_CONNECTION = 0, XAV_EVENT_SCOPE_DEVICE = 1, XAV_EVENT_SCOPE_QUEUE = 2
} xav_event_scope;
typedef enum xav_event_type {
    XAV_CLIENT_EVENT_ASYNC_ERROR = 0, XAV_CLIENT_EVENT_DEVICE_LOST = 1,
    XAV_CLIENT_EVENT_DEVICE_STATUS_CHANGED = 2, XAV_CLIENT_EVENT_DEVICE_MEMORY_PRESSURE = 3,
    XAV_CLIENT_EVENT_DEVICE_IDLE = 4, XAV_CLIENT_EVENT_SUBMISSION_COMPLETE = 5,
    XAV_CLIENT_EVENT_SUBMISSION_FAILED = 6, XAV_CLIENT_EVENT_IMAGE_RELEASED = 7,
    XAV_CLIENT_EVENT_PRESENTATION_COMPLETE = 8
} xav_event_type;
typedef struct xav_async_error_event {
    uint32_t device_xid, error_code, origin;
    uint64_t submission_token;
    uint32_t resource_xid;
} xav_async_error_event;
typedef struct xav_device_lost_event {
    uint32_t device_xid, reason_code;
    uint64_t device_generation;
} xav_device_lost_event;
typedef struct xav_device_status_changed_event {
    uint32_t physical_device_xid, new_status, reason_code;
} xav_device_status_changed_event;
typedef struct xav_device_memory_pressure_event {
    uint32_t device_xid, heap_index, pressure_level;
} xav_device_memory_pressure_event;
typedef struct xav_device_idle_event {
    uint32_t device_xid, idle_reason;
    uint64_t device_generation;
} xav_device_idle_event;
typedef struct xav_submission_complete_event {
    uint32_t device_xid, queue_family_index, queue_index;
    uint64_t submission_token;
} xav_submission_complete_event;
typedef struct xav_submission_failed_event {
    uint32_t device_xid, queue_family_index, queue_index, failure_class;
    uint64_t submission_token;
} xav_submission_failed_event;
typedef struct xav_image_released_event {
    uint32_t device_xid, queue_family_index, queue_index, swapchain_xid, image_index;
    uint64_t presentation_token;
} xav_image_released_event;
typedef struct xav_presentation_complete_event {
    uint32_t device_xid, queue_family_index, queue_index, swapchain_xid, image_index, status;
    uint64_t presentation_token;
} xav_presentation_complete_event;
typedef struct xav_event {
    uint16_t type, sequence;
    uint32_t full_sequence;
    const uint8_t *unknown_payload;
    size_t unknown_payload_size;
    union {
        xav_async_error_event async_error;
        xav_device_lost_event device_lost;
        xav_device_status_changed_event device_status_changed;
        xav_device_memory_pressure_event device_memory_pressure;
        xav_device_idle_event device_idle;
        xav_submission_complete_event submission_complete;
        xav_submission_failed_event submission_failed;
        xav_image_released_event image_released;
        xav_presentation_complete_event presentation_complete;
    } data;
} xav_event;
typedef enum xav_event_decode_result {
    XAV_EVENT_DECODE_ERROR = -1, XAV_EVENT_DECODE_NOT_XAVERIUS = 0,
    XAV_EVENT_DECODE_OK = 1, XAV_EVENT_DECODE_UNKNOWN = 2
} xav_event_decode_result;
xav_client_status xav_connection_create(xcb_connection_t *, xav_connection **,
                                        xav_version *, xcb_generic_error_t **);
xav_client_status xav_connection_negotiate_xge(xav_connection *, xav_version *,
                                               xcb_generic_error_t **);
void xav_connection_destroy(xav_connection *);
uint8_t xav_connection_major_opcode(const xav_connection *);
xav_client_status xav_enumerate_physical_devices(xav_connection *,
                                                  xav_physical_device **, size_t *,
                                                  xcb_generic_error_t **);
void xav_free_physical_devices(xav_physical_device *, size_t);
/* Requires successful XGE 1.0 negotiation; returns checked X11 errors. */
xav_client_status xav_connection_select_events(
    xav_connection *, xav_event_scope, uint32_t device_xid,
    uint32_t queue_family_index, uint32_t queue_index, uint32_t event_mask,
    xcb_generic_error_t **);
xav_event_decode_result xav_event_decode(const xav_connection *,
                                         const xcb_generic_event_t *, xav_event *);
void xav_free(void *);
const char *xav_client_status_string(xav_client_status);
#ifdef __cplusplus
}
#endif
#endif
