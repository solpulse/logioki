import threading
import unittest
from unittest import mock

import preview


class PreviewPipelineTests(unittest.TestCase):
    def test_pipeline_is_valid_and_device_path_is_not_interpolated(self):
        pipeline = preview.Gst.parse_launch(preview.PIPELINE_DESCRIPTION)
        self.assertIsNotNone(pipeline.get_by_name("source"))
        self.assertIsNotNone(pipeline.get_by_name("sink"))
        pipeline.set_state(preview.Gst.State.NULL)

    def test_stale_frame_cannot_clear_or_replace_current_generation(self):
        widget = preview.Preview.__new__(preview.Preview)
        widget._state_lock = threading.Lock()
        widget._generation = 2
        widget._pending_generation = 2
        widget._idle_id = 22
        widget._idle_generation = 2
        widget.pipeline = mock.Mock()
        widget.set_paintable = mock.Mock()

        result = widget._show_frame(1, b"stale", 1, 1, 3)

        self.assertEqual(preview.GLib.SOURCE_REMOVE, result)
        self.assertEqual(2, widget._pending_generation)
        self.assertEqual(22, widget._idle_id)
        widget.set_paintable.assert_not_called()


if __name__ == "__main__":
    unittest.main()
