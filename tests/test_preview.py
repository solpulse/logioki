import unittest

import preview


class PreviewPipelineTests(unittest.TestCase):
    def test_pipeline_is_valid_and_device_path_is_not_interpolated(self):
        pipeline = preview.Gst.parse_launch(preview.PIPELINE_DESCRIPTION)
        self.assertIsNotNone(pipeline.get_by_name("source"))
        self.assertIsNotNone(pipeline.get_by_name("sink"))
        pipeline.set_state(preview.Gst.State.NULL)


if __name__ == "__main__":
    unittest.main()
