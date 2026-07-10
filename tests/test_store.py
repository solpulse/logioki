import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import store
import v4l2ctl


class FakeCamera:
    def __init__(self, key="usb:046d:0944:one", card="MX Brio", path="/dev/video0"):
        self.key = key
        self.card = card
        self.path = path
        self.controls = [
            SimpleNamespace(id=1, type=2, default=1, inactive=False, read_only=False),
            SimpleNamespace(id=2, type=3, default=3, inactive=False, read_only=False),
            SimpleNamespace(id=3, type=1, default=30, inactive=False, read_only=False),
            SimpleNamespace(id=4, type=1, default=40, inactive=False, read_only=True),
        ]
        self.values = {1: 0, 2: 3, 3: 33, 4: 40}
        self.set_calls = []
        self.fail = set()
        self.mismatch = set()
        self.closed = False

    def get(self, ctrl_id):
        return self.values[ctrl_id]

    def set(self, ctrl_id, value):
        self.set_calls.append((ctrl_id, value))
        if ctrl_id in self.fail:
            raise OSError(5, "camera rejected value")
        if ctrl_id not in self.mismatch:
            self.values[ctrl_id] = value

    def refresh_flags(self):
        return None

    def close(self):
        self.closed = True


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/tmp")
        self.old_dir, self.old_file = store.CONFIG_DIR, store.CONFIG_FILE
        store.CONFIG_DIR = self.temp.name
        store.CONFIG_FILE = os.path.join(self.temp.name, "settings.json")

    def tearDown(self):
        store.CONFIG_DIR, store.CONFIG_FILE = self.old_dir, self.old_file
        self.temp.cleanup()

    def test_v1_settings_migrate_without_losing_controls(self):
        with open(store.CONFIG_FILE, "w") as f:
            json.dump({"MX Brio": {"controls": {"3": 77}}}, f)
        data = store.load()
        entry = store.camera_entry(data, FakeCamera())
        self.assertEqual({"3": 77}, entry["controls"])
        self.assertNotIn("MX Brio", data["legacy_cameras"])
        self.assertEqual("Streaming", entry["presets"]["streaming"]["name"])
        self.assertEqual("Video Calls", entry["presets"]["video-calls"]["name"])

    def test_identical_models_keep_separate_entries(self):
        data = store._empty_data()
        first = store.camera_entry(data, FakeCamera(key="usb:046d:0944:A"))
        second = store.camera_entry(
            data, FakeCamera(key="usb:046d:0944:B", path="/dev/video2")
        )
        first["controls"]["3"] = 10
        second["controls"]["3"] = 90
        self.assertEqual(2, len(data["cameras"]))
        self.assertEqual(10, data["cameras"]["usb:046d:0944:A"]["controls"]["3"])
        self.assertEqual(90, data["cameras"]["usb:046d:0944:B"]["controls"]["3"])

    def test_presets_create_update_delete_and_protect_builtins(self):
        entry = store.camera_entry(store._empty_data(), FakeCamera())
        preset_id = store.create_preset(entry, "  My  Studio  ", {"3": 55})
        self.assertEqual("My Studio", entry["presets"][preset_id]["name"])
        store.update_preset(entry, preset_id, {"3": 66})
        self.assertEqual({"3": 66}, entry["presets"][preset_id]["controls"])
        store.delete_preset(entry, preset_id)
        self.assertNotIn(preset_id, entry["presets"])
        with self.assertRaises(ValueError):
            store.update_preset(entry, "default", {"3": 1})
        with self.assertRaises(ValueError):
            store.delete_preset(entry, "streaming")

    def test_restore_orders_modes_verifies_values_and_reports_failures(self):
        cam = FakeCamera()
        cam.fail.add(2)
        cam.mismatch.add(3)
        result = store.apply_to_camera(cam, {"3": 70, "1": 1, "2": 4, "4": 9})
        self.assertEqual((1, 1), cam.set_calls[0])
        self.assertEqual((2, 4), cam.set_calls[1])
        self.assertEqual((3, 70), cam.set_calls[2])
        self.assertEqual(1, result.applied["1"])
        self.assertIn("2", result.failed)
        self.assertIn("camera reports", result.failed["3"])
        self.assertEqual("control is read-only", result.skipped["4"])

    def test_save_is_atomic_and_round_trips(self):
        data = store._empty_data()
        store.save(data)
        self.assertEqual(data, store.load())
        self.assertFalse(os.path.exists(store.CONFIG_FILE + ".tmp"))

    def test_apply_all_retries_a_failed_camera_restore(self):
        failed_cam = FakeCamera()
        failed_cam.fail.add(3)
        recovered_cam = FakeCamera()
        data = store._empty_data()
        entry = store.camera_entry(data, recovered_cam)
        entry["controls"] = {"3": 77}
        store.save(data)
        with mock.patch(
            "v4l2ctl.list_cameras", side_effect=[[failed_cam], [recovered_cam]]
        ), mock.patch.object(store.time, "sleep"):
            matched, result = store.apply_all(quiet=True, retry_seconds=10)
        self.assertEqual(1, matched)
        self.assertTrue(result.ok)
        self.assertEqual(77, recovered_cam.values[3])
        self.assertTrue(failed_cam.closed)
        self.assertTrue(recovered_cam.closed)


class CameraIdentityTests(unittest.TestCase):
    def test_serial_identity_distinguishes_identical_models(self):
        camera = object.__new__(v4l2ctl.Camera)
        camera.card = "MX Brio"
        camera.bus_info = "usb-0000:00:14.0-1"
        camera.path = "/dev/video0"
        camera._usb_identity = lambda: ("SERIAL1", "046d", "0944")
        self.assertEqual("usb:046d:0944:SERIAL1", camera.key)

    def test_bus_path_is_fallback_when_serial_is_missing(self):
        camera = object.__new__(v4l2ctl.Camera)
        camera.card = "MX Brio"
        camera.bus_info = "usb-0000:00:14.0-2"
        camera.path = "/dev/video2"
        camera._usb_identity = lambda: ("", "046d", "0944")
        self.assertEqual("bus:MX Brio:usb-0000:00:14.0-2", camera.key)


if __name__ == "__main__":
    unittest.main()
