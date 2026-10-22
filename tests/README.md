# Wire conformance fixtures

The golden fixtures are protocol ABI tests, not tests against a running X server.

- `wire-vectors.json` covers selected request layouts, including CreateBuffer,
  ReadBuffer and WriteBuffer payload boundaries in both X11 byte orders.
- `event-vectors.json` covers all seven registered XGE event types in both
  byte orders. Fixture values for the extension opcode and event sequence are
  deliberately fixed test values; real connections supply their negotiated
  extension opcode and current sequence number.
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
- `test_reply_spec_coverage.py` derives status sets, memory-count limits/formulas,
  and ReadBuffer alignment expectations from the normative chapters, then requires
  golden fixtures for every status in both byte orders and maximum memory counts.
- `check-wire-layout.py` validates reply vectors against the 32-byte X11
  framing contract, declared lengths, enumeration/memory record formulas, fixed reply field offsets and status values,
  reserved fields, padding, required endian coverage, and intentionally malformed negative reply fixtures.
  Positive property replies exercise one- and five-byte BYTE_ARRAY boundaries plus the registered 16-byte UUID and three-element CARD32_ARRAY shapes, including zero padding and reply-word rounding.   Negative replies include variable device-record length/padding errors and memory-type heap indices outside the advertised heap range. Additional cases cover a truncated second device record, malformed queue-family record-array length, and nonzero ReadBuffer padding. The memory-property checks separately enforce zero `memory_properties_flags`, zero reserved fields, exact aggregate length, and valid type/heap flag masks. The memory-property checks also enforce exact aggregate length, zero reserved fields, and valid type/heap flag masks; queue-family flags and device-record reserved fields are checked too. Negative cases also cover ReadBuffer payload-size mismatches and nonzero NOT_AVAILABLE fields. Reserved-byte violations are also isolated per fence and both semaphore-wait reply statuses.

Run all fixture tests from the repository root:

```sh
python3 -m py_compile tools/check-wire-layout.py tests/test_wire_vectors.py tests/test_event_vectors.py tests/test_select_events_vectors.py tests/test_reply_vectors.py tests/test_reply_spec_coverage.py
python3 tools/check-wire-layout.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

A passing fixture suite proves consistency between the reference encoders and
the committed expected bytes. It does not establish interoperability with an
unimplemented client or server; a future implementation should consume these
fixtures as an independent wire-format oracle.
