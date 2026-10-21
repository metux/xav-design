# XAverius central registries

All wire-visible numeric identifiers are defined centrally. Chapter-local tables may explain semantics but must not independently allocate values. Values in one namespace are not interchangeable with values in another namespace.

| Registry | Namespace | Status |
|---|---|---|
| [Request subopcodes](request-subopcodes.md) | X11 request subopcode | 39 current requests assigned; append-only |
| [Errors](errors.md) | XAverius error offset from X11 `first_error` | Assigned |
| [Descriptor types](descriptor-types.md) | `descriptor_type` values | v0.1 storage-buffer type assigned |
| [Shader stages](shader-stages.md) | shader-stage bit masks | v0.1 compute stage assigned |
| [Queue flags](queue-flags.md) | physical-device queue capability bits | Assigned from the device chapter |
| [Physical-device types](device-types.md) | `PHYSICALDEVICEINFO.device_type` | Assigned |
| [Event types and fields](event-types.md) | XGE event type IDs and event-local enums | Event type IDs assigned; selection request layout open |
| Feature IDs and device extensions | `CreateDevice` feature/extension namespace | Open: exact v0.1 support set not settled |
| Property names and Atoms | `GetPhysicalDeviceProperty` property namespace | Open: canonical property/Atom registry not settled |
| Command-buffer entry IDs | `CommandBufferData` entry namespace | Open: numeric IDs not yet allocated |
