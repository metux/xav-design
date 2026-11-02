#ifndef XAVERIUS_PROTO_H
#define XAVERIUS_PROTO_H
#include <X11/X.h>
#include <X11/Xmd.h>
#include <stddef.h>
#include "xaveriusconst.h"
#pragma pack(push, 4)

typedef struct { CARD8 reqType; CARD8 data; CARD16 length; CARD8 subopcode; CARD8 flags; CARD16 reserved; } xavReqHeader;
typedef struct { CARD8 response_type; CARD8 data; CARD16 sequenceNumber; CARD32 length; CARD32 pad[6]; } xavReplyHeader;
typedef struct { CARD8 response_type; CARD8 extension; CARD16 sequenceNumber; CARD32 length; CARD16 evtype; CARD8 pad[22]; } xavXGEHeader;

typedef struct { xavReqHeader header; } xavQueryVersionReq;
typedef struct { xavReqHeader header; } xavEnumeratePhysicalDevicesReq;
typedef struct { xavReqHeader header; XID physical_device_xid; ATOM property_atom; } xavGetPhysicalDevicePropertyReq;
typedef struct { xavReqHeader header; XID physical_device_xid; } xavGetPhysicalDeviceQueueFamilyPropertiesReq;
typedef struct { CARD32 queue_family_index; CARD16 queue_count; CARD16 reserved; FLOAT32 queue_priorities[1]; } xavQueueFamilyRequest;
typedef struct { CARD32 feature_id; CARD32 enabled; } xavDeviceFeatureRequest;
typedef struct { CARD16 name_length; CARD16 reserved; CARD8 name[1]; } xavDeviceExtensionRequest;
typedef struct { xavReqHeader header; XID device_xid; XID physical_device_xid; CARD16 queue_family_request_count; CARD16 feature_request_count; CARD16 device_extension_count; CARD16 reserved; CARD8 requests[1]; } xavCreateDeviceReq;
typedef struct { xavReqHeader header; XID device_xid; CARD16 queue_count; CARD16 reserved; FLOAT32 priorities[1]; } xavCreateDefaultDeviceReq;
typedef struct { xavReqHeader header; XID device_xid; } xavDestroyDeviceReq;
typedef struct { xavReqHeader header; XID physical_device_xid; } xavGetPhysicalDeviceMemoryPropertiesReq;

typedef struct { xavReqHeader header; XID device_xid; XID buffer_xid; CARD64 size; CARD32 usage_flags; CARD32 reserved; } xavCreateBufferReq;
typedef struct { xavReqHeader header; XID device_xid; XID buffer_xid; } xavGetBufferMemoryRequirementsReq;
typedef struct { xavReqHeader header; XID device_xid; XID memory_xid; CARD64 allocation_size; CARD32 memory_type_index; CARD32 reserved; } xavAllocateMemoryReq;
typedef struct { xavReqHeader header; XID device_xid; XID memory_xid; } xavFreeMemoryReq;
typedef struct { xavReqHeader header; XID device_xid; XID buffer_xid; XID memory_xid; CARD64 memory_offset; } xavBindBufferMemoryReq;
typedef struct { xavReqHeader header; XID device_xid; XID buffer_xid; CARD64 buffer_offset; CARD32 data_length; CARD8 data[1]; } xavWriteBufferReq;
typedef struct { xavReqHeader header; XID device_xid; XID buffer_xid; CARD64 buffer_offset; CARD32 data_length; } xavReadBufferReq;

