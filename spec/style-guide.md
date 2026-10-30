# Specification Language and Layout Style Guide

This guide is normative for the editorial structure of every current and future file under `spec/` and `registries/`. It does not change protocol semantics or wire assignments.

## Language

- New or materially revised normative specification text MUST be written in English, including headings, prose, table headings, captions, comments in examples, and status descriptions. Existing legacy German passages may remain during this finalization pass when their normative meaning is unambiguous; a change to such a passage MUST preserve its normative force and must not introduce a second interpretation.
- Historical source material under `wip/` may remain in its original language, but MUST be clearly marked historical and non-normative.
- Use the RFC 2119/8174 keywords **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** only when they carry their normative meaning; use uppercase spelling for that meaning.
- Use one term consistently for each concept. Prefer the terms and spellings already established in the normative chapters and registries; do not alternate between German and English names for the same wire field within one rule.
- New explanatory material SHOULD be in English. Existing German explanatory material may remain where it does not obscure a normative requirement; historical working notes belong outside the normative specification.

## Request chapter structure

Where applicable, describe each request in this order:

1. Purpose and profile availability.
2. Request type and exact total length, including whether it is a void request or returns a reply.
3. Request field table.
4. Variable-length record layouts and exact length formulae.
5. Validation rules and error precedence.
6. State transitions, atomicity, and asynchronous completion behavior.
7. Reply or event layout, if any.
8. Cross-references to central registries and shared rules.

Omit sections that do not apply, but do not reorder sections without a reason. Define shared framing and common header fields in `wire-protocol.md`; request chapters MUST NOT restate common-header fields as if they were request-specific payload.

## Wire-field tables

Use this exact header for absolute request/reply/event offsets:

```markdown
| Offset | Type | Field |
|---:|---|---|---|
```

Use this exact header for offsets relative to the beginning of a variable-length record:

```markdown
| Relative Offset | Type | Field |
|---:|---|---|---|
```

- Use decimal byte offsets unless the protocol explicitly defines another unit.
- Use `CARD8`, `CARD16`, `CARD32`, `CARD64`, `FLOAT32`, `BYTE[n]`, `XID`, and other registered wire types exactly as defined by the protocol.
- Put the wire field name in backticks. Put constraints, reserved-value requirements, and semantic meaning in the Field cell after the field name, separated by a semicolon where useful.
- For a fixed layout, list every field and every reserved/padding range. For variable payloads, specify the start offset, record size or formula, alignment, and padding requirements.
- Do not mix prose-style field lists and tables for equivalent fixed layouts in neighboring request definitions. Use the canonical table unless the layout is a compact repeated record embedded in a larger request and the same field-list format is used consistently for that record family.

## Consistency and maintenance

- Keep numeric IDs and supported values in central registries; chapter text references them rather than creating parallel assignments.
- State exact total lengths and use checked arithmetic for variable-length payloads.
- Use the same spelling and error name wherever a rule is referenced. When error precedence matters, state the ordered validation phases explicitly.
- Any editorial-only change MUST preserve wire layouts, field values, error precedence, state transitions, and normative force.
- Update the conformance tests or static checker when a layout or language/style invariant can be checked mechanically.
