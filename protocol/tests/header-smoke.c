#include <xaverius.h>
#include <stddef.h>

_Static_assert(sizeof(xavReqHeader) == 8, "request header");
_Static_assert(sizeof(xavQueryVersionReply) == 32, "version reply");
_Static_assert(offsetof(xavGetSurfaceCapabilitiesReply, records) == 64, "capability payload");
_Static_assert(sizeof(xavAsyncErrorEvent) == 60, "async event");
_Static_assert(sizeof(xavPresentationCompleteEvent) == 64, "presentation event");
_Static_assert(sizeof(xavCreateSwapchainReq) == 48, "create swapchain");
_Static_assert(sizeof(xavQueuePresentReq) == 44, "queue present tail struct");

int main(void) { return XAV_REQ_QUEUE_PRESENT != 47; }
