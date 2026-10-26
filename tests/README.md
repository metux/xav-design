# Wire conformance fixtures

The golden fixtures are protocol ABI tests, not tests against a running X server.

- `wire-vectors.json` covers selected request layouts, including CreateBuffer,
  ReadBuffer and WriteBuffer payload boundaries in both X11 byte orders.
- `event-vectors.json` covers the seven compute-baseline XGE event types in both
  byte orders. Fixture values for the extension opcode and event sequence are
  deliberately fixed test values; real connections supply their negotiated
  extension opcode and current sequence number.
- `presentation-event-vectors.json` and `test_presentation_event_vectors.py`
  cover profile-gated `IMAGE_RELEASED` and `PRESENTATION_COMPLETE` frames in
  both byte orders, including all payload fields, the 64-bit token, reserved
  fields, the 64-byte total size, and XGE `length = 8`. Negative raw-wire
  cases also reject malformed XGE lengths, mismatched event IDs, nonzero
  reserved header/payload fields, invalid serialized completion statuses,
  zero presentation tokens, and unsupported byte-order arguments. These tests
  do not imply that the presentation-capable profile is implemented by a live
  server.
- `select-events-vectors.json` covers `SelectEvents` for connection, device and
  queue scopes in both byte orders. Its tests compare field offsets, scope IDs,
  scope-specific masks and the subopcode against the normative chapters/registry.
- `reply-vectors.json` covers fixed fence/semaphore replies, padded ReadBuffer, variable one- and two-record physical-device enumeration,
  data, empty and populated physical-device enumeration, queue-family and memory-property
  records, property success, NOT_SUPPORTED/NOT_AVAILABLE failures, buffer requirements, WriteBuffer success, and
  semaphore timeout replies in both byte orders.
- `test_wire_vectors.py` checks request encoding, declared lengths, padding,
  and malformed request framing.
- `test_event_vectors.py` checks XGE header and payload encoding, total size,
  event IDs, reserved bytes, malformed raw event framing, and compares every
  encoded field offset/size against the normative event chapters. Event-local
  values, including both uses of the shared device reason-code registry, are
  checked against their registries. It also checks the full central error-offset
  range, including acceptance of offset 8 and rejection of offset 9.
- `test_select_events_vectors.py` checks golden request bytes, common-header
  reserved fields, all three scopes, valid mask bits, zero-mask deselection, and
  the normative layout and subopcode registry. Negative raw-wire cases cover
  malformed common headers and invalid scope/field combinations, as well as
  invalid scope, masks, flags and reserved fields.
- `test_reply_vectors.py` checks standard reply framing, fixed reply fields,
  variable payload lengths, record boundaries, padding, and malformed headers.
- `test_presentation_reply_vectors.py` passes every documented presentation
  reply status through the validator in both byte orders and validates raw
  reply framing, exact
  fixed/variable sizes, capability record-count formulas, failure-payload
  zeroing, queue-family support flags, ordered nonempty family records and aggregate support consistency, nonzero current extents and internally consistent minimum/maximum extent and image-count bounds
  on successful capability replies, zero-image successful swapchain replies, request-matched successful image counts and failure counts, acquire failure indices and reserved
  words. Malformed-wire cases mutate serialized replies
  to ensure invalid lengths, status values, flags, and failure payloads are
  rejected rather than merely testing the reference encoder.
- `test_reply_spec_coverage.py` derives status sets, memory-count limits/formulas,
  and ReadBuffer alignment expectations from the normative chapters, then requires
  golden fixtures for every status in both byte orders and maximum memory counts.
- `check-wire-layout.py` validates reply vectors against the 32-byte X11
  framing contract, declared lengths, enumeration/memory record formulas, fixed reply field offsets and status values,
  reserved fields, padding, required endian coverage, and intentionally malformed negative reply fixtures.
  Positive property replies exercise one- and five-byte BYTE_ARRAY boundaries plus the registered 16-byte UUID and three-element CARD32_ARRAY shapes, including zero padding and reply-word rounding.   Negative replies include variable device-record length/padding errors and memory-type heap indices outside the advertised heap range. Additional cases cover a truncated second device record, malformed queue-family record-array length, and nonzero ReadBuffer padding. The memory-property checks separately enforce zero `memory_properties_flags`, zero reserved fields, exact aggregate length, and valid type/heap flag masks. The memory-property checks also enforce exact aggregate length, zero reserved fields, and valid type/heap flag masks; queue-family flags and device-record reserved fields are checked too. Negative cases also cover ReadBuffer payload-size mismatches and nonzero NOT_AVAILABLE fields. Reserved-byte violations are also isolated per fence and both semaphore-wait reply statuses.

Run all fixture tests from the repository root:

```sh
python3 -m py_compile tools/check-wire-layout.py tests/test_wire_vectors.py tests/test_event_vectors.py tests/test_presentation_event_vectors.py tests/test_select_events_vectors.py tests/test_reply_vectors.py tests/test_reply_spec_coverage.py
python3 tools/check-wire-layout.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Live X11/XGE interoperability (implementation prerequisite)

The fixture suite above is intentionally offline. Once a XAverius server and client exist, run a separate live test against an X server that actually supports XGE (Xvfb is suitable only when the XAverius server extension is loaded into that server):

- Discover the XAverius major opcode with `QueryExtension`; do not hard-code it. Negotiate XGE with `GEQueryVersion` and verify that versions below 1.0 or failed negotiation prevent device creation and `SelectEvents` as specified.
- Send `SelectEvents` for each supported scope, then verify on the socket that the emitted packet has `response_type = GenericEvent (35)`, `extension` equal to the negotiated XAverius major opcode, the registered static `evtype`, exact `length` and total byte count, and zero reserved header/payload fields.
- Exercise every event type with known field values and decode the received bytes using the connection's byte order. In particular check the 60-byte `ASYNC_ERROR`, all five 48-byte device events, and both 56-byte terminal submission events.
- Check connection/device/queue mask isolation, zero-mask deselection, replacement rather than accumulation, failed-`SelectEvents` atomicity, unmaskable events, and that event delivery is suppressed after successful `DestroyDevice` while already queued events remain untouched.
- Race terminal submission completion against successful `SelectEvents` replacement and `DestroyDevice`; repeat enough times to expose duplicate terminal events, delivery after destruction, or use of a stale connection/resource identity.
- Run with at least one little-endian and one big-endian client if available; otherwise record the missing byte-order coverage as an explicit limitation.

Capture the raw event bytes and the server/Xlib event-decoder result for each case. Do not mark this item complete based solely on fixture tests or on a client library's decoded event structure: the raw XGE header and framing must be checked independently.

A passing fixture suite proves consistency between the reference encoders and
the committed expected bytes. It does not establish interoperability with an
unimplemented client or server; a future implementation should consume these
fixtures as an independent wire-format oracle.
