# Device feature-ID registry

This registry defines the numeric namespace used by `DEVICEFEATUREREQUEST.feature_id` in `CreateDevice`. Values are XAverius identifiers; native Vulkan structure positions, bit positions, enum values, and feature names MUST NOT be transmitted as feature IDs.

## v0.1 assignments

No optional device feature IDs are assigned in v0.1. The initial compute path uses only functionality required by the selected XAverius baseline and does not require an optional `DEVICEFEATUREREQUEST`. Vulkan `timelineSemaphore` is a mandatory v0.1 baseline capability, not an optional feature ID: the server MUST enable it for every successfully created logical Device, and `CreateDevice` MUST reject a Physical Device that does not support it.

| ID | Symbol | v0.1 status |
|---:|---|---|
| — | No assignments | No optional feature can be requested in v0.1 |

An empty registry is intentional and normative: every `feature_id` value is unknown in v0.1 and MUST be rejected with `BadValue`. Do not infer support from a native Vulkan feature or silently accept an unregistered ID.

Future feature IDs are positive `CARD32` values allocated centrally and append-only. Once assigned, an ID and its meaning MUST NOT be reused or changed. Later versions may define a registered feature that a particular Physical Device does not support; that case is distinct from an unknown ID and follows the `BadMatch` rule in [device discovery and logical devices](../spec/devices.md).

`CreateDefaultDevice` does not enable or imply optional feature IDs. This registry does not describe Vulkan core-version functionality, which is governed by the XAverius v0.1 baseline and the applicable request semantics.
