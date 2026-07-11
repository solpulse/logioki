import unittest

import flatpak_portal


class FlatpakPortalTests(unittest.TestCase):
    def test_expected_request_handle_uses_dbus_sender_and_token(self):
        class Connection:
            def baseService(self):
                return ":1.204"

        self.assertEqual(
            "/org/freedesktop/portal/desktop/request/1_204/logioki_token",
            flatpak_portal._expected_handle(Connection(), "logioki_token"),
        )


if __name__ == "__main__":
    unittest.main()
