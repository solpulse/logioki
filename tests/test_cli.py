import unittest
from unittest import mock

import logioki_cli
import store


class CommandLineTests(unittest.TestCase):
    def test_headless_apply_does_not_import_gui(self):
        result = store.RestoreResult(applied={"1": 1})
        with mock.patch.object(store, "apply_all", return_value=(1, result)) as apply_all:
            self.assertEqual(0, logioki_cli.main(["logioki", "--apply", "--retry", "5"]))
        apply_all.assert_called_once_with(retry_seconds=5)


if __name__ == "__main__":
    unittest.main()
