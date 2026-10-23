# XGE interoperability test plan

This plan is the implementation-level follow-up for the static XGE ABI checks. It does not change the protocol contract or assign new IDs.

## Preconditions and test setup

- Use an X11 server/client pair with XGE support and an XAverius implementation.
- Run each client connection in both byte orders where the X11 test harness supports separate connections configured that way.
- Do not assume any fixed XAverius major opcode. Discover it independently on each connection using standard `QueryExtension("XAverius")`.
- Record the server, X server version, XGE version, client byte order, negotiated extension opcode, request sequence numbers, and captured raw packets for every failure.

## Required positive cases

1. **Extension discovery:** `QueryExtension` reports XAverius present; the returned major opcode is in 128..255. Send a harmless known request using that returned value and confirm the server dispatches by the subopcode at byte offset 4, not by the X11 `data` byte.
2. **XGE negotiation:** issue `GEQueryVersion` and verify successful negotiation of at least XGE 1.0 before attempting `CreateDevice`, `CreateDefaultDevice`, or `SelectEvents`.
3. **Selection request:** send the 32-byte `SelectEvents` request for each supported scope. Verify the standard X11 length is 8 words, `data`, flags and reserved fields are zero, and all multibyte fields follow the connection byte order.
4. **Dynamic event opcode:** trigger each available XAverius event and confirm XGE header byte 1 equals that connection's QueryExtension major opcode. Do not compare against fixture value 0x90.
5. **XGE framing:** verify response type 35, 16-bit sequence, 32-bit XGE length at offset 4, 16-bit event type at offset 8, zero reserved bytes at offsets 10..31, and exact total bytes `32 + 4 * length`. Check every event type implemented by the server against its registered size and offsets.
6. **Event masks:** verify connection-, device-, and queue-scoped events go only to the matching selection. Verify a successful zero mask clears only its selected scope and that replacing one scope does not alter other scopes.
7. **Terminal-event exclusivity:** for accepted submissions, verify no submission produces both `SUBMISSION_COMPLETE` and `SUBMISSION_FAILED`. Test event-send failure or client disconnect separately from the internal terminal outcome.
8. **Connection isolation:** create two clients with distinct masks. Confirm neither client receives the other's selected events and that a late backend completion cannot enqueue an event onto a closed or different connection.

## Required negative cases

- Before successful XGE negotiation, `CreateDevice`, `CreateDefaultDevice`, and `SelectEvents` return `BadMatch`; a rejected `SelectEvents` leaves the prior selection unchanged.
- Reject malformed `SelectEvents` length, nonzero `data`/flags/reserved fields, unknown scope, scope-incompatible nonzero fields, and mask bits unsupported by the active profile.
- Reject a valid-range but wrong extension opcode in a captured/decoded event when validating against the connection's negotiated opcode.
- Reject XGE frames with response type other than 35, mismatched declared length, nonzero reserved bytes, unknown event type, or event-specific size mismatch.
- Confirm errors preserve the original request sequence and report the dynamically assigned major opcode plus the request subopcode in the standard X11 error fields.

## Evidence and pass criteria

For each case, save the raw request/reply/event bytes and the decoded field table. A case passes only when both the wire bytes and the observed behavior match the normative specification. Static golden-vector tests alone do not satisfy this plan. Until this plan is run against an actual implementation, live XGE interoperability remains open.