typedef struct { xavReqHeader header; XID device_xid; XID shader_module_xid; CARD32 data_length; CARD8 data[1]; } xavShaderModuleDataReq;
typedef struct { CARD32 binding; CARD32 descriptor_type; CARD32 descriptor_count; CARD32 stage_flags; } xavDescriptorSetLayoutBinding;
typedef struct { xavReqHeader header; XID device_xid; XID descriptor_set_layout_xid; CARD32 flags; CARD32 binding_count; xavDescriptorSetLayoutBinding bindings[1]; } xavCreateDescriptorSetLayoutReq;
typedef struct { CARD32 descriptor_type; CARD32 descriptor_count; } xavDescriptorPoolSize;
typedef struct { xavReqHeader header; XID device_xid; XID descriptor_pool_xid; CARD32 max_sets; CARD16 pool_size_count; CARD16 reserved; xavDescriptorPoolSize pool_sizes[1]; } xavCreateDescriptorPoolReq;
typedef struct { xavReqHeader header; XID device_xid; XID descriptor_pool_xid; } xavDestroyDescriptorPoolReq;
typedef struct { XID descriptor_set_xid; XID descriptor_set_layout_xid; } xavDescriptorSetAllocation;
typedef struct { xavReqHeader header; XID device_xid; XID descriptor_pool_xid; CARD16 descriptor_set_count; CARD16 reserved; xavDescriptorSetAllocation allocations[1]; } xavAllocateDescriptorSetsReq;
typedef struct { XID descriptor_set_xid; CARD32 binding; CARD32 array_element; CARD32 descriptor_type; XID buffer_xid; CARD64 buffer_offset; CARD64 range; } xavDescriptorWrite;
typedef struct { xavReqHeader header; XID device_xid; CARD16 write_count; CARD16 reserved0; CARD32 reserved1; xavDescriptorWrite writes[1]; } xavUpdateDescriptorSetsReq;
typedef struct { xavReqHeader header; XID device_xid; XID descriptor_pool_xid; CARD16 descriptor_set_count; CARD16 reserved; XID descriptor_set_xids[1]; } xavFreeDescriptorSetsReq;
typedef struct { CARD32 stage_flags; CARD32 offset; CARD32 size; } xavPushConstantRange;
typedef struct { xavReqHeader header; XID device_xid; XID pipeline_layout_xid; CARD16 set_layout_count; CARD16 push_constant_range_count; CARD8 data[1]; } xavCreatePipelineLayoutReq;
typedef struct { xavReqHeader header; XID device_xid; XID pipeline_xid; XID pipeline_layout_xid; XID shader_module_xid; CARD16 entry_point_length; CARD16 reserved; CARD8 entry_point[1]; } xavCreateComputePipelineReq;

typedef struct { xavReqHeader header; XID device_xid; XID command_pool_xid; CARD32 queue_family_index; CARD32 flags; } xavCreateCommandPoolReq;
typedef struct { xavReqHeader header; XID device_xid; XID command_pool_xid; } xavDestroyCommandPoolReq;
typedef struct { xavReqHeader header; XID device_xid; XID command_buffer_xid; } xavResetCommandBufferReq;
typedef struct { xavReqHeader header; XID command_buffer_xid; XID command_pool_xid; CARD8 entries[1]; } xavCommandBufferDataReq;
typedef struct { CARD16 command_id; CARD16 entry_length; } xavCommandEntryHeader;
typedef struct { CARD16 command_id; CARD16 entry_length; XID pipeline_xid; } xavCmdBindPipeline;
typedef struct { CARD16 command_id; CARD16 entry_length; XID pipeline_layout_xid; CARD32 first_set; CARD16 descriptor_set_count; CARD16 reserved; XID descriptor_set_xids[1]; } xavCmdBindDescriptorSets;
typedef struct { CARD16 command_id; CARD16 entry_length; CARD32 group_count_x; CARD32 group_count_y; CARD32 group_count_z; } xavCmdDispatch;
typedef struct { CARD16 command_id; CARD16 entry_length; CARD32 stage_flags; XID pipeline_layout_xid; CARD32 offset; CARD32 data_length; CARD8 data[1]; } xavCmdPushConstants;
typedef struct { CARD16 command_id; CARD16 entry_length; XID buffer_xid; XID swapchain_xid; CARD32 image_index; CARD64 buffer_offset; CARD32 row_length; CARD32 image_height; CARD32 reserved; } xavCmdCopyBufferToSwapchainImage;

