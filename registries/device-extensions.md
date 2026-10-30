# Device-extension registry

This registry defines the names accepted in `DEVICEEXTENSIONREQUEST` entries of `CreateDevice`. Names are protocol-level ASCII strings, not numeric IDs and not server-assigned X11 Atoms.

## v0.1 assignments

No optional device extensions are assigned in v0.1.

| Extension name | v0.1 status |
|---|---|
| — | No optional device extensions are registered |

This empty registry is intentional and normative. A syntactically valid extension name is not thereby a registered XAverius extension. In v0.1, every syntactically valid name is unknown to XAverius and MUST be rejected with `BadMatch`; a malformed name MUST be rejected with `BadValue`. A server MUST NOT silently ignore an extension request or expose extension functionality merely because the backend Vulkan implementation supports a similarly named extension.

Future entries are added centrally. An extension name, once registered, MUST retain its spelling and meaning. Registration does not require every Physical Device to support the extension; a registered extension unsupported by the selected Physical Device is rejected with `BadMatch`. The server MUST enable only extensions explicitly requested by the client and supported by the selected Physical Device.

`CreateDefaultDevice` MUST NOT enable optional client-requested device extensions implicitly. This registry covers device extensions only; it does not define instance extensions or extensions used internally by the server. The server MAY enable `VK_KHR_timeline_semaphore` internally when required to implement the mandatory v0.1 `timelineSemaphore` baseline on a Vulkan API version where the feature is provided by that extension; this backend dependency is not a client-requested optional extension and is not a registry assignment.
