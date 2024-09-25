# pyre-unsafe
from unittest import mock, TestCase

from autoval.lib.utils.autoval_exceptions import TestError

from autoval_ssd.lib.utils.hdparm_utils import HdparmUtils
from autoval_ssd.unittest.mock.lib.mock_host import MockHost

CMDMAP = [
    {"cmd": "hdparm -W /dev/sda", "result": "write-caching =  0 (off)"},
    {"cmd": "ls /sys/block/sda/device/scsi_disk/", "result": "0:0:0:0"},
    {"cmd": "hdparm -W1 /dev/sda", "result": "write-caching =  1 (on)"},
    {
        "cmd": (
            "echo 'write through' > "
            "/sys/block/sda/device/scsi_disk/0:0:0:0/cache_type"
        ),
        "result": "pass",
    },
    {"cmd": "hdparm -W0 /dev/sda", "result": "write-caching =  1 (on)"},
    {"cmd": "hdparm -A /dev/sda", "result": "look-ahead    =  1 (on)"},
    {"cmd": "hdparm -A1 /dev/sda", "result": "look-ahead    =  1 (on)"},
    {"cmd": "hdparm -A0 /dev/sda", "result": "look-ahead    =  0 (on)"},
    {
        "cmd": "hdparm -I /dev/sda",
        "result": (
            "Security:\n"
            "         Master password revision code = 65534\n"
            "         supported\n"
            "         not     enabled\n"
            "         not     locked\n"
        ),
    },
    {
        "cmd": "time hdparm --user-master u --security-set-pass pass /dev/sda",
        "result": "Issuing SECURITY_SET_PASS command",
    },
    {
        "cmd": "time hdparm --user-master u --security-erase-enhanced pass /dev/sda",
        "result": "pass",
    },
    {
        "cmd": "time hdparm --user-master u --security-erase pass /dev/sda",
        "result": "pass",
    },
    {"cmd": "hdparm -Y /dev/sda", "result": "issuing sleep command"},
    {"cmd": "hdparm -y /dev/sda", "result": "issuing idle command"},
]


class HdparmUtilsUnitTest(TestCase):
    def setUp(self) -> None:
        """initializing the required variables with the required data"""
        self.mock_host = MockHost(cmd_map=CMDMAP)
        self.log = ""

    def mock_log(self, log):
        """Mock AutovalLog log_info"""
        self.log = log

    def test_get_write_cache(self):
        """unit test for the get_write_cache"""
        out = HdparmUtils.get_write_cache(self.mock_host, "sda")
        self.assertEqual(out, 0)

        # Exception block
        cmd = "hdparm -W /dev/sda"
        result = "write =  0 (off)"
        self.mock_host.update_cmd_map(cmd, result)
        with self.assertRaises(TestError) as exp:
            HdparmUtils.get_write_cache(self.mock_host, "sda")
        self.assertEqual(
            "[AUTOVAL TEST ERROR] Failed to get write cache. "
            "'hdparm' output: write =  0 (off)",
            str(exp.exception),
        )

    def test_enable_write_cache(self):
        """unit test for the enable write cache"""
        HdparmUtils.enable_write_cache(self.mock_host, "sda")

    def test_disable_write_cache(self):
        """unit test for the disable write cache"""
        HdparmUtils.disable_write_cache(self.mock_host, "sda")

    def test_power_sleep_hdd(self):
        """unit test for the power_sleep_hdd"""
        HdparmUtils.power_sleep_hdd(self.mock_host, "sda")

    def test_power_idle_hdd(self):
        """unit test for the power_idle_hdd"""
        HdparmUtils.power_idle_hdd(self.mock_host, "sda")

    def test_get_read_lookahead(self):
        """unit test for the get_read_lookahead"""
        out = HdparmUtils.get_read_lookahead(self.mock_host, "sda")
        self.assertEqual(out, 1)
        # Exception block
        cmd = "hdparm -A /dev/sda"
        result = "look-ahe    =  1 (on)"
        self.mock_host.update_cmd_map(cmd, result)
        with self.assertRaises(TestError) as exp:
            HdparmUtils.get_read_lookahead(self.mock_host, "sda")
        expected_out = (
            "[AUTOVAL TEST ERROR] Failed to get read lookahead. "
            "'hdparm' output: look-ahe    =  1 (on)"
        )
        self.assertEqual(expected_out, str(exp.exception))

    def test_enable_read_lookahead(self):
        """unit test for the enable_read_lookahead"""
        HdparmUtils.enable_read_lookahead(self.mock_host, "sda")

    def test_disable_read_lookahead(self):
        """unit test for the disable_read_lookahead"""
        HdparmUtils.disable_read_lookahead(self.mock_host, "sda")

    def test_is_drive_secure_with_password(self):
        """unit test for the ssd_secure_erase"""
        out = HdparmUtils.is_drive_secure_with_password(self.mock_host, "sda")
        self.assertEqual(out, False)
        cmd = "hdparm -I /dev/sda"
        result = (
            "Security:\n"
            "         Master password revision code = 65534\n"
            "         supported\n"
            "         enabled\n"
            "         not     locked\n"
        )
        self.mock_host.update_cmd_map(cmd, result)
        out = HdparmUtils.is_drive_secure_with_password(self.mock_host, "sda")
        self.assertEqual(out, True)
        # Negative test
        result = "Security:\n"
        self.mock_host.update_cmd_map(cmd, result)
        out = HdparmUtils.is_drive_secure_with_password(self.mock_host, "sda")
        self.assertEqual(out, False)
        # Exception block
        result = ""
        self.mock_host.update_cmd_map(cmd, result)
        with self.assertRaises(TestError) as exp:
            HdparmUtils.is_drive_secure_with_password(self.mock_host, "sda")
        self.assertIn("Unable to find security status on /dev/sda", str(exp.exception))

    @mock.patch.object(HdparmUtils, "is_drive_secure_with_password")
    def test_ssd_secure_erase(self, mock_drive_secure):
        """unit test for the ssd_secure_erase"""
        mock_drive_secure.return_value = False
        HdparmUtils.ssd_secure_erase(self.mock_host, "sda")
        mock_drive_secure.assert_called_once()

        # Exception block
        with mock.patch.object(
            self.mock_host,
            "run",
            side_effect=Exception("Error cmd failure in setting password for /dev/sda"),
        ):
            with self.assertRaises(TestError) as exp:
                HdparmUtils.ssd_secure_erase(self.mock_host, "sda")

            self.assertIn(
                "Error Error cmd failure in setting password", str(exp.exception)
            )