typedef struct { XID semaphore_xid; CARD64 wait_value; CARD32 wait_stage_mask; } xavQueueSubmitWait;
typedef struct { XID semaphore_xid; CARD64 signal_value; } xavQueueSubmitSignal;
typedef struct { xavReqHeader header; XID device_xid; CARD32 queue_family_index; CARD32 queue_index; XID fence_xid; CARD16 command_buffer_count; CARD16 wait_semaphore_count; CARD16 signal_semaphore_count; CARD16 reserved; CARD64 submission_token; CARD8 arrays[1]; } xavQueueSubmitReq;
typedef struct { xavReqHeader header; XID device_xid; XID semaphore_xid; CARD32 semaphore_type; CARD64 initial_value; } xavCreateSemaphoreReq;
typedef struct { xavReqHeader header; XID device_xid; XID semaphore_xid; } xavGetSemaphoreCounterValueReq;
typedef struct { XID semaphore_xid; CARD64 wait_value; } xavWaitSemaphoreEntry;
typedef struct { xavReqHeader header; XID device_xid; CARD32 semaphore_count; CARD32 wait_mode; CARD64 timeout_ns; xavWaitSemaphoreEntry entries[1]; } xavWaitSemaphoresReq;
typedef struct { xavReqHeader header; XID device_xid; XID semaphore_xid; CARD64 signal_value; } xavSignalSemaphoreReq;
typedef struct { xavReqHeader header; XID device_xid; XID semaphore_xid; } xavDestroySemaphoreReq;
typedef struct { xavReqHeader header; XID device_xid; XID fence_xid; CARD32 create_flags; CARD32 reserved; } xavCreateFenceReq;
typedef struct { xavReqHeader header; XID device_xid; XID fence_xid; } xavGetFenceStatusReq;
typedef struct { xavReqHeader header; XID device_xid; XID fence_xid; CARD64 timeout_ns; } xavWaitForFenceReq;
typedef struct { xavReqHeader header; XID device_xid; XID fence_xid; } xavResetFenceReq;
typedef struct { xavReqHeader header; XID device_xid; XID fence_xid; } xavDestroyFenceReq;
typedef struct { xavReqHeader header; XID device_xid; XID resource_xid; } xavDestroyResourceReq;
typedef struct { xavReqHeader header; CARD32 scope; XID device_xid; CARD32 queue_family_index; CARD32 queue_index; CARD32 event_mask; CARD32 reserved; } xavSelectEventsReq;

typedef struct { xavReqHeader header; XID surface_xid; XID window_xid; } xavCreateSurfaceReq;
typedef struct { xavReqHeader header; XID surface_xid; } xavDestroySurfaceReq;
typedef struct { xavReqHeader header; XID device_xid; XID surface_xid; } xavGetSurfaceCapabilitiesReq;
typedef struct { xavReqHeader header; XID device_xid; XID swapchain_xid; XID surface_xid; CARD32 image_count; CARD32 format_id; CARD32 color_space_id; CARD32 width; CARD32 height; CARD32 present_mode_id; CARD32 image_usage_flags; } xavCreateSwapchainReq;
typedef struct { xavReqHeader header; XID swapchain_xid; } xavDestroySwapchainReq;
typedef struct { xavReqHeader header; XID device_xid; XID swapchain_xid; CARD64 timeout_ns; XID semaphore_xid; XID fence_xid; } xavAcquireNextImageReq;
typedef struct { xavReqHeader header; XID device_xid; CARD32 queue_family_index; CARD32 queue_index; XID swapchain_xid; CARD32 image_index; CARD32 wait_semaphore_count; CARD64 presentation_token; XID wait_semaphore_xids[1]; } xavQueuePresentReq;

/* Replies whose fields occupy the standard 32-byte reply header's data area. */
typedef struct { CARD8 response_type; CARD8 data; CARD16 sequenceNumber; CARD32 length; CARD16 major_version; CARD16 minor_version; CARD8 reserved[20]; } xavQueryVersionReply;
typedef struct { CARD8 response_type; CARD8 data; CARD16 sequenceNumber; CARD32 length; CARD32 status; CARD32 property_type; CARD32 value_length; CARD8 reserved[12]; } xavGetPhysicalDevicePropertyReply;
typedef struct { CARD8 response_type; CARD8 data; CARD16 sequenceNumber; CARD32 length; CARD32 memory_type_count; CARD32 memory_heap_count; CARD32 memory_properties_flags; CARD32 reserved; CARD8 pad[8]; } xavGetPhysicalDeviceMemoryPropertiesReply;
typedef struct { CARD32 property_flags; CARD32 heap_index; } xavMemoryTypeInfo;
typedef struct { CARD64 size; CARD32 heap_flags; CARD32 reserved; } xavMemoryHeapInfo;
typedef struct { CARD8 response_type; CARD8 data; CARD16 sequenceNumber; CARD32 length; CARD64 size; CARD64 alignment; CARD32 memory_type_bits; CARD32 reserved; } xavGetBufferMemoryRequirementsReply;
typedef struct { CARD32 queue_flags; CARD32 queue_count; CARD32 reserved; } xavQueueFamilyInfo;
typedef struct { XID physical_device_xid; CARD32 device_type; CARD32 vendor_id; CARD32 device_id; CARD32 api_version; CARD32 driver_version; CARD32 compute_queue_family_count; CARD16 device_name_length; CARD16 reserved; CARD8 device_name[1]; } xavPhysicalDeviceInfo;
typedef struct { CARD8 response_type; CARD8 data; CARD16 sequenceNumber; CARD32 length; CARD64 counter_value; CARD8 reserved[16]; } xavGetSemaphoreCounterValueReply;
typedef struct { CARD8 response_type; CARD8 data; CARD16 sequenceNumber; CARD32 length; CARD32 status; CARD8 reserved[20]; } xavWaitSemaphoresReply;
typedef struct { CARD8 response_type; CARD8 fence_status; CARD16 sequenceNumber; CARD32 length; CARD8 reserved[24]; } xavGetFenceStatusReply;
typedef struct { CARD8 response_type; CARD8 data; CARD16 sequenceNumber; CARD32 length; CARD32 status; CARD8 reserved[20]; } xavWaitForFenceReply;

