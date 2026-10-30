"""Focused lifetime reference models for pipeline and descriptor layouts."""
from __future__ import annotations

from dataclasses import dataclass
import unittest


@dataclass
class PipelineLayout:
    xid_live: bool = True
    backend_live: bool = True
    dependent_pipelines: int = 0
    recording_direct_refs: int = 0
    executable_direct_refs: int = 0
    accepted_direct_uses: int = 0


def create_pipeline(layout: PipelineLayout) -> str:
    if not layout.xid_live:
        return "BadValue"
    layout.dependent_pipelines += 1
    return "SUCCESS"


def destroy_pipeline_layout(layout: PipelineLayout) -> str:
    if not layout.xid_live:
        return "BadValue"
    if layout.recording_direct_refs or layout.accepted_direct_uses:
        return "INVALID_SYNCHRONIZATION_STATE"
    # Executable command buffers are invalidated atomically with public XID
    # invalidation. A Pipeline's independent retained layout identity survives.
    layout.executable_direct_refs = 0
    layout.xid_live = False
    if layout.dependent_pipelines == 0:
        layout.backend_live = False
    return "SUCCESS"


def destroy_pipeline(layout: PipelineLayout) -> str:
    if layout.dependent_pipelines == 0:
        return "BadValue"
    layout.dependent_pipelines -= 1
    if not layout.xid_live and layout.dependent_pipelines == 0:
        layout.backend_live = False
    return "SUCCESS"


@dataclass
class DescriptorSetLayout:
    xid_live: bool = True
    backend_live: bool = True
    allocated_sets: int = 0


@dataclass
class DescriptorSet:
    layout: DescriptorSetLayout
    live: bool = True
    update_count: int = 0


def create_pipeline_layout(layout: DescriptorSetLayout) -> str:
    # Successful creation consumes the public layout XID synchronously and
    # does not create a lasting public-XID dependency.
    return "SUCCESS" if layout.xid_live else "BadValue"


def allocate_set(layout: DescriptorSetLayout) -> DescriptorSet | None:
    if not layout.xid_live:
        return None
    layout.allocated_sets += 1
    return DescriptorSet(layout)


def destroy_descriptor_set_layout(layout: DescriptorSetLayout) -> str:
    if not layout.xid_live:
        return "BadValue"
    layout.xid_live = False
    if layout.allocated_sets == 0:
        layout.backend_live = False
    return "SUCCESS"


def update_descriptor_set(descriptor_set: DescriptorSet) -> str:
    if not descriptor_set.live or not descriptor_set.layout.backend_live:
        return "BadValue"
    # The Set uses its retained immutable layout identity, not a new XID lookup.
    descriptor_set.update_count += 1
    return "SUCCESS"


def free_descriptor_set(descriptor_set: DescriptorSet) -> str:
    if not descriptor_set.live:
        return "BadValue"
    descriptor_set.live = False
    descriptor_set.layout.allocated_sets -= 1
    if not descriptor_set.layout.xid_live and descriptor_set.layout.allocated_sets == 0:
        descriptor_set.layout.backend_live = False
    return "SUCCESS"


class PipelineLayoutLifetimeTests(unittest.TestCase):
    def test_destroy_public_layout_keeps_live_pipeline_dependency(self) -> None:
        layout = PipelineLayout()
        self.assertEqual(create_pipeline(layout), "SUCCESS")
        self.assertEqual(destroy_pipeline_layout(layout), "SUCCESS")
        self.assertFalse(layout.xid_live)
        self.assertTrue(layout.backend_live)
        self.assertEqual(layout.dependent_pipelines, 1)
        self.assertEqual(create_pipeline(layout), "BadValue")
        self.assertEqual(destroy_pipeline(layout), "SUCCESS")
        self.assertFalse(layout.backend_live)

    def test_recording_direct_reference_rejects_atomically(self) -> None:
        layout = PipelineLayout(recording_direct_refs=1, executable_direct_refs=2)
        before = (layout.xid_live, layout.backend_live, layout.executable_direct_refs)
        self.assertEqual(destroy_pipeline_layout(layout), "INVALID_SYNCHRONIZATION_STATE")
        self.assertEqual(
            (layout.xid_live, layout.backend_live, layout.executable_direct_refs), before
        )

    def test_accepted_direct_use_rejects_but_pipeline_hold_does_not(self) -> None:
        layout = PipelineLayout(dependent_pipelines=1, accepted_direct_uses=1)
        self.assertEqual(destroy_pipeline_layout(layout), "INVALID_SYNCHRONIZATION_STATE")
        layout.accepted_direct_uses = 0
        self.assertEqual(destroy_pipeline_layout(layout), "SUCCESS")
        self.assertTrue(layout.backend_live)

    def test_executable_direct_references_are_invalidated_on_success(self) -> None:
        layout = PipelineLayout(executable_direct_refs=3)
        self.assertEqual(destroy_pipeline_layout(layout), "SUCCESS")
        self.assertEqual(layout.executable_direct_refs, 0)

    def test_descriptor_layout_destroy_preserves_allocated_sets(self) -> None:
        layout = DescriptorSetLayout()
        self.assertEqual(create_pipeline_layout(layout), "SUCCESS")
        first = allocate_set(layout)
        second = allocate_set(layout)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(destroy_descriptor_set_layout(layout), "SUCCESS")
        self.assertFalse(layout.xid_live)
        self.assertTrue(layout.backend_live)
        self.assertIsNone(allocate_set(layout))
        self.assertEqual(create_pipeline_layout(layout), "BadValue")
        self.assertEqual(update_descriptor_set(first), "SUCCESS")
        self.assertEqual(update_descriptor_set(second), "SUCCESS")

    def test_descriptor_layout_backend_released_after_last_set(self) -> None:
        layout = DescriptorSetLayout()
        first = allocate_set(layout)
        second = allocate_set(layout)
        self.assertEqual(destroy_descriptor_set_layout(layout), "SUCCESS")
        self.assertEqual(free_descriptor_set(first), "SUCCESS")
        self.assertTrue(layout.backend_live)
        self.assertEqual(free_descriptor_set(second), "SUCCESS")
        self.assertFalse(layout.backend_live)

    def test_set_release_is_exactly_once(self) -> None:
        layout = DescriptorSetLayout()
        descriptor_set = allocate_set(layout)
        self.assertEqual(free_descriptor_set(descriptor_set), "SUCCESS")
        self.assertEqual(layout.allocated_sets, 0)
        self.assertEqual(free_descriptor_set(descriptor_set), "BadValue")
        self.assertEqual(layout.allocated_sets, 0)


if __name__ == "__main__":
    unittest.main()
