#!/usr/bin/env python3
"""Regression guards for XAverius negative-test contracts.

These tests ensure the normative conformance matrix continues to specify the
high-risk precedence and atomic-rejection cases. They are contract/document
regression tests, not a substitute for tests against a live server/backend.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class NegativeContractRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.conformance = read("spec/conformance.md")
        cls.errors = read("spec/errors.md")
        cls.presentation = read("spec/presentation.md")

    def test_common_validation_stage_order_is_normative(self) -> None:
        for phrase in ("wire structure first", "field values", "field order"):
            with self.subTest(document="error mapping", contract=phrase):
                self.assertIn(phrase, self.errors)
        self.assertIn("framing before scalar syntax", self.conformance)
        self.assertIn("scalar syntax before XID resolution", self.conformance)
        self.assertIn("XID/type/ownership checks before lifecycle", self.conformance)

    def test_create_and_batch_rejection_preserves_public_xids(self) -> None:
        required = (
            "Failed creates leave target XIDs unallocated",
            "a failed create leaves the target XID unallocated",
        )
        joined = self.conformance + self.errors
        for phrase in required:
            with self.subTest(contract=phrase):
                self.assertIn(phrase, joined)

    def test_synchronization_request_precedence_matches_normative_phase_order(self) -> None:
        sync = read("spec/synchronization.md")
        queue = read("spec/queue-submission.md")
        errors = self.errors
        cases = (
            ("SignalSemaphore", sync.split("## `SignalSemaphore`", 1)[1].split("\n## ", 1)[0],
             errors.split("- `SignalSemaphore`:", 1)[1].split("\n- `WaitSemaphores`:", 1)[0],
             ("exact total length of 24 bytes", "resolve the device XID, then the semaphore XID",
              "check resource type, client/device ownership, and cross-device association",
              "check device state", "check timeline type and signal-value/reservation consistency")),
            ("WaitSemaphores", sync.split("## `WaitSemaphores`", 1)[1].split("\n## ", 1)[0],
             errors.split("- `WaitSemaphores`:", 1)[1].split("\n- `GetFenceStatus`:", 1)[0],
             ("length and checked arithmetic", "`semaphore_count != 0`", "resolve the device XID and then semaphore XIDs in array order",
              "check resource type, client/device ownership, and cross-device association",
              "check device state", "verify that all semaphores are timeline semaphores")),
        )
        for name, normative, mapped, phases in cases:
            with self.subTest(request=name):
                positions = [normative.find(phrase) for phrase in phases]
                self.assertTrue(all(position >= 0 for position in positions), positions)
                self.assertEqual(positions, sorted(positions))
                self.assertIn("device loss", normative.lower())
                self.assertIn("DEVICE_LOST", mapped)

        queue_phases = (
            "incorrect total length",
            "syntactic fields are checked",
            "required XIDs are resolved in wire order",
            "resource type, client/device ownership, and queue association",
            "unavailable or lost device takes precedence over mutable submission state",
            "first the optional fence state",
            "command buffers in array order",
            "wait entries in array order",
            "finally signal entries in array order",
        )
        queue_section = queue.split("Error precedence (the first applicable phase wins):", 1)[1].split("\n\n", 1)[0]
        positions = [queue_section.find(phrase) for phrase in queue_phases]
        self.assertTrue(all(position >= 0 for position in positions), positions)
        self.assertEqual(positions, sorted(positions))
        self.assertIn("QueueSubmit", errors)
        self.assertIn("DEVICE_LOST", queue_section)
        self.assertIn("rejected request is atomic", queue_section)

    def test_write_buffer_length_precedes_scalar_and_resource_errors(self) -> None:
        memory = read("spec/memory-buffers.md")
        write_spec = memory.split("## 5.7 `WriteBuffer`", 1)[1].split(
            "## 5.8 `ReadBuffer`", 1
        )[0]
        write_errors = self.errors.split("### `WriteBuffer`", 1)[1].split(
            "### `ReadBuffer`", 1
        )[0]
        for section_name, section in (("normative chapter", write_spec), ("error map", write_errors)):
            with self.subTest(section=section_name):
                length = section.index("BadLength")
                scalar = section.index("BadValue")
                xid = section.index("BadValue", scalar + 1) if section_name == "error map" else section.index("buffer MUST be bound")
                self.assertLess(length, scalar)
                self.assertLess(scalar, xid)
        self.assertIn("arithmetic wider than 32 bits", write_spec)
        self.assertIn("maximum X11 request length", write_spec)
        self.assertIn("Request-Gesamtlänge mit Überlauf", write_errors)

    def test_read_write_buffer_full_validation_precedence(self):
        memory = read("spec/memory-buffers.md")
        errors = self.errors
        cases = (
            ("WriteBuffer", "## 5.7 `WriteBuffer`", "### `WriteBuffer`", (
                "checked wide arithmetic",
                "`data_length > 0`",
                "resolve `device_xid`, then `buffer_xid` in wire order",
                "validate live resource types, client ownership, and device association",
                "check logical-device availability",
                "validate binding, `TRANSFER_DST` usage, and the overflow-safe buffer range",
                "perform the ordered transfer",
            ), (
                "total length with checked count/overflow arithmetic",
                "positive `data_length`",
                "`device_xid`, then `buffer_xid` in wire order",
                "live resource type, client ownership, and Device association",
                "Device state",
                "Buffer binding, `TRANSFER_DST`, and range",
                "transfer/synchronization work",
            )),
            ("ReadBuffer", "## 5.8 `ReadBuffer`", "### `ReadBuffer`", (
                "exact 28-byte request length",
                "`data_length > 0`",
                "resolve `device_xid`, then `buffer_xid` in wire order",
                "validate live resource types, client ownership, and device association",
                "check logical-device availability",
                "validate binding, `TRANSFER_SRC` usage, and the overflow-safe buffer range",
                "establish the required snapshot ordering and perform the read",
            ), (
                "exact 28-byte length",
                "positive `data_length`",
                "`device_xid`, then `buffer_xid` in wire order",
                "live resource type, client ownership, and Device association",
                "Device state",
                "Buffer binding, `TRANSFER_SRC`, and range",
                "snapshot/transfer work",
            )),
        )
        for name, heading, error_heading, memory_phases, error_phases in cases:
            section = memory.split(heading, 1)[1].split("\n## ", 1)[0]
            error_section = errors.split(error_heading, 1)[1].split("\n### ", 1)[0]
            for document, phrases in ((section, memory_phases), (error_section, error_phases)):
                positions = [document.find(phrase) for phrase in phrases]
                with self.subTest(request=name, phases=phrases):
                    self.assertTrue(all(position >= 0 for position in positions), positions)
                    self.assertEqual(positions, sorted(positions))
            with self.subTest(request=name, device_loss=True):
                self.assertIn("reported before binding/usage/range errors", section)
    def test_buffer_and_descriptor_mixed_failures_are_atomic(self) -> None:
        self.assertIn("BindBufferMemory", self.conformance)
        self.assertIn("UpdateDescriptorSets", self.conformance)
        self.assertIn("All rejected requests remain atomic and change no binding, descriptor slots, or internal references", self.conformance)

    def test_destroy_and_free_cleanup_remain_valid_after_device_loss(self) -> None:
        errors = read("spec/errors.md")
        memory = read("spec/memory-buffers.md")
        destroy = errors.split("### `DestroyResource`", 1)[1].split("\n### ", 1)[0]
        free = memory.split("## 5.5 `FreeMemory`", 1)[1].split("\n## ", 1)[0]
        destroy_phases = ("Falsche Request-Länge", "Ungültige oder nicht mehr live XID", "Ressourcentyp, der nicht für den generischen Request zugelassen ist", "Verstoß gegen die typabhängigen Recording-/Pending-Lebensdauerregeln", "Device Loss allein ist kein zusätzlicher Ablehnungsgrund")
        free_phases = ("exact 16-byte request length", "resolve `device_xid`, then `memory_xid`", "validate live resource types, client ownership, and device association", "internally live Buffer remains bound", "accepted GPU access that has not reached a terminal outcome", "Device loss alone is not a blanket rejection")
        for name, section, phrases in (("DestroyResource", destroy, destroy_phases), ("FreeMemory", free, free_phases)):
            with self.subTest(request=name):
                positions = [section.find(phrase) for phrase in phrases]
                self.assertTrue(all(position >= 0 for position in positions), positions)
                self.assertEqual(positions, sorted(positions))
        self.assertIn("sicheren Quieszenz", destroy)
        self.assertIn("quarantining the internal allocation", free)

    def test_destroy_device_cascade_and_late_callbacks_are_identity_safe(self) -> None:
        devices = read("spec/devices.md")
        lifetime = read("spec/resource-lifetime.md")
        section = devices.split("## `DestroyDevice`", 1)[1].split("\n## ", 1)[0]
        for phrase in (
            "single server-side linearization point",
            "cascading public invalidation",
            "wait already terminally established",
            "Accepted submissions are not cancelled",
            "MUST NOT enqueue a new event",
            "captured internal object identities rather than re-resolving numeric XIDs",
            "retained or quarantined",
        ):
            with self.subTest(contract=phrase):
                self.assertIn(phrase, section)
        for phrase in (
            "`DestroyDevice` cascade linearization",
            "A wait whose success, timeout, or Device-loss result was established first keeps that result",
            "MUST NOT mutate the new resource",
            "remain retained or quarantined until backend access is known to be impossible",
        ):
            with self.subTest(lifetime_contract=phrase):
                self.assertIn(phrase, lifetime)

    def test_device_teardown_drains_internal_resource_edges_before_memory_release(self) -> None:
        lifetime = read("spec/resource-lifetime.md")
        memory = read("spec/memory-buffers.md")
        for phrase in (
            "Cross-resource teardown and backing-memory release",
            "DescriptorSet XID does not by itself prove that its slot-held Buffer references",
            "retire descriptor-slot and recorded-command references",
            "MUST NOT release a bound Memory allocation before the old Buffer identity",
            "a publicly invalidated Buffer can remain internally live because a descriptor slot",
        ):
            with self.subTest(lifetime_contract=phrase):
                self.assertIn(phrase, lifetime)
        for phrase in (
            "Successful `FreeMemory` requires that no live internal buffer identity remains bound",
            "retire each Buffer-to-Memory binding exactly once",
            "MUST NOT invoke public `FreeMemory` semantics on an already invalidated child XID",
        ):
            with self.subTest(memory_contract=phrase):
                self.assertIn(phrase, memory)

    def test_queue_present_precedence_and_atomicity_matrix_is_complete(self) -> None:
        required = (
            "Device loss beats Surface loss and accepted-token reuse",
            "Surface loss and OUT_OF_DATE beat accepted-token reuse",
            "unsupported queue presentation capability is `BadMatch` before token reuse",
            "accepted-token reuse returns `BadValue` before image-state",
            "no request-attributable token reservation, wait reservation/consumption, or image transition",
            "A rejected request causes no partial state mutation attributable to that request",
        )
        for phrase in required:
            with self.subTest(contract=phrase):
                self.assertIn(phrase, self.conformance)

    def test_present_lifecycle_tests_cover_both_serialized_orders(self) -> None:
        required = (
            "If the lifecycle transition is serialized before acceptance",
            "if acceptance is serialized first",
            "first serialized terminal outcome",
            "exactly one terminal status",
            "independent lifecycle transitions that race with it are not rolled back",
        )
        for phrase in required:
            with self.subTest(contract=phrase):
                self.assertIn(phrase, self.conformance)

    def test_acquire_failures_do_not_signal_or_acquire(self) -> None:
        required = (
            "Every non-success result has zero `image_index`",
            "signals neither optional synchronization object",
            "must not acquire an image",
            "both synchronization objects unchanged and unsignaled",
        )
        for phrase in required:
            with self.subTest(contract=phrase):
                self.assertIn(phrase, self.conformance)

    def test_presentation_profile_is_explicitly_gated(self) -> None:
        self.assertIn("presentation-capable profile", self.presentation)
        self.assertIn("remain gated on the presentation-capable profile", self.presentation)
        self.assertIn("compute-only implementations", self.conformance)

    def test_rejected_wire_framing_has_no_side_effects(self) -> None:
        required = (
            "declared-length mismatch",
            "before payload allocation, XID lookup, or state mutation",
            "no partial resource creation, upload commit, command-buffer append/finalization",
        )
        for phrase in required:
            with self.subTest(contract=phrase):
                self.assertIn(phrase, self.conformance)


def first_common_request_error(
    *,
    envelope_valid=True,
    data=0,
    common_reserved=0,
    subopcode=1,
    presentation_supported=True,
    expected_request_bytes=16,
    actual_request_bytes=16,
    scalar_valid=True,
    xid_valid=True,
):
    """Small decision oracle for the shared precedence phases, not a server test."""
    if not envelope_valid:
        return "BadLength"
    if data != 0 or common_reserved != 0:
        return "BadValue"
    if 41 <= subopcode <= 47 and not presentation_supported:
        return "BadRequest"
    if actual_request_bytes != expected_request_bytes:
        return "BadLength"
    if not scalar_valid:
        return "BadValue"
    if not xid_valid:
        return "BadValue"
    return None


class CommonRequestErrorPrecedenceTests(unittest.TestCase):
    def test_envelope_bad_length_precedes_common_header_errors(self):
        self.assertEqual(
            first_common_request_error(
                envelope_valid=False, data=1, common_reserved=1,
                subopcode=41, presentation_supported=False,
            ),
            "BadLength",
        )

    def test_common_invariant_fields_precede_profile_gate_and_xid_lookup(self):
        self.assertEqual(
            first_common_request_error(
                data=1, subopcode=41, presentation_supported=False,
                xid_valid=False,
            ),
            "BadValue",
        )
        self.assertEqual(
            first_common_request_error(
                common_reserved=1, subopcode=41, presentation_supported=False,
                xid_valid=False,
            ),
            "BadValue",
        )

    def test_profile_gate_precedes_request_specific_payload_validation(self):
        self.assertEqual(
            first_common_request_error(
                subopcode=41, presentation_supported=False,
                expected_request_bytes=32, actual_request_bytes=8,
                scalar_valid=False, xid_valid=False,
            ),
            "BadRequest",
        )

    def test_supported_request_length_precedes_scalar_and_xid_errors(self):
        self.assertEqual(
            first_common_request_error(
                expected_request_bytes=32, actual_request_bytes=28,
                scalar_valid=False, xid_valid=False,
            ),
            "BadLength",
        )

    def test_request_scalar_errors_precede_xid_lookup(self):
        self.assertEqual(
            first_common_request_error(scalar_valid=False, xid_valid=False),
            "BadValue",
        )

    def test_checker_and_spec_define_same_common_phase_order(self):
        wire = read("spec/wire-protocol.md")
        checker = read("tools/check-wire-layout.py")
        errors = read("spec/errors.md")
        for phrase in (
            "## Common Request Validation Precedence",
            "Validate the X11 envelope independently of XAverius fields",
            "Validate the common-header fields that have invariant meanings",
            "These checks precede subopcode dispatch, profile gating, request-specific parsing",
            "The `flags` byte at offset 5 is request-specific",
            "An unsupported presentation request returns `BadRequest` before parsing",
            "validate its exact layout, request-specific lengths/counts and checked arithmetic",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, wire)
        self.assertIn("def check_common_request_error_precedence", checker)
        self.assertIn("check_common_request_error_precedence(c)", checker)
        self.assertIn("wire structure first, then field values, then XIDs in the field order", errors)




class RequestSpecificPrecedenceExceptionTests(unittest.TestCase):
    def test_create_resource_precedence_orders_target_xid_before_input_xids(self):
        memory = read("spec/memory-buffers.md")
        shaders = read("spec/shaders-pipelines.md")
        cases = (
            (memory, "## 5.1 `CreateBuffer`", ("exact request length", "`size`, `usage_flags`, and `reserved", "target `buffer_xid` as a create-XID", "`device_xid` lookup", "resource type and client/device ownership", "logical-device state", "backend buffer creation")),
            (memory, "## 5.4 `AllocateMemory`", ("exact request length", "`allocation_size`, `memory_type_index`, and `reserved", "target `memory_xid` as a create-XID", "`device_xid` lookup", "resource type and client/device ownership", "logical-device state", "backend allocation")),
            (shaders, "## 6.2 Descriptor Set Layout", ("exact count-consistent request length", "flags, binding records, counts, unique binding numbers", "target `descriptor_set_layout_xid` as a create-XID", "`device_xid` lookup", "resource type and client/device ownership", "logical-device state", "device-limit/descriptor support checks", "backend allocation")),
            (shaders, "## 6.3 Descriptor Pool", ("exakte count-konsistente Request-Länge", "positive Counts, doppelte Pool-Size-Typen", "Ziel-Pool-XID als Create-XID", "Device-XID (`BadValue` bei unbekannter/nicht-live XID)", "Ressourcentyp und Client-/Device-Ownership", "Device-Zustand", "Backend-Allokation")),
        )
        for document, heading, phrases in cases:
            section = document.split(heading, 1)[1].split(chr(10) + "## ", 1)[0]
            positions = [section.find(phrase) for phrase in phrases]
            self.assertTrue(all(position >= 0 for position in positions), heading)
            self.assertEqual(positions, sorted(positions), heading)

    def test_pipeline_and_shader_upload_precedence_is_normative(self):
        shaders = read("spec/shaders-pipelines.md")
        cases = (
            ("## 6.1 Shader Modules", ("exact total length `20 + pad4(data_length)`", "request-specific flag combination", "for `CREATE`, validate `shader_module_xid` as a create-XID", "resolve `device_xid`", "resource type and client/device ownership", "logical-device state", "upload-assembly state and chunk-size/aggregate-size limits", "on `FINAL`, validate the assembled SPIR-V")),
            ("## 6.7 `CreatePipelineLayout`", ("exakte, count-konsistente Wire-Länge", "reservierte Felder, nicht unterstützte Stage-Bits", "Ziel-XID (`BadIDChoice`)", "Device- und Set-Layout-XIDs in Wire-Reihenfolge", "Ressourcentyp, Ownership und Cross-Device-Zuordnung", "Device-Zustand", "geräteabhängige Limits und Vulkan-Kompatibilität", "Backend-Erstellung")),
            ("## 6.8 Compute Pipeline", ("exakte Wire-Länge", "positiven Entry-Point-Count", "Ziel-Pipeline-XID (`BadIDChoice`)", "Device-, Pipeline-Layout- und Shader-Module-XIDs in Wire-Reihenfolge", "Ressourcentyp, Ownership und Cross-Device-Zuordnung", "Device-Zustand", "Backend-Pipeline-Erstellung")),
        )
        for heading, phrases in cases:
            with self.subTest(request=heading):
                section = shaders.split(heading, 1)[1].split("\n## ", 1)[0]
                positions = [section.find(phrase) for phrase in phrases]
                self.assertTrue(all(position >= 0 for position in positions), positions)
                self.assertEqual(positions, sorted(positions))
        self.assertIn("before assembly lookup", shaders)
        self.assertIn("This device-loss rule overrides the generic missing-assembly sentence above.", shaders)

    def test_create_default_device_has_total_validation_precedence(self):
        devices = read("spec/devices.md")
        errors = read("spec/errors.md")
        section = devices.split("## `CreateDefaultDevice`", 1)[1].split("\n## ", 1)[0]
        phrases = (
            "validate the exact/formula-based request length using checked arithmetic",
            "validate `queue_count`, the reserved field, and every priority",
            "validate the target `device_xid` as a create-XID",
            "require successful XGE 1.0-or-later negotiation",
            "select a suitable physical device and compute-capable queue family",
        )
        positions = [section.find(phrase) for phrase in phrases]
        self.assertTrue(all(p >= 0 for p in positions))
        self.assertEqual(positions, sorted(positions))
        self.assertIn("invalid/occupied `device_xid` returns `BadIDChoice`", errors)
        self.assertIn("missing XGE negotiation returns `BadMatch`", errors)
        self.assertIn("no compute-capable device with `XAverius.timelineSemaphore = 1` and sufficient queue count returns `DEVICE_UNAVAILABLE`", errors)

    def test_signal_semaphore_keeps_xid_checks_before_value_reservation_checks(self):
        sync = read("spec/synchronization.md")
        section = sync.split("## `SignalSemaphore`", 1)[1].split("\n## ", 1)[0]
        phrases = (
            "exact total length of 24 bytes",
            "resolve the device XID, then the semaphore XID",
            "check resource type, client/device ownership",
            "check device state",
            "check timeline type and signal-value/reservation consistency",
        )
        positions = [section.find(phrase) for phrase in phrases]
        self.assertTrue(all(p >= 0 for p in positions), positions)
        self.assertEqual(positions, sorted(positions))

    def test_wait_semaphores_keeps_scalar_checks_before_xid_resolution(self):
        sync = read("spec/synchronization.md")
        section = sync.split("## `WaitSemaphores`", 1)[1].split("\n## ", 1)[0]
        phrases = (
            "length and checked arithmetic",
            "semaphore_count != 0",
            "resolve the device XID and then semaphore XIDs in array order",
            "check resource type, client/device ownership",
            "check device state",
            "verify that all semaphores are timeline semaphores",
        )
        positions = [section.find(phrase) for phrase in phrases]
        self.assertTrue(all(p >= 0 for p in positions), positions)
        self.assertEqual(positions, sorted(positions))

    def test_queue_submit_and_command_buffer_exceptions_are_explicit(self):
        queue = read("spec/queue-submission.md")
        command = read("spec/command-recording.md")
        self.assertIn("syntactic fields are checked", queue)
        self.assertIn("required XIDs are resolved in wire order", queue)
        self.assertIn("wire-structure errors take precedence over field errors", command)
        self.assertIn("target XID is checked before the pool XID", command)

    def test_presentation_statuses_follow_synchronous_validation(self):
        presentation = read("spec/presentation.md")
        section = presentation.split("## 5.3 Request validation, status precedence, and atomic acceptance", 1)[1].split("\n## ", 1)[0]
        phrases = (
            "wire length and checked arithmetic",
            "scalar/reserved-field validation",
            "XID resolution in the defined order",
            "type and ownership validation",
            "Device availability",
            "immutable request constraints",
            "lifecycle/capability status",
            "mutable state and synchronization eligibility",
        )
        positions = [section.find(phrase) for phrase in phrases]
        self.assertTrue(all(p >= 0 for p in positions), positions)
        self.assertEqual(positions, sorted(positions))

    def test_checker_audits_request_specific_precedence_exceptions(self):
        checker = read("tools/check-wire-layout.py")
        self.assertIn("def check_request_specific_precedence_exceptions", checker)
        self.assertIn("check_request_specific_precedence_exceptions(c)", checker)





    def test_create_default_device_validation_precedence_is_explicit_and_ordered(self):
        devices = read("spec/devices.md")
        section = devices.split("## `CreateDefaultDevice`", 1)[1].split("\n## ", 1)[0]
        phases = ("(1) validate the exact/formula-based request length", "(2) validate `queue_count`, the reserved field, and every priority", "(3) validate the target `device_xid` as a create-XID", "(4) require successful XGE 1.0-or-later negotiation", "(5) select a suitable physical device and compute-capable queue family")
        positions = [section.find(phase) for phase in phases]
        self.assertTrue(all(p >= 0 for p in positions), positions)
        self.assertEqual(positions, sorted(positions))
        self.assertIn("that can supply the requested `queue_count`", section)
        self.assertIn("if no such combination is available, it reports `DEVICE_UNAVAILABLE`", section)
        checker = read("tools/check-wire-layout.py")
        self.assertIn("def check_create_default_device_precedence", checker)
        self.assertIn("check_create_default_device_precedence(c)", checker)

    def test_create_device_validation_precedence_is_explicit_and_ordered(self):
        devices = read("spec/devices.md")
        section = devices.split("## `CreateDevice`", 1)[1].split("\n## ", 1)[0]
        phases = (
            "1. Validate the complete variable-length request framing",
            "2. Validate wire-level and scalar fields",
            "An unknown feature ID, because no optional feature IDs are assigned in v0.1",
            "3. Validate `device_xid` as a create-XID",
            "4. Resolve `physical_device_xid`",
            "5. Validate that the XID is a Physical-Device resource",
            "6. Require successful XGE 1.0-or-later negotiation",
            "7. Check physical-device availability",
            "8. Validate every requested queue-family index and queue count",
            "9. Check the mandatory v0.1 baseline capability",
            "10. Only after all prior checks succeed may backend device creation begin",
        )
        positions = [section.find(phrase) for phrase in phases]
        self.assertTrue(all(position >= 0 for position in positions), positions)
        self.assertEqual(positions, sorted(positions))
        self.assertIn("unknown feature ID takes precedence over target-XID occupancy", section)
        self.assertIn("target-XID validation precedes physical-device lookup", section)
        self.assertIn("In v0.1 every syntactically valid client extension name is unregistered", section)
        checker = read("tools/check-wire-layout.py")
        self.assertIn("def check_create_device_precedence", checker)
        self.assertIn("check_create_device_precedence(c)", checker)

    def test_command_buffer_reset_invalidation_and_rerecording_retire_references_once(self):
        command = read("spec/command-recording.md")
        lifetime = read("spec/resource-lifetime.md")
        queue = read("spec/queue-submission.md")
        for phrase in (
            "retires the command buffer's recorded-resource reference edges exactly once",
            "A rejected reset, including reset of a PENDING buffer",
            "A subsequent successful rerecording begins from INITIAL and builds a fresh reference set",
            "If submission acceptance wins, reset is rejected while the command buffer is PENDING.",
        ):
            with self.subTest(contract=phrase):
                self.assertIn(phrase, command)
        self.assertIn("reset MUST NOT retire those same edges again", lifetime)
        self.assertIn("Command-buffer reference retirement is separate from submission terminalization", queue)
        checker = read("tools/check-wire-layout.py")
        self.assertIn("def check_command_buffer_reference_retirement", checker)
        self.assertIn("check_command_buffer_reference_retirement(c)", checker)

class CommandBufferEntryRequestLimitTests(unittest.TestCase):
    def test_maximum_entry_accounts_for_fixed_command_buffer_request_header(self):
        command = read("spec/command-recording.md")
        wire = read("spec/wire-protocol.md")
        registry = read("registries/command-entries.md")
        conformance = read("spec/conformance.md")

        self.assertIn("Maximum entry size: 65531 words (262124 bytes)", command)
        self.assertIn("16-byte fixed request header (four 32-bit words)", command)
        self.assertIn("maximum ordinary request length is 262140 bytes", wire)
        self.assertIn("at most 65531 words (262124 bytes)", registry)
        self.assertIn("`entry_length = 65531` words", conformance)
        self.assertIn("`entry_length = 65532`", conformance)
        self.assertIn("aggregate exceeds 65531 words", conformance)

        maximum_request_bytes = 16 + 65531 * 4
        first_unrepresentable_request_bytes = 16 + 65532 * 4
        self.assertEqual(maximum_request_bytes, 262140)
        self.assertGreater(first_unrepresentable_request_bytes, 262140)


class CommandBufferEmbeddedXidPrecedenceTests(unittest.TestCase):
    def test_embedded_entry_xids_are_resolved_before_type_and_device_checks(self):
        command = read("spec/command-recording.md")
        errors = read("spec/errors.md")
        conformance = read("spec/conformance.md")

        self.assertIn("then every resource XID embedded in command entries in entry order and field order", command)
        self.assertIn("CMD_BIND_DESCRIPTOR_SETS", command)
        self.assertIn("resolves its Pipeline-Layout XID followed by Descriptor-Set XIDs in array order", command)
        self.assertIn("every required XID has been resolved", errors)
        self.assertIn("embedded command-entry XIDs in entry order and field order", errors)
        self.assertIn("Resolve all required XIDs before checking live resource types", conformance)
        self.assertIn("Device state, which precedes command-buffer state and resource-dependent entry compatibility", conformance)


if __name__ == "__main__":
    unittest.main(verbosity=2)