/* XGE events. */
typedef struct { xavXGEHeader header; XID device_xid; CARD32 error_code; CARD32 origin; CARD64 submission_token; XID resource_xid; CARD32 reserved; } xavAsyncErrorEvent;
typedef struct { xavXGEHeader header; XID device_xid; CARD32 reason_code; CARD64 device_generation; } xavDeviceLostEvent;
typedef struct { xavXGEHeader header; XID physical_device_xid; CARD32 new_status; CARD32 reason_code; CARD32 reserved; } xavDeviceStatusChangedEvent;
typedef struct { xavXGEHeader header; XID device_xid; CARD32 heap_index; CARD32 pressure_level; CARD32 reserved; } xavDeviceMemoryPressureEvent;
typedef struct { xavXGEHeader header; XID device_xid; CARD32 idle_reason; CARD64 device_generation; } xavDeviceIdleEvent;
typedef struct { xavXGEHeader header; XID device_xid; CARD32 queue_family_index; CARD32 queue_index; CARD32 reserved; CARD64 submission_token; } xavSubmissionCompleteEvent;
typedef struct { xavXGEHeader header; XID device_xid; CARD32 queue_family_index; CARD32 queue_index; CARD32 failure_class; CARD64 submission_token; } xavSubmissionFailedEvent;
typedef struct { xavXGEHeader header; XID device_xid; CARD32 queue_family_index; CARD32 queue_index; XID swapchain_xid; CARD32 image_index; CARD32 reserved; CARD64 presentation_token; } xavImageReleasedEvent;
typedef struct { xavXGEHeader header; XID device_xid; CARD32 queue_family_index; CARD32 queue_index; XID swapchain_xid; CARD32 image_index; CARD32 status; CARD64 presentation_token; } xavPresentationCompleteEvent;

/* Variable-length presentation capability reply starts at offset 64. */
typedef struct {
    CARD8 response_type; CARD8 data; CARD16 sequenceNumber; CARD32 length;
    CARD32 status; CARD32 present_supported; CARD32 current_width; CARD32 current_height;
    CARD32 min_image_count; CARD32 max_image_count; CARD32 min_width; CARD32 min_height;
    CARD32 max_width; CARD32 max_height; CARD32 format_pair_count; CARD32 present_mode_count;
    CARD32 image_usage_flags; CARD32 queue_family_count; CARD8 records[1];
} xavGetSurfaceCapabilitiesReply;
typedef struct { CARD32 format_id; CARD32 color_space_id; } xavSurfaceFormatPair;
typedef struct { CARD32 queue_family_index; CARD32 present_supported; } xavSurfaceQueueFamilyInfo;
typedef struct { xavReplyHeader header; CARD32 status; CARD32 actual_image_count; } xavCreateSwapchainReply;
typedef struct { xavReplyHeader header; CARD32 status; CARD32 image_index; CARD32 reserved; } xavAcquireNextImageReply;
typedef struct { xavReplyHeader header; CARD32 status; } xavQueuePresentReply;

#pragma pack(pop)

