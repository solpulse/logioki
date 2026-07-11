import unittest
from types import SimpleNamespace

from device_monitor import DeviceRegistry


class FakeCamera(SimpleNamespace):
    def __init__(self, key, path=None):
        super().__init__(key=key, path=path, closed=False)

    def close(self):
        self.closed = True


class DeviceRegistryTests(unittest.TestCase):
    def test_initial_snapshot_collapses_duplicate_stable_identities(self):
        first = FakeCamera("camera-a", "/dev/video0")
        duplicate = FakeCamera("camera-a", "/dev/video1")

        registry = DeviceRegistry(lambda: (), [first, duplicate])

        self.assertEqual((first,), registry.devices)
        self.assertFalse(first.closed)
        self.assertTrue(duplicate.closed)

    def test_refresh_preserves_existing_descriptors_and_closes_duplicates(self):
        original = FakeCamera("camera-a")
        duplicate = FakeCamera("camera-a")
        added = FakeCamera("camera-b")
        registry = DeviceRegistry(lambda: [duplicate, added], [original])

        change = registry.refresh()

        self.assertEqual((original, added), change.devices)
        self.assertEqual((added,), change.added)
        self.assertEqual((), change.removed)
        self.assertTrue(duplicate.closed)
        self.assertFalse(original.closed)

    def test_refresh_collapses_multiple_nodes_with_the_same_stable_identity(self):
        first = FakeCamera("usb:046d:085e:serial", "/dev/video2")
        second = FakeCamera("usb:046d:085e:serial", "/dev/video3")
        registry = DeviceRegistry(lambda: [first, second])

        change = registry.refresh()

        self.assertEqual((first,), change.devices)
        self.assertEqual((first,), change.added)
        self.assertTrue(second.closed)

    def test_refresh_reports_removed_devices_without_closing_before_consumer_handles_them(self):
        removed = FakeCamera("camera-a")
        registry = DeviceRegistry(lambda: [], [removed])

        change = registry.refresh()

        self.assertEqual((removed,), change.removed)
        self.assertFalse(removed.closed)

    def test_refresh_replaces_same_camera_when_device_node_changes(self):
        original = FakeCamera("camera-a", "/dev/video0")
        replacement = FakeCamera("camera-a", "/dev/video4")
        registry = DeviceRegistry(lambda: [replacement], [original])

        change = registry.refresh()

        self.assertEqual((replacement,), change.devices)
        self.assertEqual((replacement,), change.added)
        self.assertEqual((original,), change.removed)
        self.assertFalse(original.closed)

    def test_close_releases_every_owned_device(self):
        first, second = FakeCamera("a"), FakeCamera("b")
        registry = DeviceRegistry(lambda: (), [first, second])
        registry.close()
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)
        self.assertEqual((), registry.devices)


if __name__ == "__main__":
    unittest.main()
