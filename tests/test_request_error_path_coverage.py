#!/usr/bin/env python3
"""Guard the remaining resource-lifetime negative-test matrix against error-map drift."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RequestErrorPathCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.errors = (ROOT / "spec/errors.md").read_text(encoding="utf-8")
        cls.conformance = (ROOT / "spec/conformance.md").read_text(encoding="utf-8")
        cls.lifetime = (ROOT / "spec/resource-lifetime.md").read_text(encoding="utf-8")

    def test_each_added_negative_path_is_present_and_mapped(self):
        cases = {
            "FreeMemory": ("BadMatch", "INVALID_SYNCHRONIZATION_STATE"),
            "BindBufferMemory": ("BadLength", "BadValue", "BadMatch", "DEVICE_LOST"),
            "DestroyResource": ("BadValue", "BadMatch", "INVALID_SYNCHRONIZATION_STATE"),
            "FreeDescriptorSets": ("BadMatch", "INVALID_SYNCHRONIZATION_STATE"),
            "DestroyDescriptorPool": ("INVALID_SYNCHRONIZATION_STATE",),
            "ResetFence": ("INVALID_SYNCHRONIZATION_STATE",),
            "DestroyFence": ("INVALID_SYNCHRONIZATION_STATE",),
        }
        section = self.conformance.split(
            "## Remaining request error-path negative tests", 1
        )[1]
        for request, outcomes in cases.items():
            with self.subTest(request=request):
                self.assertIn("`" + request + "`", section)
                self.assertIn("`" + request + "`", self.errors)
                for outcome in outcomes:
                    self.assertIn(outcome, section)
                    self.assertIn(outcome, self.errors)

    def test_batch_and_lifetime_failures_require_atomic_rejection(self):
        section = self.conformance.split(
            "## Remaining request error-path negative tests", 1
        )[1]
        self.assertIn("no earlier Set freed", section)
        self.assertIn("Pool, all child Sets, and all Pool capacity accounting remain unchanged", section)
        self.assertIn("Bei Ablehnung bleibt die Allokation unverändert", self.errors)
        self.assertIn("no partial free", section)

    def test_memory_free_checks_internal_buffer_liveness(self):
        self.assertIn(
            "intern noch lebender, gebundener Buffer", self.errors
        )
        self.assertIn(
            "internally live Buffer remains bound", self.conformance
        )
        self.assertIn("FreeMemory", self.lifetime)

    def test_sync_status_query_precedence_matches_error_map(self):
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        errors = self.errors
        conformance = self.conformance

        fence = synchronization.split("## `GetFenceStatus`", 1)[1].split("\n## ", 1)[0]
        fence_phases = (
            "exact total length (`BadLength`)",
            "resolve Device XID, then Fence XID in wire order (`BadValue`",
            "validate live resource types, client ownership, and Device association (`BadMatch`)",
            "atomically snapshot the server-stored Fence state",
        )
        positions = [fence.find(phase) for phase in fence_phases]
        self.assertTrue(all(position >= 0 for position in positions), positions)
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Device Loss is not an error for this state-only query", fence)

        counter = synchronization.split("## `GetSemaphoreCounterValue`", 1)[1].split("\n## ", 1)[0]
        counter_phases = (
            "exact total length (`BadLength`)",
            "resolve Device XID, then Semaphore XID in wire order (`BadValue`",
            "validate live resource type, client ownership, and Device association (`BadMatch`)",
            "check Device state (`DEVICE_LOST`)",
            "require a Timeline semaphore (`BadMatch`)",
        )
        positions = [counter.find(phase) for phase in counter_phases]
        self.assertTrue(all(position >= 0 for position in positions), positions)
        self.assertEqual(positions, sorted(positions))
        self.assertIn("serialized against Device Loss", counter)
        self.assertIn("GetFenceStatus", errors)
        self.assertIn("GetSemaphoreCounterValue", errors)
        self.assertIn("Device Loss is not an error", conformance)
        self.assertIn("counter snapshot", conformance)

    def test_wait_for_fence_and_destroy_fence_precedence_matches_error_map(self):
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        errors = self.errors
        wait = synchronization.split("## `WaitForFence`", 1)[1].split("\n## ", 1)[0]
        destroy = synchronization.split("## Destroying Fences", 1)[1].split("\n## ", 1)[0]
        wait_errors = errors.split("- `WaitForFence`:", 1)[1].split("\n- `DestroyFence`:", 1)[0]
        destroy_errors = errors.split("- `DestroyFence`:", 1)[1].split("\n- `DestroySemaphore`:", 1)[0]

        wait_phases = (
            "exact total length (`BadLength`)",
            "resolve Device XID, then Fence XID in wire order (`BadValue`",
            "validate live resource types, client ownership, and Device association (`BadMatch`)",
            "inspect Device state and the Fence/wait outcome",
        )
        positions = [wait.find(phase) for phase in wait_phases]
        self.assertTrue(all(position >= 0 for position in positions), positions)
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Device loss yields the normal reply status `DEVICE_LOST`, even if the Fence is already `FAILED`", wait)
        self.assertIn("Device Loss has already been detected and established as the terminal result", wait)
        self.assertIn("Device loss returns normal reply status `DEVICE_LOST`, even if the stored Fence state is `FAILED`", wait_errors)
        self.assertIn("Device Loss has already been detected and established as terminal", wait_errors)

        destroy_phases = (
            "exact total length (`BadLength`)",
            "resolve Device XID, then Fence XID (`BadValue`",
            "validate live resource types, client ownership, and Device association (`BadMatch`)",
            "validate lifetime blockers (`INVALID_SYNCHRONIZATION_STATE`)",
        )
        positions = [destroy.find(phase) for phase in destroy_phases]
        self.assertTrue(all(position >= 0 for position in positions), positions)
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Device Loss alone is not an error for this logical cleanup request", destroy)
        self.assertIn("finally check lifetime blockers (`INVALID_SYNCHRONIZATION_STATE`", destroy_errors)
        self.assertIn("Device Loss alone is not an error for this logical cleanup request", destroy_errors)

    def test_fence_destroy_boundary_is_serialized_wait_result(self):
        self.assertIn("terminal result has been serialized", self.conformance)
        self.assertIn("an unsent reply alone does not keep destruction blocked", self.conformance)
        self.assertIn("offene `WaitForFence`-Registrierung", self.errors)

    def test_create_device_error_precedence_matches_device_chapter(self):
        devices = (ROOT / "spec/devices.md").read_text(encoding="utf-8")
        errors = self.errors
        device_order = [
            "Validate the complete variable-length request framing",
            "Validate wire-level and scalar fields",
            "Validate `device_xid` as a create-XID",
            "Resolve `physical_device_xid`",
            "Validate that the XID is a Physical-Device resource",
            "Require successful XGE 1.0-or-later negotiation",
            "Check physical-device availability",
            "Validate every requested queue-family index and queue count",
            "Check requested registry-defined features and extensions",
            "Only after all prior checks succeed may backend device creation begin",
        ]
        errors_order = [
            "Validate complete request framing using checked arithmetic",
            "Validate wire-level and scalar fields",
            "Validate create-XID `device_xid`",
            "Resolve `physical_device_xid`",
            "Validate that the resolved XID is a Physical-Device resource",
            "Require successful XGE 1.0-or-later negotiation",
            "Check Physical-Device availability",
            "Validate queue-family indices and requested queue counts",
            "Validate registered feature support and extension registration/support",
            "Only after all validation succeeds may backend creation begin",
        ]
        device_section = devices.split("### Normative validation precedence", 1)[1].split("\n\nBefore creation", 1)[0]
        error_section = errors.split("The following error precedence applies to `CreateDevice`", 1)[1].split("\n\n## Request-spezifische Fehlerzuordnung", 1)[0]
        for phrase in device_order:
            self.assertIn(phrase, device_section)
        device_positions = [device_section.index(phrase) for phrase in device_order]
        self.assertEqual(device_positions, sorted(device_positions), "devices.md phase order must be normative")
        for phrase in errors_order:
            self.assertIn(phrase, error_section)
        for earlier, later in zip(errors_order, errors_order[1:]):
            self.assertLess(error_section.index(earlier), error_section.index(later))
        # The conformance oracle must preserve the specific mixed-failure outcomes.
        conformance = self.conformance.split("## `CreateDevice` mixed-failure and atomicity tests", 1)[1].split("\n\n- A server without", 1)[0]
        for phrase in (
            "Malformed total length plus an invalid or occupied `device_xid` → `BadLength`",
            "Invalid or occupied `device_xid` plus unknown `physical_device_xid` → `BadIDChoice`",
            "Unknown `physical_device_xid` plus missing XGE 1.0 negotiation → `BadValue`",
            "An unavailable Physical Device plus a well-formed but unsupported queue/feature/extension request → `DEVICE_UNAVAILABLE`",
        ):
            with self.subTest(mixed_failure=phrase):
                self.assertIn(phrase, conformance)

    def test_discovery_allocation_and_transfer_negative_matrix(self):
        section = self.conformance.split(
            "## Discovery, allocation, and transfer rejection matrix", 1
        )[1]
        cases = {
            "EnumeratePhysicalDevices": ("UTF-8", "empty reply"),
            "GetPhysicalDeviceProperty": ("BadAtom", "NOT_SUPPORTED", "NOT_AVAILABLE"),
            "GetPhysicalDeviceQueueFamilyProperties": ("BadLength", "BadValue", "BadMatch"),
            "GetPhysicalDeviceMemoryProperties": ("BadLength", "BadValue", "BadMatch"),
            "CreateDefaultDevice": ("BadValue", "BadIDChoice", "DEVICE_UNAVAILABLE"),
            "CreateBuffer": ("BadLength", "BadValue", "BadIDChoice", "DEVICE_LOST", "ALLOCATION_FAILED"),
            "AllocateMemory": ("BadLength", "BadValue", "BadIDChoice", "DEVICE_LOST", "ALLOCATION_FAILED"),
            "GetBufferMemoryRequirements": ("BadLength", "BadValue", "BadMatch"),
            "ReadBuffer": ("BadLength", "BadValue", "BadMatch", "DEVICE_LOST", "TRANSFER_FAILED", "ALLOCATION_FAILED", "DEPENDENCY_FAILED"),
            "UpdateDescriptorSets": ("DEVICE_LOST", "INVALID_SYNCHRONIZATION_STATE"),
        }
        for request, outcomes in cases.items():
            with self.subTest(request=request):
                self.assertIn("`" + request + "`", section)
                self.assertIn("`" + request + "`", self.errors)
                for outcome in outcomes:
                    self.assertIn(outcome, section)

    def test_buffer_memory_requirements_precedence_and_device_loss_contract(self):
        memory = (ROOT / "spec/memory-buffers.md").read_text(encoding="utf-8")
        errors = self.errors
        section = memory.split("## 5.3 `GetBufferMemoryRequirements`", 1)[1].split("\n## ", 1)[0]
        error_section = errors.split("- `GetBufferMemoryRequirements`:", 1)[1].split("\n- `AllocateMemory`:", 1)[0]
        memory_phases = (
            "exact 16-byte request length",
            "resolve `device_xid`, then `buffer_xid` in wire order",
            "validate live resource types, client ownership, and device association",
            "return the buffer's stored memory-requirement metadata",
        )
        error_phases = (
            "exakte 16-Byte-Länge",
            "Device-XID, dann Buffer-XID in Wire-Reihenfolge",
            "Ressourcentyp, Ownership und Device-Zuordnung",
            "gespeicherte Requirements zurückgeben",
        )
        for document, phrases in ((section, memory_phases), (error_section, error_phases)):
            positions = [document.find(phrase) for phrase in phrases]
            self.assertTrue(all(position >= 0 for position in positions), positions)
            self.assertEqual(positions, sorted(positions))
        self.assertIn("MUST NOT start backend work", section)
        self.assertIn("remains valid after logical-device loss", section)
        self.assertIn("keine Backend-Arbeit", error_section)
        self.assertIn("bei Device Loss zulässig", error_section)

    def test_physical_device_property_error_precedence_is_explicit_and_consistent(self):
        devices = (ROOT / "spec/devices.md").read_text(encoding="utf-8")
        errors = self.errors
        section = devices.split("## `GetPhysicalDeviceProperty`", 1)[1].split("\n## ", 1)[0]
        phases = (
            "exact 16-byte request length (`BadLength`)",
            "resolve the Physical-Device XID (`BadValue` if unknown or non-live)",
            "validate that the live resource is a Physical Device (`BadMatch` otherwise)",
            "validate `property_atom` as a server-known X11 Atom (`BadAtom` if invalid)",
            "look up the Atom name in the XAverius property registry",
        )
        positions = [section.find(phase) for phase in phases]
        self.assertTrue(all(position >= 0 for position in positions), positions)
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Physical-Device XID resolution (`BadValue` for unknown/non-live XIDs)", errors)
        self.assertIn("Atom (`BadAtom` if invalid)", section)
        self.assertIn("takes precedence over an invalid Atom", errors)
        conformance = (ROOT / "spec/conformance.md").read_text(encoding="utf-8")
        for mixed_case in ("malformed length + invalid Atom → `BadLength`", "unknown Device + invalid Atom → `BadValue`", "live non-Physical-Device XID + invalid Atom → `BadMatch`", "valid Physical Device + invalid Atom → `BadAtom`"):
            self.assertIn(mixed_case, conformance)
        self.assertIn("NOT_SUPPORTED", section)
        self.assertIn("NOT_AVAILABLE", section)

    def test_discovery_and_memory_request_names_match_registry(self):
        registry = (ROOT / "registries/request-subopcodes.md").read_text(encoding="utf-8")
        names = (
            "EnumeratePhysicalDevices", "GetPhysicalDeviceProperty",
            "GetPhysicalDeviceQueueFamilyProperties", "GetPhysicalDeviceMemoryProperties",
            "CreateDefaultDevice", "CreateBuffer", "AllocateMemory",
            "GetBufferMemoryRequirements", "ReadBuffer", "UpdateDescriptorSets",
        )
        for name in names:
            with self.subTest(request=name):
                self.assertIn("`" + name + "`", registry)
                self.assertIn("`" + name + "`", self.conformance)


    def test_presentation_request_error_paths_match_registry(self):
        presentation = (ROOT / "spec/presentation.md").read_text(encoding="utf-8")
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        registry = (ROOT / "registries/request-subopcodes.md").read_text(encoding="utf-8")
        cases = {
            "CreateSurface": ("BadIDChoice", "BadWindow", "BadMatch"),
            "DestroySurface": ("BadValue", "BadMatch", "INVALID_SYNCHRONIZATION_STATE"),
            "GetSurfaceCapabilities": ("BadValue", "BadMatch", "SURFACE_LOST", "DEVICE_LOST"),
            "CreateSwapchain": ("BadIDChoice", "BadValue", "BadMatch", "OUT_OF_DATE", "SURFACE_LOST", "DEVICE_LOST", "ALLOCATION_FAILED", "UNSUPPORTED_CONFIGURATION"),
            "DestroySwapchain": ("BadValue", "BadMatch", "INVALID_SYNCHRONIZATION_STATE"),
            "AcquireNextImage": ("BadValue", "BadMatch", "INVALID_SYNCHRONIZATION_STATE", "NOT_READY", "TIMEOUT", "OUT_OF_DATE", "SURFACE_LOST", "DEVICE_LOST", "DEVICE_DESTROYED"),
            "QueuePresent": ("BadValue", "BadMatch", "INVALID_SYNCHRONIZATION_STATE", "DEPENDENCY_FAILED", "OUT_OF_DATE", "SURFACE_LOST", "DEVICE_LOST"),
        }
        for subopcode, (request, outcomes) in enumerate(cases.items(), start=41):
            with self.subTest(request=request):
                self.assertIn("`" + request + "`", registry)
                self.assertIn("`" + request + "`", presentation)
                self.assertIn("`" + request + "`", self.errors)
                self.assertIn(f"`{request}` | {subopcode} |", registry)
                for outcome in outcomes:
                    self.assertIn(outcome, self.errors)
                    self.assertTrue(
                        outcome in presentation or outcome in synchronization,
                        f"{outcome} has no presentation/synchronization contract",
                    )

    def test_presentation_rejections_preserve_state_and_status_is_not_x11_error(self):
        presentation = (ROOT / "spec/presentation.md").read_text(encoding="utf-8")
        self.assertIn("leaves the target XID unallocated", presentation)
        self.assertIn("no partial object, reference, image-state, synchronization-state, or token change", self.errors)
        self.assertIn("Token uniqueness is checked against previously accepted presentations", self.errors)
        self.assertIn("first terminal result serialized", self.errors)
        self.assertIn("QueuePresent reply status values are 0 SUCCESS", presentation)
        self.assertIn("normal reply statuses", self.errors)


    def test_synchronization_request_rejection_matrix_matches_registry(self):
        registry = (ROOT / "registries/request-subopcodes.md").read_text(encoding="utf-8")
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        section = self.conformance.split(
            "## Synchronization request rejection matrix", 1
        )[1]
        cases = {
            "CreateSemaphore": ("BadLength", "BadValue", "BadIDChoice", "ALLOCATION_FAILED"),
            "CreateFence": ("BadLength", "BadValue", "BadIDChoice", "ALLOCATION_FAILED"),
            "SignalSemaphore": ("BadMatch", "DEVICE_LOST", "INVALID_SYNCHRONIZATION_STATE"),
            "WaitSemaphores": ("BadLength", "BadValue", "BadMatch", "DEVICE_LOST"),
            "WaitForFence": ("BadLength", "BadValue", "BadMatch", "TIMEOUT", "DEVICE_LOST", "DEVICE_DESTROYED"),
            "GetFenceStatus": ("BadLength", "BadValue", "BadMatch"),
            "GetSemaphoreCounterValue": ("BadLength", "BadValue", "BadMatch", "DEVICE_LOST"),
            "ResetFence": ("BadLength", "BadValue", "BadMatch", "DEVICE_LOST", "INVALID_SYNCHRONIZATION_STATE"),
            "DestroyFence": ("BadLength", "BadValue", "BadMatch", "INVALID_SYNCHRONIZATION_STATE"),
            "DestroySemaphore": ("BadLength", "BadValue", "BadMatch", "INVALID_SYNCHRONIZATION_STATE"),
        }
        for request, outcomes in cases.items():
            with self.subTest(request=request):
                self.assertIn("`" + request + "`", registry)
                self.assertIn("`" + request + "`", synchronization)
                self.assertIn("`" + request + "`", section)
                self.assertIn("`" + request + "`", self.errors)
                for outcome in outcomes:
                    self.assertIn(outcome, section)
                    self.assertIn(outcome, self.errors)

    def test_synchronization_rejections_preserve_wait_and_signal_state(self):
        section = self.conformance.split(
            "## Synchronization request rejection matrix", 1
        )[1]
        for phrase in (
            "Every rejection leaves the target XID unallocated",
            "counter and all reservations remain unchanged",
            "No synchronous rejection may install a wait registration",
            "all rejections preserve the stored state",
            "an unsent reply alone must not block destruction",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)


    def test_wait_semaphores_check_registration_race_is_closed(self):
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        errors = self.errors
        conformance = self.conformance

        wait = synchronization.split("## `WaitSemaphores`", 1)[1].split("\n## ", 1)[0]
        for phrase in (
            "initial condition check and installation of the open wait registration MUST be one atomic operation",
            "visible to the initial condition check",
            "observe the installed registration and trigger its reevaluation",
            "MUST NOT install a wait registration",
            "no callback can terminalize a cancelled or already-terminal registration",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, wait)

        self.assertIn("prevents lost wakeups", errors)
        self.assertIn("never be lost between check and registration", conformance)
        self.assertIn("callback after cancellation or terminalization", conformance)


    def test_reset_fence_device_loss_precedes_mutable_fence_state(self):
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        errors = self.errors
        section = synchronization.split("## `ResetFence`", 1)[1].split("\n## ", 1)[0]
        error_section = errors.split("- `ResetFence`:", 1)[1].split("\n- `WaitForFence`:", 1)[0]
        phases = (
            "exact total length (`BadLength`)",
            "resolve Device XID, then Fence XID (`BadValue`",
            "validate live resource types, client ownership, and Device association (`BadMatch`)",
            "check Device state (`DEVICE_LOST`)",
            "validate the mutable Fence state",
        )
        positions = [section.find(phase) for phase in phases]
        self.assertTrue(all(position >= 0 for position in positions), positions)
        self.assertEqual(positions, sorted(positions))
        self.assertIn("`DEVICE_LOST` takes precedence over the Fence state", error_section)
        self.assertIn("reset from `PENDING` or `UNSIGNALED` results in `INVALID_SYNCHRONIZATION_STATE`", section)

    def test_reset_fence_is_serialized_with_submission_completion_and_stale_callbacks(self):
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        queue = (ROOT / "spec/queue-submission.md").read_text(encoding="utf-8")
        conformance = self.conformance
        reset = synchronization.split("## `ResetFence`", 1)[1].split("\n## ", 1)[0]
        terminal = queue.split("**Atomic terminal transition:**", 1)[1].split("\n## ", 1)[0]

        for phrase in (
            "form one serialized atomic operation against submission terminalization and new `QueueSubmit` acceptance",
            "if the Fence is `PENDING` at the operation's linearization point, reset is rejected",
            "Each Fence has an internal, non-wire-visible use generation",
            "A completion/failure callback may update the Fence only if",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, reset)

        for phrase in (
            "captured internal Fence identity, internal use generation, and submission association",
            "MUST be ignored even if the numeric Fence XID has since been reused",
            "one atomic terminalization step",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, terminal)

        self.assertIn("`ResetFence` gegen den terminalen Submission-Callback", conformance)
        self.assertIn("verspätete oder doppelte Callbacks der alten Submission", conformance)
        self.assertIn("weder `FAILED` zurück auf `SIGNALED` setzen", conformance)


    def test_signal_semaphore_counter_and_reservation_errors_have_distinct_precedence(self):
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        queue = (ROOT / "spec/queue-submission.md").read_text(encoding="utf-8")
        errors = self.errors
        signal_section = synchronization.split("## `SignalSemaphore`", 1)[1].split("\n## ", 1)[0]
        error_section = errors.split("- `SignalSemaphore`: normative precedence:", 1)[1].split("\n- `WaitSemaphores`:", 1)[0]
        for phrase in (
            "less than or equal to the observable counter is rejected with `BadValue`",
            "crosses or violates an existing GPU signal reservation is rejected with `INVALID_SYNCHRONIZATION_STATE`",
            "check device state",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, signal_section)
        self.assertIn(
            "not greater than the observable counter returns `BadValue`",
            error_section,
        )
        self.assertIn("a timeline `signal_value` not greater than the observable counter returns `BadValue`", error_section)
        self.assertIn(
            "exceeds the counter but crosses or violates an already reserved GPU signal value returns `INVALID_SYNCHRONIZATION_STATE`",
            error_section,
        )

        self.assertLess(
            signal_section.index("check device state"),
            signal_section.index("less than or equal to the observable counter"),
        )
        self.assertLess(
            signal_section.index("less than or equal to the observable counter"),
            signal_section.index("crosses or violates an existing GPU signal reservation"),
        )
        self.assertIn(
            "a timeline signal value that is not greater than the observable counter results in `BadValue`",
            queue,
        )
        self.assertIn(
            "a value that exceeds the counter but is not greater than every already-reserved pending GPU signal value results in `INVALID_SYNCHRONIZATION_STATE`",
            queue,
        )

    def test_queue_submit_precedence_and_atomic_acceptance_match_error_contract(self):
        queue = (ROOT / "spec/queue-submission.md").read_text(encoding="utf-8")
        registry = (ROOT / "registries/request-subopcodes.md").read_text(encoding="utf-8")
        section = self.conformance

        # The request registry, normative chapter, general error mapping, and
        # conformance matrix must all retain the same request and outcomes.
        self.assertIn("`QueueSubmit` | 28 |", registry)
        self.assertIn("`QueueSubmit`", queue)
        self.assertIn("`QueueSubmit`", self.errors)
        self.assertIn("`QueueSubmit`", section)
        for outcome in (
            "BadLength", "BadValue", "BadMatch", "DEVICE_UNAVAILABLE",
            "DEVICE_LOST", "INVALID_SYNCHRONIZATION_STATE", "DEPENDENCY_FAILED",
        ):
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, queue)
                self.assertIn(outcome, self.errors)
                self.assertIn(outcome, section)

        # These ordering markers prevent an apparently harmless wording edit
        # from reversing the phases or allowing partial reservation.
        for phrase in (
            "incorrect total length", "submission_token = 0",
            "device, optional fence", "an unavailable or lost device",
            "in wire order", "fully non-mutating",
            "the token remains unused", "no submission objects",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, queue)
        for phrase in (
            "semaphore counters, signal availability",
            "The `EXECUTABLE`-to-`PENDING` transitions and synchronization reservations therefore form one shared commit",
            "Every synchronously rejected request is atomic and generates no submission event",
        ):
            with self.subTest(atomicity=phrase):
                self.assertIn(phrase, queue + section)

    def test_all_assigned_requests_are_named_in_error_and_conformance_contracts(self):
        registry = (ROOT / "registries/request-subopcodes.md").read_text(encoding="utf-8")
        requests = []
        for line in registry.splitlines():
            fields = line.split("|")
            if len(fields) >= 4 and fields[1].strip().startswith("`") and fields[2].strip().isdigit():
                requests.append((fields[1].strip().strip("`"), fields[2].strip()))
        self.assertEqual(len(requests), 47, "the audit must cover the full assigned request inventory")
        for request, subopcode in requests:
            with self.subTest(request=request, subopcode=subopcode):
                self.assertIn(f"`{request}` | {subopcode} |", registry)
                self.assertIn(f"`{request}`", self.errors)
                self.assertIn(f"`{request}`", self.conformance)


    def test_descriptor_updates_and_destruction_share_one_lifetime_contract(self):
        recording = (ROOT / "spec/command-recording.md").read_text(encoding="utf-8")
        descriptors = (ROOT / "spec/shaders-pipelines.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec/resource-lifetime.md").read_text(encoding="utf-8")
        errors = self.errors
        conformance = self.conformance

        # Descriptor contents are live set state, not a snapshot captured at bind time.
        for phrase in (
            "descriptor-slot contents are not copied into the command buffer as an immutable snapshot",
            "atomically updates the derived buffer references",
            "uses the set's current contents at submission time",
            "is not invalidated solely by a successful descriptor update",
        ):
            with self.subTest(recording_rule=phrase):
                self.assertIn(phrase, recording)

        # A multi-write update and set/pool destruction must not expose partial state.
        for phrase in (
            "Mehrere Writes desselben Descriptor-Slots",
            "Die Operation ist atomar",
            "Bei einem Fehler darf keine Teilmenge der Sets öffentlich angelegt bleiben",
            "Bei Ablehnung bleiben Pool, Sets und Command-Buffer-Zustände unverändert",
            "werden der Pool und alle enthaltenen Descriptor Sets öffentlich invalidiert",
        ):
            with self.subTest(descriptor_rule=phrase):
                self.assertIn(phrase, descriptors)

        # Lifetime rules distinguish RECORDING blockers from EXECUTABLE invalidation
        # and require the same semantics in the conformance/error contracts.
        for phrase in (
            "von einem `RECORDING`-Command-Buffer referenziert",
            "referencing non-pending `EXECUTABLE` command buffers become `INVALID`",
            "updates the derived internal Buffer references",
        ):
            with self.subTest(lifetime_rule=phrase):
                self.assertIn(phrase, lifetime)
        for phrase in (
            "no partial free",
            "preserve every old slot and indirect resource reference",
            "nicht allein wegen der durch das Update entfernten indirekten Referenz invalidiert",
            "bleibt das Set nicht submitbar",
        ):
            with self.subTest(conformance_rule=phrase):
                self.assertIn(phrase, conformance)
        for phrase in (
            "UpdateDescriptorSets",
            "DestroyDescriptorPool",
            "FreeDescriptorSets",
            "INVALID_SYNCHRONIZATION_STATE",
        ):
            with self.subTest(error_contract=phrase):
                self.assertIn(phrase, errors)


    def test_device_teardown_waits_and_submission_terminalization_are_consistent(self):
        devices = (ROOT / "spec/devices.md").read_text(encoding="utf-8")
        lifetime = (ROOT / "spec/resource-lifetime.md").read_text(encoding="utf-8")
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        queue = (ROOT / "spec/queue-submission.md").read_text(encoding="utf-8")
        conformance = self.conformance

        # DestroyDevice terminates unresolved host waits, but does not fabricate GPU completion.
        for phrase in (
            "WaitSemaphores",
            "WaitForFence",
            "DEVICE_DESTROYED",
            "Wait conditions whose successful result was established before `DestroyDevice` was processed",
            "Internal Vulkan objects are released only when Vulkan lifetime rules",
        ):
            with self.subTest(device_rule=phrase):
                self.assertIn(phrase, devices)
        for phrase in (
            "The first terminal outcome detected wins",
            "Device loss",
            "DestroyDevice",
            "without a reply",
        ):
            with self.subTest(wait_rule=phrase):
                self.assertIn(phrase, synchronization + conformance)

        # Accepted work has one real terminal outcome; event suppression and disconnect
        # must not release backend resources early or manufacture completion.
        for phrase in (
            "exactly one terminal outcome",
            "Each accepted submission receives exactly one internal terminal outcome",
            "the server delivers exactly that event unless delivery is suppressed by a previously processed `DestroyDevice` request",
        ):
            with self.subTest(queue_rule=phrase):
                self.assertIn(phrase, queue)
        for phrase in (
            "all associated public XIDs become `INVALID`",
            "remain `DESTROY_PENDING`",
            "lifecycle rules suppress delivery of presentation events",
            "disconnect neither requires successful completion nor indefinite waiting for GPU progress",
            "premature release of internal backend objects",
        ):
            with self.subTest(lifetime_rule=phrase):
                self.assertIn(phrase, lifetime + conformance)

    def test_command_recording_and_submission_precedence_have_mixed_failure_vectors(self):
        recording = (ROOT / "spec/command-recording.md").read_text(encoding="utf-8")
        queue = (ROOT / "spec/queue-submission.md").read_text(encoding="utf-8")
        errors = self.errors
        conformance = self.conformance

        # Assert the normative phase ordering, not merely that each error is named.
        cb_phases = (
            "Request length, ABORT length",
            "Common-header flags",
            "Target XID, then pool XID",
            "Resource type, client ownership",
            "associated device state is checked",
        )
        recording_precedence = recording[recording.index("### Error Precedence for `CommandBufferData`"):]
        positions = [recording_precedence.index(phrase) for phrase in cb_phases]
        self.assertEqual(positions, sorted(positions))
        submit_phases = (
            "incorrect total length",
            "submission_token = 0",
            "required XIDs are resolved in wire order",
            "resource type, client/device ownership",
            "an unavailable or lost device",
            "mutable preconditions are checked in wire order",
        )
        positions = [queue.index(phrase) for phrase in submit_phases]
        self.assertEqual(positions, sorted(positions))

        # Mixed-failure vectors and atomic rejection must be present in the
        # conformance oracle and agree with the normative/error descriptions.
        for phrase in (
            "For `CommandBufferData`, an invalid flag combination combined with an invalid target XID returns `BadValue`",
            "a structurally truncated entry combined with an invalid target XID returns `BadLength`",
            "For CREATE/Append/FINAL on a lost Device, `DEVICE_LOST` takes precedence",
            "ABORT is the exception",
        ):
            with self.subTest(command_buffer_vector=phrase):
                self.assertIn(phrase, conformance)
        for phrase in (
            "`QueueSubmit` uses token `0` or a previously used token while also containing an unknown Device/Buffer XID",
            "an incorrect live resource type or foreign ownership returns `BadMatch`",
            "After valid XID/type/ownership/queue checks, Device Loss returns `DEVICE_LOST` before errors for a non-`EXECUTABLE` command buffer",
            "A wait-stage mask containing reserved bits returns `BadValue` before XID/state validation",
        ):
            with self.subTest(submit_vector=phrase):
                self.assertIn(phrase, conformance)

        # Every synchronous rejection remains non-mutating, even when earlier
        # objects in the same request passed their individual validation.
        for phrase in (
            "the current chunk is never partially accepted",
            "state, entries, and references remain unchanged",
        ):
            with self.subTest(command_buffer_atomicity=phrase):
                self.assertIn(phrase, conformance + recording)
        for phrase in (
            "fully non-mutating",
            "no submission objects",
            "no synchronization state changes",
        ):
            with self.subTest(submit_atomicity=phrase):
                self.assertIn(phrase, queue + errors)


    def test_create_surface_mixed_xid_precedence_has_golden_contract(self):
        presentation = (ROOT / "spec/presentation.md").read_text(encoding="utf-8")
        errors = self.errors
        conformance = self.conformance

        # Length and scalar syntax precede XID checks; target XID precedes Window lookup.
        order = (
            "Validate exact/fixed or formula-derived wire length",
            "Validate scalar syntax and reserved fields",
            "`CreateSurface` checks `surface_xid` before resolving `window_xid`",
        )
        positions = [errors.index(phrase, errors.index("### Normative validation precedence for the seven presentation requests")) for phrase in order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn(
            "For `CreateSurface`, validate `surface_xid` as a create-XID before resolving `window_xid`",
            presentation,
        )

        self.assertIn(
            "invalid/already occupied `surface_xid` combined with an unknown/destroyed/non-Window `window_xid` returns `BadIDChoice`",
            conformance,
        )
        self.assertIn(
            "an invalid request length combined with either invalid XID returns `BadLength`",
            conformance,
        )
        self.assertIn("Neither rejection allocates a Surface or retains a Window reference.", conformance)

    def test_presentation_create_and_status_precedence_match_error_contract(self):
        presentation = (ROOT / "spec/presentation.md").read_text(encoding="utf-8")
        errors = self.errors
        conformance = self.conformance

        # Create ordering must be identical in the normative chapter and test oracle.
        create_order = (
            "For `CreateSwapchain`, validate in this order after scalar syntax: `device_xid`, target `swapchain_xid`, then `surface_xid`.",
        )
        for phrase in create_order:
            with self.subTest(create_order=phrase):
                self.assertIn(phrase, presentation)
                self.assertIn("`CreateSwapchain` validates `device_xid`, target `swapchain_xid`, then `surface_xid` after scalar syntax", conformance)
        for phrase in (
            "After wire-length and scalar-field validation, XID validation follows request field order: resolve `device_xid`, validate the target `swapchain_xid` as a create-XID, then resolve `surface_xid`.",
            "A syntactically valid but unsupported configuration returns `UNSUPPORTED_CONFIGURATION`",
            "`SURFACE_LOST`, `DEVICE_LOST`, and `ALLOCATION_FAILED` are normal reply statuses",
        ):
            with self.subTest(error_mapping=phrase):
                self.assertIn(phrase, errors)

        # The mixed-failure oracle must preserve status precedence and failed-create atomicity.
        for phrase in (
            "Device loss beats Surface loss and accepted-token reuse",
            "Failed creates leave target XIDs unallocated and retain no references",
            "A rejected request causes no partial state mutation attributable to that request",
        ):
            with self.subTest(conformance=phrase):
                self.assertIn(phrase, conformance)
        self.assertIn("If Device loss (without destruction) serializes first, `CreateSwapchain` returns `DEVICE_LOST`", presentation)
        self.assertIn("OUT_OF_DATE", presentation)
        self.assertIn("SURFACE_LOST", presentation)


    def test_acquire_and_present_status_precedence_is_explicit(self):
        errors = self.errors
        presentation = (ROOT / "spec/presentation.md").read_text(encoding="utf-8")
        conformance = self.conformance

        acquire = errors[errors.index("For a new `AcquireNextImage` evaluation"):errors.index("For `QueuePresent`, status replies") ]
        for phrase in (
            "`DEVICE_LOST` takes precedence over `SURFACE_LOST`",
            "which takes precedence over `OUT_OF_DATE`",
            "these outcomes precede mutable synchronization-state checks and timeout polling",
            "even if no image is available or the timeout is zero",
        ):
            with self.subTest(acquire_precedence=phrase):
                self.assertIn(phrase, acquire)

        queue_present = errors[errors.index("### Normative validation precedence for the seven presentation requests"):errors.index("## Synchronous versus Asynchronous Errors") ]
        queue_stages = (
            "Device loss takes precedence over Surface loss",
            "`QueuePresent` returns `SURFACE_LOST` before `OUT_OF_DATE`",
            "reject reuse of a token from an earlier accepted presentation with `BadValue`",
            "then check image state",
            "validate wait semaphores in array order",
        )
        positions = [queue_present.index(phrase) for phrase in queue_stages]
        self.assertEqual(positions, sorted(positions))

        for phrase in (
            "Device loss beats Surface loss and accepted-token reuse",
            "Surface loss and OUT_OF_DATE beat accepted-token reuse",
            "accepted-token reuse returns `BadValue` before image-state and semaphore-eligibility checks",
        ):
            with self.subTest(conformance_precedence=phrase):
                self.assertIn(phrase, conformance)
        self.assertIn("Device loss (without destruction) serializes first, `CreateSwapchain` returns `DEVICE_LOST`", presentation)


    def test_reset_and_host_wait_validation_phases_agree_across_chapters(self):
        recording = (ROOT / "spec/command-recording.md").read_text(encoding="utf-8")
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        errors = self.errors
        conformance = self.conformance

        # ResetCommandBuffer: structural and identity failures precede device/state checks.
        reset_start = recording.index("`ResetCommandBuffer` is a void request")
        reset = recording[reset_start:recording.index("## 7.2 Command Buffer States", reset_start)]
        reset_order = (
            "fixed total length of 16 bytes",
            "Unknown or non-live device or buffer XIDs result in `BadValue`",
            "live resource of the wrong type",
            "After successful XID and ownership validation, an unavailable device",
            "Only then does the server check the pool's `RESET_COMMAND_BUFFER` flag",
        )
        positions = [reset.index(phrase) for phrase in reset_order]
        self.assertEqual(positions, sorted(positions))
        for phrase in (
            "After successful XID and ownership validation, an unavailable device results in `DEVICE_UNAVAILABLE` and a lost device in `DEVICE_LOST`",
            "On rejection, the state, entries, and references remain unchanged.",
        ):
            with self.subTest(reset_contract=phrase):
                self.assertIn(phrase, reset)
        self.assertIn("`ResetCommandBuffer` validates request length, XIDs, type, ownership, and cross-Device association", conformance)

        # WaitSemaphores rejects malformed requests before registration; pending waits
        # have terminal outcomes distinct from initial request validation.
        wait = synchronization[synchronization.index("## `WaitSemaphores`"):synchronization.index("## `WaitForFence`") ]
        wait_order = (
            "length and checked arithmetic",
            "semaphore_count != 0",
            "resolve the device XID and then semaphore XIDs in array order",
            "check resource type, client/device ownership, and cross-device association",
            "check device state",
            "verify that all semaphores are timeline semaphores",
        )
        positions = [wait.index(phrase) for phrase in wait_order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("every synchronous rejection leaves no wait registration", wait)
        self.assertIn("An open wait has exactly one terminal outcome", wait)
        self.assertIn("WaitSemaphores", errors)

        fence_wait = synchronization[synchronization.index("## `WaitForFence`"):synchronization.index("## `ResetFence`") ]
        for phrase in (
            "Request: exactly 24 bytes",
            "resolve Device XID, then Fence XID in wire order (`BadValue` for unknown or non-live XIDs)",
            "Device loss yields the normal reply status `DEVICE_LOST`",
            "`DEVICE_DESTROYED` is returned",
        ):
            with self.subTest(fence_wait_contract=phrase):
                self.assertIn(phrase, fence_wait)
        self.assertIn("WaitForFence", conformance)
        self.assertIn("WaitSemaphores", conformance)


    def test_host_signal_and_reset_fence_precedence_remain_aligned(self):
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        errors = self.errors
        conformance = self.conformance

        signal = synchronization[synchronization.index("## `SignalSemaphore`"):synchronization.index("## Destroying Semaphores") ]
        signal_order = (
            "(1) exact total length of 24 bytes (`BadLength`)",
            "(2) resolve the device XID, then the semaphore XID",
            "(3) check resource type, client/device ownership, and cross-device association",
            "(4) check device state",
            "(5) check timeline type and signal-value/reservation consistency",
        )
        positions = [signal.index(phrase) for phrase in signal_order]
        self.assertEqual(positions, sorted(positions))
        for phrase in (
            "Synchronous validation MUST follow this order: (1) exact total length of 24 bytes (`BadLength`)",
            "check device state (`DEVICE_UNAVAILABLE` or `DEVICE_LOST`)",
            "All checks before signaling form one atomic request operation; synchronous rejection changes neither counters nor reservations",
        ):
            with self.subTest(signal_contract=phrase):
                self.assertIn(phrase, synchronization)

        reset_fence = synchronization[synchronization.index("## `ResetFence`"):synchronization.index("## Destroying Fences") ]
        reset_order = (
            "exact total length (`BadLength`)",
            "resolve Device XID, then Fence XID (`BadValue` for unknown or non-live XIDs)",
            "check Device state (`DEVICE_LOST`)",
            "Only `SIGNALED` and `FAILED` may be reset",
            "reset from `PENDING` or `UNSIGNALED` results in `INVALID_SYNCHRONIZATION_STATE`",
        )
        positions = [reset_fence.index(phrase) for phrase in reset_order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("`ResetFence`: Device verloren | `DEVICE_LOST`", errors)
        self.assertIn("`ResetFence` prüft exakt 16 Bytes und Device-/Fence-XIDs vor dem Zustandscheck", conformance)


    def test_buffer_memory_precedence_and_transfer_atomicity_stay_aligned(self):
        memory = (ROOT / "spec/memory-buffers.md").read_text(encoding="utf-8")
        lifetime = self.lifetime
        errors = self.errors
        conformance = self.conformance

        create_buffer = memory[memory.index("## 5.1 `CreateBuffer`"):memory.index("## 5.2")]
        allocate = memory[memory.index("## 5.4 `AllocateMemory`"):memory.index("## 5.5")]
        bind = memory[memory.index("## 5.6 `BindBufferMemory`"):memory.index("## 5.7")]
        write = memory[memory.index("## 5.7 `WriteBuffer`"):memory.index("## 5.8")]
        read = memory[memory.index("## 5.8 `ReadBuffer`"): ]

        # Creation and allocation must not publish partially initialized XIDs.
        for request_section, phrases in (
            (create_buffer, ("size", "usage_flags = 0", "Creating a buffer does not allocate or bind memory.")),
            (allocate, ("memory_type_index", "The request is atomic", "`memory_xid` remains unallocated")),
        ):
            for phrase in phrases:
                with self.subTest(create_or_allocate=phrase):
                    self.assertIn(phrase, request_section)
        self.assertIn("CreateBuffer", conformance)
        self.assertIn("AllocateMemory", conformance)

        # Binding has a normative phase order and must be all-or-nothing.
        bind_order = (
            "(1) exact wire length",
            "(2) resolve device, buffer, and memory XIDs in wire order",
            "(3) resource type, client/device ownership, and cross-device association",
            "(4) device state",
            "(5) binding-specific checks",
        )
        positions = [bind.index(phrase) for phrase in bind_order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("if rejected, the buffer remains unbound", bind)
        self.assertIn("`BindBufferMemory`", errors)
        self.assertIn("`BindBufferMemory`", conformance)

        # A destroyed public Buffer can still keep its allocation alive through
        # descriptor/internal references; FreeMemory must not invalidate it.
        self.assertIn("any internally live buffer remains bound to this allocation", memory)
        self.assertIn("atomically rejected if any internally live buffer remains bound to this allocation (`BadMatch`)", memory)
        self.assertIn("On rejection, the memory XID and allocation remain unchanged.", memory)

        # Read/write are ordering boundaries, not merely synchronous byte copies.
        for phrase in (
            "accepted before this `WriteBuffer` request have reached a terminal outcome",
            "MUST NOT send a successful reply",
            "same logical device",
        ):
            with self.subTest(write_boundary=phrase):
                self.assertIn(phrase, write)
        for phrase in (
            "alle vor diesem Request angenommenen `QueueSubmit`-Submissions",
            "stabilen Daten-Snapshot",
            "MUST NOT send a successful data reply",
        ):
            with self.subTest(read_boundary=phrase):
                self.assertIn(phrase, read)
        for phrase in ("ReadBuffer", "WriteBuffer", "DEPENDENCY_FAILED", "DEVICE_LOST"):
            with self.subTest(transfer_contract=phrase):
                self.assertIn(phrase, errors)
                self.assertIn(phrase, conformance)

    def test_pipeline_creation_and_resource_destroy_lifetimes_match_error_precedence(self):
        pipelines = (ROOT / "spec/shaders-pipelines.md").read_text(encoding="utf-8")
        lifetime = self.lifetime
        errors = self.errors
        conformance = self.conformance

        layout = pipelines[pipelines.index("## 6.7 `CreatePipelineLayout`"):pipelines.index("## 6.8 Compute Pipeline")]
        pipeline = pipelines[pipelines.index("## 6.8 Compute Pipeline"): ]
        for request_section, ordered_phases in (
            (layout, (
                "(1) exakte, count-konsistente Wire-Länge",
                "(2) reservierte Felder, nicht unterstützte Stage-Bits",
                "(3) Ziel-XID",
                "(4) Device- und Set-Layout-XIDs in Wire-Reihenfolge",
                "(5) Ressourcentyp, Ownership und Cross-Device-Zuordnung",
                "(6) Device-Zustand",
                "(7) geräteabhängige Limits",
            )),
            (pipeline, (
                "(1) exakte Wire-Länge",
                "(2) positiven Entry-Point-Count",
                "(3) Ziel-Pipeline-XID",
                "(4) Device-, Pipeline-Layout- und Shader-Module-XIDs in Wire-Reihenfolge",
                "(5) Ressourcentyp, Ownership und Cross-Device-Zuordnung",
                "(6) Device-Zustand",
                "(7) Backend-Pipeline-Erstellung",
            )),
        ):
            positions = [request_section.index(phrase) for phrase in ordered_phases]
            self.assertEqual(positions, sorted(positions))
            self.assertRegex(request_section, r"(?i)atomic|atomar|unangelegt|unallocated")

        # Destruction invalidates public XIDs atomically, while retained internal
        # references survive until no backend access can remain.
        for phrase in (
            "destruction is rejected with `INVALID_SYNCHRONIZATION_STATE`",
            "If a resource referenced by an `EXECUTABLE` command buffer is destroyed",
            "transition to `INVALID` before the destroy request completes successfully",
            "no backend access remains possible",
        ):
            with self.subTest(lifetime_rule=phrase):
                self.assertIn(phrase, lifetime)
        for phrase in ("CreatePipelineLayout", "CreateComputePipeline", "DestroyResource"):
            with self.subTest(request=phrase):
                self.assertIn("`" + phrase + "`", errors)
                self.assertIn("`" + phrase + "`", conformance)


    def test_create_device_empty_registries_and_unknown_requests_have_distinct_errors(self):
        devices = (ROOT / "spec/devices.md").read_text(encoding="utf-8")
        features = (ROOT / "registries/feature-ids.md").read_text(encoding="utf-8")
        extensions = (ROOT / "registries/device-extensions.md").read_text(encoding="utf-8")
        errors = self.errors

        # v0.1 has no optional feature IDs: an unknown ID is a scalar error
        # and therefore precedes create-XID occupancy.
        self.assertIn("every `feature_id` value is unknown in v0.1", features)
        self.assertIn("unknown feature ID", devices)
        self.assertIn("unknown feature ID takes precedence over target-XID occupancy", devices)
        self.assertIn("An unknown `feature_id` not defined in the XAverius feature registry results in `BadValue`", devices)

        # Extension syntax errors are scalar BadValue; syntactically valid
        # but unregistered names reach the later registry phase and are BadMatch.
        self.assertIn("every syntactically valid name is unknown to XAverius", extensions)
        self.assertIn("a malformed name MUST be rejected with `BadValue`", extensions)
        self.assertIn("unknown to the XAverius extension registry or unsupported by the selected physical device results in `BadMatch`", devices)
        self.assertIn("An extension name that is syntactically valid but unknown to the XAverius extension registry or unsupported by the physical device", errors)

        ordered = (
            "Validate wire-level and scalar fields",
            "Validate `device_xid` as a create-XID",
            "Resolve `physical_device_xid`",
            "Require successful XGE 1.0-or-later negotiation",
            "Check physical-device availability",
            "Validate every requested queue-family index and queue count",
            "Check requested registry-defined features and extensions",
        )
        positions = [devices.index(phrase, devices.index("### Normative validation precedence")) for phrase in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("All validation occurs before creating the logical device", devices)
        self.assertIn("`device_xid` remains unallocated", devices)


    def test_select_events_mixed_failure_precedence_matches_normative_chapters(self):
        events = (ROOT / "spec/events.md").read_text(encoding="utf-8")
        errors = self.errors
        conformance = self.conformance

        # Keep the normative chapter and central error map synchronized. This
        # prevents an implementation from checking XGE before scalar/XID errors
        # in one code path but after them in another.
        event_heading = events.index("## Event Selection")
        event_start = events.index("Normative validation precedence is:", event_heading)
        event_section = events[event_start:events.index("The masks depend on the scope:", event_start)]
        error_heading = errors.index("### `SelectEvents`")
        error_start = errors.index("Normative validation precedence, matching [Event Selection]", error_heading)
        error_section = errors[error_start:errors.index("\n\n###", error_start)]
        phases_by_section = {
            "events": (
                "exact 32-byte request length",
                "validate scope, zero-valued unused fields",
                "resolve `device_xid`",
                "validate live type and client ownership",
                "require successful XGE 1.0-or-later negotiation",
                "validate the queue-family/index tuple",
                "atomically replace",
            ),
            "errors": (
                "exact 32-byte request length",
                "scope, unused fields, reserved fields",
                "resolve `device_xid`",
                "validate live type and client ownership",
                "require successful XGE 1.0-or-later negotiation",
                "validate the queue-family/index tuple",
                "atomically replace",
            ),
        }
        for section_name, section in (("events", event_section), ("errors", error_section)):
            with self.subTest(section=section_name):
                positions = [section.index(phrase) for phrase in phases_by_section[section_name]]
                self.assertEqual(positions, sorted(positions))
                self.assertIn("A later phase MUST NOT override an earlier error", section)

        # Rejection must preserve the prior selection even if earlier phases passed.
        for phrase in (
            "previous selection remains unchanged",
            "XID/type/ownership errors take precedence over the XGE prerequisite",
        ):
            with self.subTest(atomicity=phrase):
                self.assertIn(phrase, events + errors)
        self.assertIn("`SelectEvents`", conformance)

    def test_semaphore_reservation_identity_and_device_loss_ignore_stale_callbacks(self):
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        queue = (ROOT / "spec/queue-submission.md").read_text(encoding="utf-8")
        conformance = self.conformance

        binary = synchronization.split("## Binary Semaphores", 1)[1].split("\n## Presentation Waits", 1)[0]
        timeline = synchronization.split("## Timeline Semaphores", 1)[1].split("\n## `GetSemaphoreCounterValue`", 1)[0]
        terminal = queue.split("**Atomic terminal transition:**", 1)[1].split("\n## Semaphore references", 1)[0]
        references = queue.split("## Semaphore references", 1)[1].split("\n# Queue Ordering", 1)[0]

        for phrase in (
            "unique internal reservation identity tied to the exact internal semaphore identity",
            "MUST NOT find or modify a reservation by numeric XID alone",
            "MUST NOT publish success, change `UNTRUSTED`, consume/resurrect a signal",
        ):
            with self.subTest(section="binary", phrase=phrase):
                self.assertIn(phrase, binary)

        for phrase in (
            "unique internal reservation identity tied to the exact semaphore identity",
            "late or duplicate callbacks MUST NOT advance the counter or remove a newer operation's reservation",
            "max(current_counter, completed_signal_value)",
        ):
            with self.subTest(section="timeline", phrase=phrase):
                self.assertIn(phrase, timeline)

        for phrase in (
            "unique reservation identity for the specific wait/signal operation",
            "numeric XID lookup alone is never sufficient",
            "MUST NOT publish success, change an `UNTRUSTED` binary semaphore",
        ):
            with self.subTest(section="terminalization", phrase=phrase):
                self.assertIn(phrase, terminal)

        self.assertIn("removing a reservation must compare the captured internal semaphore identity and reservation identity", references)
        self.assertIn("interleave Device Loss with wait-consumption, signal-success and signal-failure callbacks", conformance)
        self.assertIn("no late callback changes the payload state or affects a newer reservation", conformance)


    def test_mixed_failure_oracles_are_complete_and_match_normative_phase_order(self):
        """Cross-check the same precedence decisions in spec, error map, and test oracle."""
        devices = (ROOT / "spec/devices.md").read_text(encoding="utf-8")
        presentation = (ROOT / "spec/presentation.md").read_text(encoding="utf-8")
        events = (ROOT / "spec/events.md").read_text(encoding="utf-8")
        synchronization = (ROOT / "spec/synchronization.md").read_text(encoding="utf-8")
        registry = (ROOT / "registries/request-subopcodes.md").read_text(encoding="utf-8")

        # Each entry is a concrete mixed-failure oracle, not merely a list of
        # error names. The source order and the expected winner must both exist.
        cases = (
            {
                "request": "CreateDevice",
                "subopcode": 4,
                "source": devices,
                "ordered": (
                    "Validate the complete variable-length request framing",
                    "Validate wire-level and scalar fields",
                    "Validate `device_xid` as a create-XID",
                    "Resolve `physical_device_xid`",
                ),
                "oracle": "Malformed total length plus an invalid or occupied `device_xid` → `BadLength`",
                "winner": "`BadLength`",
            },
            {
                "request": "GetPhysicalDeviceProperty",
                "subopcode": 2,
                "source": devices,
                "ordered": (
                    "exact 16-byte request length (`BadLength`)",
                    "resolve the Physical-Device XID (`BadValue` if unknown or non-live)",
                    "validate that the live resource is a Physical Device (`BadMatch` otherwise)",
                    "validate `property_atom` as a server-known X11 Atom (`BadAtom` if invalid)",
                ),
                "oracle": "malformed length + invalid Atom → `BadLength`",
                "winner": "`BadLength`",
            },
            {
                "request": "CreateSurface",
                "subopcode": 41,
                "source": self.errors,
                "ordered": (
                    "Validate exact/fixed or formula-derived wire length",
                    "Validate scalar syntax and reserved fields",
                    "Resolve request XIDs in wire-field order",
                    "Validate live resource types, connection ownership",
                ),
                "oracle": "Mixed-failure `CreateSurface`: after exact-length and scalar validation, an invalid/already occupied `surface_xid` combined with an unknown/destroyed/non-Window `window_xid` returns `BadIDChoice`",
                "winner": "`BadIDChoice`",
            },
            {
                "request": "SelectEvents",
                "subopcode": 40,
                "source": events,
                "ordered": (
                    "exact 32-byte request length",
                    "validate scope, zero-valued unused fields",
                    "resolve `device_xid`",
                    "validate live type and client ownership",
                    "require successful XGE 1.0-or-later negotiation",
                ),
                "oracle": "after valid Device XID/type/ownership checks, missing XGE negotiation plus an invalid queue tuple returns `BadMatch` from the XGE prerequisite",
                "winner": "`BadMatch`",
            },
            {
                "request": "SignalSemaphore",
                "subopcode": 32,
                "source": synchronization,
                "ordered": (
                    "(1) exact total length of 24 bytes (`BadLength`)",
                    "(2) resolve the device XID, then the semaphore XID",
                    "(3) check resource type, client/device ownership, and cross-device association",
                    "(4) check device state",
                    "(5) check timeline type and signal-value/reservation consistency",
                ),
                "oracle": "in particular, `DEVICE_LOST` after valid resource resolution takes precedence over a Binary-semaphore type error",
                "winner": "`DEVICE_LOST`",
            },
            {
                "request": "WaitSemaphores",
                "subopcode": 31,
                "source": synchronization,
                "ordered": (
                    "length and checked arithmetic",
                    "semaphore_count != 0",
                    "resolve the device XID and then semaphore XIDs in array order",
                    "check resource type, client/device ownership, and cross-device association",
                    "check device state",
                    "verify that all semaphores are timeline semaphores",
                ),
                "oracle": "in particular, `DEVICE_LOST` after valid XIDs and ownership takes precedence over a Semaphore type error",
                "winner": "`DEVICE_LOST`",
            },
        )
        conformance = self.conformance
        for case in cases:
            request = case["request"]
            with self.subTest(request=request):
                self.assertIn(f"`{request}` | {case['subopcode']} |", registry)
                self.assertIn(f"`{request}`", self.errors)
                self.assertIn(f"`{request}`", conformance)
                self.assertIn(case["oracle"], conformance)
                self.assertIn(case["winner"], self.errors)
                positions = [case["source"].find(phase) for phase in case["ordered"]]
                self.assertTrue(all(position >= 0 for position in positions), positions)
                self.assertEqual(positions, sorted(positions), f"{request}: normative phase order changed")

        # Detect accidental omission of a mixed-failure oracle: the listed
        # cases must stay unique and the presentation case must remain in the
        # presentation-profile section rather than an unrelated chapter.
        self.assertEqual(len({case["request"] for case in cases}), len(cases))
        presentation_oracles = self.conformance.split(
            "## Presentation-profile conformance cases", 1
        )[1]
        self.assertIn(cases[2]["oracle"], presentation_oracles)


    def test_mixed_failure_oracles_are_scoped_to_their_request_contracts(self):
        """Reject false positives caused by finding an outcome elsewhere in the spec."""
        errors = self.errors
        conformance = self.conformance

        # The oracle must live in the request's own conformance area, and the
        # winning result must be justified by that request's own error mapping.
        first_heading = conformance.find("\n## ")
        preamble = conformance[:first_heading] if first_heading >= 0 else conformance
        presentation_cases = conformance.split(
            "## Presentation-profile conformance cases", 1
        )[1].split("\n## ", 1)[0]
        create_device_cases = conformance.split(
            "## `CreateDevice` mixed-failure and atomicity tests", 1
        )[1].split("\n## ", 1)[0]
        discovery_cases = conformance.split(
            "## Discovery, allocation, and transfer rejection matrix", 1
        )[1].split("\n## ", 1)[0]

        error_sections = {
            "CreateDevice": errors.split(
                "The following error precedence applies to `CreateDevice`", 1
            )[1].split("\n\n## Request-spezifische Fehlerzuordnung", 1)[0],
            "GetPhysicalDeviceProperty": errors.split(
                "- `GetPhysicalDeviceProperty` precedence is:", 1
            )[1].split("\n- `GetPhysicalDeviceQueueFamilyProperties`:", 1)[0],
            "CreateSurface": errors.split(
                "- `CreateSurface`:", 1
            )[1].split("\n- `DestroySurface`:", 1)[0],
            "SelectEvents": errors.split(
                "### `SelectEvents`", 1
            )[1].split("\n\n### ", 1)[0],
            "SignalSemaphore": errors.split(
                "- `SignalSemaphore`: normative precedence:", 1
            )[1].split("\n- `WaitSemaphores`:", 1)[0],
            "WaitSemaphores": errors.split(
                "- `WaitSemaphores`:", 1
            )[1].split("\n- `WaitForFence`:", 1)[0],
        }
        conformance_sections = {
            "CreateDevice": create_device_cases,
            "GetPhysicalDeviceProperty": discovery_cases,
            "CreateSurface": presentation_cases,
            "SelectEvents": preamble,
            "SignalSemaphore": preamble,
            "WaitSemaphores": preamble,
        }
        cases = (
            ("CreateDevice", "Malformed total length plus an invalid or occupied `device_xid` → `BadLength`", "`BadLength`"),
            ("GetPhysicalDeviceProperty", "malformed length + invalid Atom → `BadLength`", "`BadLength`"),
            ("CreateSurface", "Mixed-failure `CreateSurface`: after exact-length and scalar validation, an invalid/already occupied `surface_xid` combined with an unknown/destroyed/non-Window `window_xid` returns `BadIDChoice`", "`BadIDChoice`"),
            ("SelectEvents", "after valid Device XID/type/ownership checks, missing XGE negotiation plus an invalid queue tuple returns `BadMatch` from the XGE prerequisite", "`BadMatch`"),
            ("SignalSemaphore", "in particular, `DEVICE_LOST` after valid resource resolution takes precedence over a Binary-semaphore type error", "`DEVICE_LOST`"),
            ("WaitSemaphores", "in particular, `DEVICE_LOST` after valid XIDs and ownership takes precedence over a Semaphore type error", "`DEVICE_LOST`"),
        )
        for request, oracle, winner in cases:
            with self.subTest(request=request):
                self.assertIn(oracle, conformance_sections[request])
                self.assertIn(winner, error_sections[request])
                self.assertIn(winner, oracle)

        # Every normative error mapping used above must retain its own ordered
        # stages; an error token elsewhere in errors.md is not sufficient.
        ordered_error_phases = {
            "CreateDevice": (
                "Validate complete request framing using checked arithmetic",
                "Validate wire-level and scalar fields",
                "Validate create-XID `device_xid`",
                "Resolve `physical_device_xid`",
            ),
            "GetPhysicalDeviceProperty": (
                "Physical-Device XID resolution (`BadValue` for unknown/non-live XIDs)",
                "live resource type (`BadMatch`)",
                "Atom (`BadAtom` if invalid)",
            ),
            "CreateSurface": (
                "Validate exact/fixed or formula-derived wire length",
                "Validate scalar syntax and reserved fields",
                "Resolve request XIDs in wire-field order",
                "Validate live resource types, connection ownership",
            ),
            "SelectEvents": (
                "exact 32-byte request length",
                "scope, unused fields, reserved fields",
                "resolve `device_xid`",
                "require successful XGE 1.0-or-later negotiation",
            ),
            "SignalSemaphore": (
                "incorrect length",
                "resolve Device XID, then Semaphore XID",
                "validate resource type, ownership, and cross-device use",
                "check Device state",
                "finally validate semaphore type",
            ),
            "WaitSemaphores": (
                "length and overflow",
                "resolve Device and Semaphore XIDs in array order",
                "validate type, ownership, and cross-device use",
                "check Device state",
                "finally require every Semaphore to be `TIMELINE`"
            ),
        }
        for request, phases in ordered_error_phases.items():
            section = error_sections[request]
            positions = [section.find(phase) for phase in phases]
            with self.subTest(request=request, phases="error-map order"):
                self.assertTrue(all(pos >= 0 for pos in positions), positions)
                self.assertEqual(positions, sorted(positions), "error-map precedence contradicts its declared order")


if __name__ == "__main__":
    unittest.main()
