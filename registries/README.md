# XAverius central registries

All wire-visible numeric identifiers are defined centrally. Chapter-local tables may explain semantics but must not independently allocate values. Values in one namespace are not interchangeable with values in another namespace.

The automated wire-layout checker validates uniqueness and expected ranges for the current request, event, error, command-entry, descriptor-type, device-type, queue-flag, shader-stage, and physical-property type assignments. It also checks that the v0.1 optional feature-ID and device-extension sets remain explicitly empty. These checks guard documentation consistency; they do not freeze the protocol or replace semantic review.

| Registry | Namespace | Status |
|---|---|---|
| [Request subopcodes](request-subopcodes.md) | X11 request subopcode | 40 current requests assigned; append-only |
| [Errors](errors.md) | XAverius error offset from X11 `first_error` | Assigned |
| [Descriptor types](descriptor-types.md) | `descriptor_type` values | v0.1 storage-buffer type assigned |
| [Shader stages](shader-stages.md) | shader-stage bit masks | v0.1 compute stage assigned |
| [Queue flags](queue-flags.md) | physical-device queue capability bits | Bits 0–4 assigned; bits 5–31 reserved |
| [Physical-device types](device-types.md) | `PHYSICALDEVICEINFO.device_type` | Assigned |
| [Event types and fields](event-types.md) | XGE event type IDs and event-local enums | Event type IDs and SelectEvents layout assigned |
| [Feature IDs](feature-ids.md) | `DEVICEFEATUREREQUEST.feature_id` | v0.1 has no optional feature assignments |
| [Device extensions](device-extensions.md) | `DEVICEEXTENSIONREQUEST` names | v0.1 has no optional device extensions |
| [Physical-device properties](physical-device-properties.md) | Canonical Atom names and property wire types | Four v0.1 properties registered; Atom numbers remain server-assigned |
| [Command-buffer entry IDs](command-entries.md) | `CommandBufferData` entry namespace | Values 1–4 assigned for v0.1 compute path |