#define sz_xavReqHeader 8
#define sz_xavReplyHeader 32
#define sz_xavXGEHeader 32
#define sz_xavQueryVersionReq 8
#define sz_xavEnumeratePhysicalDevicesReq 8
#define sz_xavGetPhysicalDevicePropertyReq 16
#define sz_xavGetPhysicalDeviceQueueFamilyPropertiesReq 12
#define sz_xavCreateDeviceReq 24
#define sz_xavCreateDefaultDeviceReq 16
#define sz_xavDestroyDeviceReq 12
#define sz_xavGetPhysicalDeviceMemoryPropertiesReq 12
#define sz_xavCreateBufferReq 32
#define sz_xavGetBufferMemoryRequirementsReq 16
#define sz_xavAllocateMemoryReq 32
#define sz_xavFreeMemoryReq 16
#define sz_xavBindBufferMemoryReq 28
#define sz_xavWriteBufferReq 28
#define sz_xavReadBufferReq 28
#define sz_xavShaderModuleDataReq 20
#define sz_xavCreateDescriptorSetLayoutReq 24
#define sz_xavCreateDescriptorPoolReq 24
#define sz_xavDestroyDescriptorPoolReq 16
#define sz_xavAllocateDescriptorSetsReq 20
#define sz_xavUpdateDescriptorSetsReq 20
#define sz_xavFreeDescriptorSetsReq 20
#define sz_xavCreatePipelineLayoutReq 20
#define sz_xavCreateComputePipelineReq 28
#define sz_xavCreateCommandPoolReq 24
#define sz_xavDestroyCommandPoolReq 16
#define sz_xavResetCommandBufferReq 16
#define sz_xavCommandBufferDataReq 16
#define sz_xavQueueSubmitReq 40
#define sz_xavCreateSemaphoreReq 28
#define sz_xavGetSemaphoreCounterValueReq 16
#define sz_xavWaitSemaphoresReq 28
#define sz_xavSignalSemaphoreReq 24
#define sz_xavDestroySemaphoreReq 16
#define sz_xavCreateFenceReq 24
#define sz_xavGetFenceStatusReq 16
#define sz_xavWaitForFenceReq 24
#define sz_xavResetFenceReq 16
#define sz_xavDestroyFenceReq 16
#define sz_xavDestroyResourceReq 16
#define sz_xavSelectEventsReq 32
#define sz_xavCreateSurfaceReq 16
#define sz_xavDestroySurfaceReq 12
#define sz_xavGetSurfaceCapabilitiesReq 16
#define sz_xavCreateSwapchainReq 48
#define sz_xavDestroySwapchainReq 12
#define sz_xavAcquireNextImageReq 32
#define sz_xavQueuePresentReq 40
#define sz_xavAsyncErrorEvent 60
#define sz_xavDeviceLostEvent 48
#define sz_xavDeviceStatusChangedEvent 48
#define sz_xavDeviceMemoryPressureEvent 48
#define sz_xavDeviceIdleEvent 48
#define sz_xavSubmissionCompleteEvent 56
#define sz_xavSubmissionFailedEvent 56
#define sz_xavImageReleasedEvent 64
#define sz_xavPresentationCompleteEvent 64

#if defined(__cplusplus)
# define XAV_STATIC_ASSERT(c, m) static_assert((c), m)
#elif defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
# define XAV_STATIC_ASSERT(c, m) _Static_assert((c), m)
#else
# define XAV_STATIC_ASSERT(c, m) typedef char xav_static_assert_##__LINE__[(c) ? 1 : -1]
#endif
XAV_STATIC_ASSERT(sizeof(xavReqHeader) == 8, "request header size");
XAV_STATIC_ASSERT(sizeof(xavReplyHeader) == 32, "reply header size");
XAV_STATIC_ASSERT(sizeof(xavXGEHeader) == 32, "XGE header size");
XAV_STATIC_ASSERT(sizeof(xavQueryVersionReply) == 32, "QueryVersion reply size");
XAV_STATIC_ASSERT(sizeof(xavGetPhysicalDevicePropertyReply) == 32, "property reply size");
XAV_STATIC_ASSERT(sizeof(xavGetBufferMemoryRequirementsReply) == 32, "memory requirements reply size");
XAV_STATIC_ASSERT(offsetof(xavAsyncErrorEvent, submission_token) == 44, "ASYNC_ERROR token offset");
XAV_STATIC_ASSERT(sizeof(xavAsyncErrorEvent) == 60, "ASYNC_ERROR event size");
XAV_STATIC_ASSERT(offsetof(xavImageReleasedEvent, presentation_token) == 56, "IMAGE_RELEASED token offset");
XAV_STATIC_ASSERT(sizeof(xavImageReleasedEvent) == 64, "IMAGE_RELEASED event size");
XAV_STATIC_ASSERT(offsetof(xavGetSurfaceCapabilitiesReply, records) == 64, "capabilities variable payload offset");
#undef XAV_STATIC_ASSERT
#endif
