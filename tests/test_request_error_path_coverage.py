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

    def test_fence_destroy_boundary_is_serialized_wait_result(self):
        self.assertIn("terminal result has been serialized", self.conformance)
        self.assertIn("an unsent reply alone does not keep destruction blocked", self.conformance)
        self.assertIn("offene `WaitForFence`-Registrierung", self.errors)

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
            "falsche Gesamtlänge", "submission_token = 0",
            "Device, optionale Fence", "nicht verfügbares/verlorenes Device",
            "in Wire-Reihenfolge", "vollständig nicht-mutierend",
            "der Token bleibt unbenutzt", "keine Submission-Objekte",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, queue)
        for phrase in (
            "semaphore counters, binary signal availability",
            "atomically with submission acceptance",
            "synchron abgewiesene Requests erzeugen kein Submission-Event",
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
            "Descriptor-Slot-Inhalte werden nicht als unveränderlicher Snapshot",
            "aktualisiert atomar die abgeleiteten Buffer-Referenzen",
            "verwendet bei Submission die aktuellen Inhalte",
            "wird allein durch ein erfolgreiches Descriptor-Update nicht invalidiert",
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
            "referenzierende nicht-pending `EXECUTABLE`-Command-Buffer `INVALID`",
            "internen Referenzanpassungen atomar mit der öffentlichen Invalidierung",
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
            "Wait-Bedingungen, deren Ergebnis vor Verarbeitung",
            "Interne Vulkan-Objekte werden erst freigegeben",
        ):
            with self.subTest(device_rule=phrase):
                self.assertIn(phrase, devices)
        for phrase in (
            "Der zuerst festgestellte terminale Ausgang gewinnt",
            "Device Loss",
            "DestroyDevice",
            "ohne Reply",
        ):
            with self.subTest(wait_rule=phrase):
                self.assertIn(phrase, synchronization + conformance)

        # Accepted work has one real terminal outcome; event suppression and disconnect
        # must not release backend resources early or manufacture completion.
        for phrase in (
            "genau einen terminalen Ausgang",
            "Der Server darf keine erfolgreiche Completion vortäuschen",
            "das Backend nicht mehr auf die Ressourcen zugreift",
        ):
            with self.subTest(queue_rule=phrase):
                self.assertIn(phrase, queue)
        for phrase in (
            "alle zugehörigen öffentlichen XIDs werden `INVALID`",
            "bleiben `DESTROY_PENDING`",
            "Lifecycle-Regeln die Zustellung von Presentation-Events unterdrücken",
            "ohne Completion zu erfinden",
            "Backend-Ressourcen vorzeitig freizugeben",
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
            "Request-Länge, ABORT-Länge",
            "Common-Header-Flags",
            "Ziel-XID, danach Pool-XID",
            "Ressourcentyp, Client-Ownership",
            "Zustand des zugehörigen Devices",
        )
        positions = [recording.index(phrase) for phrase in cb_phases]
        self.assertEqual(positions, sorted(positions))
        submit_phases = (
            "falsche Gesamtlänge",
            "submission_token = 0",
            "erforderliche XIDs werden in Wire-Reihenfolge",
            "Ressourcentyp, Client-/Device-Ownership",
            "nicht verfügbares/verlorenes Device",
            "veränderlichen Voraussetzungen in Wire-Reihenfolge",
        )
        positions = [queue.index(phrase) for phrase in submit_phases]
        self.assertEqual(positions, sorted(positions))

        # Mixed-failure vectors and atomic rejection must be present in the
        # conformance oracle and agree with the normative/error descriptions.
        for phrase in (
            "Bei `CommandBufferData` mit ungültiger Flag-Kombination und ungültiger Ziel-XID gewinnt",
            "bei strukturell abgeschnittenem Entry und ungültiger Ziel-XID gewinnt `BadLength`",
            "Bei CREATE/Append/FINAL auf einem verlorenen Device gewinnt",
            "ABORT bleibt die Ausnahme",
        ):
            with self.subTest(command_buffer_vector=phrase):
                self.assertIn(phrase, conformance)
        for phrase in (
            "`QueueSubmit` mit Token `0` oder bereits verwendetem Token und gleichzeitig unbekannter",
            "falscher live Ressourcentyp/fremde Ownership `BadMatch`",
            "Device Loss `DEVICE_LOST` vor einem nicht-`EXECUTABLE` Command Buffer",
            "Wait-Stage-Maske mit reservierten Bits ergibt `BadValue`",
        ):
            with self.subTest(submit_vector=phrase):
                self.assertIn(phrase, conformance)

        # Every synchronous rejection remains non-mutating, even when earlier
        # objects in the same request passed their individual validation.
        for phrase in (
            "kein Teil des aktuellen Chunks angehängt",
            "Zustand, Entries und Referenzen unverändert",
        ):
            with self.subTest(command_buffer_atomicity=phrase):
                self.assertIn(phrase, conformance + recording)
        for phrase in (
            "vollständig nicht-mutierend",
            "keine Submission-Objekte",
            "Semaphore-Counter, Signalverfügbarkeit, Pending-Slots",
        ):
            with self.subTest(submit_atomicity=phrase):
                self.assertIn(phrase, queue + errors)


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

        queue_present = errors[errors.index("### Normative validation precedence for the seven presentation requests"):errors.index("## Synchron versus asynchron") ]
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
        reset_start = recording.index("`ResetCommandBuffer` ist ein Void-Request")
        reset = recording[reset_start:recording.index("`TRANSIENT` und `RESET_COMMAND_BUFFER` sind unabhängige Bits", reset_start)]
        reset_order = (
            "feste Gesamtlänge von 16 Bytes",
            "Unbekannte/nicht-live Device- oder Buffer-XIDs ergeben `BadValue`",
            "falscher live Ressourcentyp",
            "Nach erfolgreicher XID-/Ownership-Prüfung ergibt ein nicht verfügbares Device",
            "Erst danach prüft der Server das `RESET_COMMAND_BUFFER`-Flag",
        )
        positions = [reset.index(phrase) for phrase in reset_order]
        self.assertEqual(positions, sorted(positions))
        for phrase in (
            "Nach erfolgreicher XID-/Ownership-Prüfung ergeben ein nicht verfügbares oder verlorenes logisches Device",
            "Jede Ablehnung lässt Zustand, Entries und Ressourcenreferenzen unverändert",
        ):
            with self.subTest(reset_contract=phrase):
                self.assertIn(phrase, errors)
        self.assertIn("`ResetCommandBuffer` prüft Request-Länge, XIDs, Typ, Ownership und Cross-Device-Zuordnung", conformance)

        # WaitSemaphores rejects malformed requests before registration; pending waits
        # have terminal outcomes distinct from initial request validation.
        wait = synchronization[synchronization.index("## `WaitSemaphores`"):synchronization.index("## `WaitForFence`") ]
        wait_order = (
            "(1) Länge und checked-arithmetic",
            "(2) `semaphore_count != 0`",
            "(3) Device-XID und danach Semaphore-XIDs in Array-Reihenfolge",
            "(4) Ressourcentyp, Client-/Device-Ownership",
            "(5) Device-Zustand prüfen",
            "(6) prüfen, dass alle Semaphoren Timeline-Semaphoren sind",
        )
        positions = [wait.index(phrase) for phrase in wait_order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("jede synchrone Ablehnung hinterlässt keine Wait-Registrierung", wait)
        self.assertIn("Für einen bereits registrierten offenen Wait ist Device Loss dagegen ein terminales Wait-Ergebnis", wait)
        self.assertIn("Device Loss während `WaitSemaphores` wird als `DEVICE_LOST`-X11-Fehler gemeldet", errors)

        fence_wait = synchronization[synchronization.index("## `WaitForFence`"):synchronization.index("## `ResetFence`") ]
        for phrase in (
            "Request: 24 Bytes exakt",
            "Unbekannte/nicht-live Device- oder Fence-XIDs ergeben `BadValue`",
            "Bei Device Loss wird `DEVICE_LOST` zurückgegeben",
            "`DEVICE_DESTROYED` zurückgegeben",
        ):
            with self.subTest(fence_wait_contract=phrase):
                self.assertIn(phrase, fence_wait)
        self.assertIn("`WaitForFence` wird `DEVICE_LOST` als normaler Reply-Status zurückgegeben", errors)
        self.assertIn("`WaitSemaphores` und `WaitForFence` liefern bei Timeout einen normalen Reply-Status", errors)


if __name__ == "__main__":
    unittest.main()
