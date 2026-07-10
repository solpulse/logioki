import unittest
from types import SimpleNamespace

from device_monitor import DeviceRegistry


class FakeCamera(SimpleNamespace):
    def __init__(self, key):
        super().__init__(key=key, closed=False)

    def close(self):
        self.closed = True


class DeviceRegistryTests(unittest.TestCase):
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

    def test_refresh_reports_removed_devices_without_closing_before_consumer_handles_them(self):
        removed = FakeCamera("camera-a")
        registry = DeviceRegistry(lambda: [], [removed])

        change = registry.refresh()

        self.assertEqual((removed,), change.removed)
        self.assertFalse(removed.closed)

    def test_close_releases_every_owned_device(self):
        first, second = FakeCamera("a"), FakeCamera("b")
        registry = DeviceRegistry(lambda: (), [first, second])
        registry.close()
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)
        self.assertEqual((), registry.devices)


if __name__ == "__main__":
    unittest.main()
