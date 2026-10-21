# Wire conformance fixtures

The golden fixtures are protocol ABI tests, not tests against a running X server.

- `wire-vectors.json` covers selected request layouts, including CreateBuffer,
  ReadBuffer and WriteBuffer payload boundaries in both X11 byte orders.
- `event-vectors.json` covers all seven registered XGE event types in both
  byte orders. Fixture values for the extension opcode and event sequence are
  deliberately fixed test values; real connections supply their negotiated
  extension opcode and current sequence number.
- `reply-vectors.json` covers fixed fence/semaphore replies, padded ReadBuffer
  data, empty and populated physical-device enumeration, queue-family and memory-property
  records, property success, NOT_SUPPORTED/NOT_AVAILABLE failures, buffer requirements, WriteBuffer success, and
  semaphore timeout replies in both byte orders.
- `test_wire_vectors.py` checks request encoding, declared lengths, padding,
  and malformed request framing.
- `test_event_vectors.py` checks XGE header and payload encoding, total size,
  event IDs, reserved bytes, and malformed raw event framing.
- `test_reply_vectors.py` checks standard reply framing, fixed reply fields,
  variable payload lengths, record boundaries, padding, and malformed headers.
- `check-wire-layout.py` validates reply vectors against the 32-byte X11
  framing contract, declared lengths, enumeration/memory record formulas, fixed reply field offsets and status values,
  reserved fields, padding, required endian coverage, and intentionally malformed negative reply fixtures.

Run all fixture tests from the repository root:

```sh
python3 -m py_compile tools/check-wire-layout.py tests/test_wire_vectors.py tests/test_event_vectors.py tests/test_reply_vectors.py
python3 tools/check-wire-layout.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

A passing fixture suite proves consistency between the reference encoders and
the committed expected bytes. It does not establish interoperability with an
unimplemented client or server; a future implementation should consume these
fixtures as an independent wire-format oracle.
