import os
import tempfile
import unittest
from unittest import mock

import logioki


class RestoreServiceTests(unittest.TestCase):
    def test_install_writes_retrying_unit_and_enables_it(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            unit_path = os.path.join(directory, "logioki-restore.service")
            with mock.patch.object(logioki, "SYSTEMD_UNIT", unit_path), mock.patch.object(
                logioki.subprocess, "run"
            ) as run:
                ok, error = logioki.install_restore_service()
            self.assertTrue(ok, error)
            with open(unit_path) as f:
                unit = f.read()
            self.assertIn("--apply --retry=30", unit)
            self.assertIn("WantedBy=default.target", unit)
            self.assertEqual("daemon-reload", run.call_args_list[0].args[0][-1])
            self.assertIn("enable", run.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
