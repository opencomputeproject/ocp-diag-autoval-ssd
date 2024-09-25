# pyre-unsafe
import time
import unittest
import unittest.mock as mock
from unittest.mock import patch

from autoval.lib.transport.ssh import SSHConn
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.file_actions import FileActions

from autoval_ssd.lib.utils.scrtnycli_utils import ScrtnyCli
from autoval_ssd.lib.utils.storage.drive import Drive, DriveType
from autoval_ssd.unittest.mock.lib.mock_host import MockHost

CMD_MAP = [
    {"cmd": "smartctl -x /dev/sda", "result": "=== START OF INFORMATION SECTION ==="},
    {"cmd": "smartctl -x /dev/sdb", "file": "smartctl_x_sda"},
    {"cmd": "cat /sys/block/sdb/queue/rotational", "result": "0"},
    {"cmd": "cat /sys/block/sda/queue/rotational", "result": "0"},
    {
        "cmd": "smartctl -A /dev/sda",
        "result": "194 Temperature_Celsius     0x0022   075   043"
        "   ---    Old_age   Always       -       25 (Min/Max 20/43)",
    },
    {
        "cmd": "lsiutil -p1 -a 19,,0,0 20",
        "result": " 3.  0   2  Disk       WDC      WUH721414AL4204  C221",
    },
    {
        "cmd": "lsiutil -p1 -s",
        "result": " 0   2   0  Disk       WDC      WUH721414AL4204  C221  5000cca25885c9c9     2",
    },
    {
        "cmd": "sg_readcap /dev/sda",
        "result": "Device size: 256060514304 bytes, 244198.3 MiB, 256.06 GB",
    },
    {
        "cmd": "fbjbod list --json",
        "result": '{"/dev/sg37": {"sg_device": "/dev/sg37",'
        ' "bsg_device": "/dev/bsg/6:0:36:0", "name": "BryceCanyon"}}',
    },
    {
        "cmd": "fbjbod hdd --json /dev/sg37",
        "result": """{"/dev/sg37": {"Device00             ":
            {"name": "Device00             ", "slot": "0",
             "phy": "2", "status": "Power On", "devname": "/dev/sda"}}}""",
    },
]


# Decorator for common mocks.
def apply_mock(func):
    def mocking(*args, **kwargs):
        mock_host = MockHost(cmd_map=CMD_MAP)
        with mock.patch.object(SSHConn, "run", side_effect=mock_host.run):
            func(*args, **kwargs)

    return mocking


class DriveUnitTest(unittest.TestCase):
    @apply_mock
    @mock.patch.object(AutovalLog, "log_info")
    def setUp(self, mock_log) -> None:
        self.host = MockHost(cmd_map=CMD_MAP)
        self.drive_sda = Drive(self.host, "sda")
        self.drive_sdb = Drive(self.host, "sdb")
        self.drive_emmc = Drive(self.host, "mmcblk0")
        self.log = ""

    def get_logger(self, out: str):
        """method will override the Autoval.log_info"""
        self.log += out

    @apply_mock
    def test_get_smartctl_output(self):
        # valid smartctl output
        result = "=== START OF INFORMATION SECTION ==="
        self.assertEqual(self.drive_sda.get_smartctl_output(), result)
        # Invalid smartctl output
        cmd = "smartctl -x /dev/sda"
        self.host.update_cmd_map(cmd, "")
        with self.assertRaises(TestError) as exp:
            self.drive_sda.get_smartctl_output()
        self.assertEqual(
            "[AUTOVAL TEST ERROR] Failed to get SMART for /dev/sda: ",
            str(exp.exception),
        )

    def test_extract_smart_field(self):
        # checking smart health output for sata drive - valid case
        pattern = r"SMART overall-health self-assessment test result: (\w+)"
        smart_data = """=== START OF READ SMART DATA SECTION ===
            SMART overall-health self-assessment test result: PASSED
        """
        self.assertEqual(
            self.drive_sda.extract_smart_field("Health status", smart_data, pattern),
            "PASSED",
        )
        # checking smart health output for sata drive - invalid case
        smart_data = """=== START OF READ SMART DATA SECTION ===
            SMART health self-assessment test result: PASSED
        """
        with self.assertRaises(TestError) as exp:
            self.drive_sda.extract_smart_field("Health status", smart_data, pattern)
        self.assertEqual(
            "[AUTOVAL TEST ERROR] Didn't find Health status in SMART output",
            str(exp.exception),
        )

    @apply_mock
    def test_get_type(self):
        # Asserting for all the drive types
        self.assertEqual(self.drive_emmc.get_type(), DriveType.EMMC)
        cmd = "cat /sys/block/sda/queue/rotational"
        try:
            self.assertEqual(self.drive_sda.get_type(), DriveType.SSD)
            self.host.update_cmd_map(cmd, "1")
            self.assertEqual(self.drive_sda.get_type(), DriveType.HDD)
            self.host.update_cmd_map(cmd, "2")
            # Invalid case where the unknown type is in output
            with self.assertRaises(Exception) as exp:
                self.drive_sda.get_type()
            self.assertEqual("Unknown device type '2'", str(exp.exception))
        finally:
            self.host.update_cmd_map(cmd, "0")

    @apply_mock
    @mock.patch.object(time, "sleep")
    def test_reset(self, mock_sleep):
        # Assert Method not implemented for SAS and SATA drive
        with self.assertRaises(NotImplementedError) as exp:
            self.drive_sda.reset()
        self.assertEqual("Reset method not implemented", str(exp.exception))

        # valid case
        if self.drive_sda.type == DriveType.HDD:
            self.drive_sda.reset()  # This should not raise an error

    @apply_mock
    def test_get_drive_temperature(self):
        # Drive temperature for SAS drive output
        self.assertEqual(self.drive_sda.get_drive_temperature(), 25)
        # Drive temperature for SATA drive output
        cmd = "smartctl -A /dev/sda"
        mock_output = "Current Drive Temperature:     31 C"
        self.host.update_cmd_map(cmd, mock_output)
        self.assertEqual(self.drive_sda.get_drive_temperature(), 31)
        # Exceptional case where drive temperature is not present
        self.host.update_cmd_map(cmd, "")
        with self.assertRaises(Exception) as exp:
            self.drive_sda.get_drive_temperature()
        self.assertEqual(
            "Current Drive Temperature not in output: ", str(exp.exception)
        )

    def test_move_smart_to_upper_level(self):
        samrt_drive_info = {"SMART": {"health": "OK", "element_in_grown_defect": 0}}
        drive_info = {"health": "OK", "element_in_grown_defect": 0}
        # smart drive info dict with "SMART" key
        self.assertDictEqual(
            self.drive_sda.move_smart_to_upper_level(samrt_drive_info), drive_info
        )
        # smart drive info dict without "SMART" key
        self.assertDictEqual(
            self.drive_sda.move_smart_to_upper_level(drive_info), drive_info
        )

    @apply_mock
    def test_get_capacity(self):
        self.assertEqual(self.drive_sda.get_capacity(), 256060514304)

    @apply_mock
    @mock.patch.object(Drive, "collect_data")
    def test_collect_data_in_config_check_format(self, mock_smart_data):
        mock_smart_data.return_value = {
            "SMART": {"health": "PASSED", "Power_Cycle_Count-raw": 1454},
            "block_name": "sda",
            "serial_number": "19208A800175",
        }
        result = {
            "19208A800175": {
                "block_name": "sda",
                "serial_number": "19208A800175",
                "health": "PASSED",
                "Power_Cycle_Count-raw": 1454,
            }
        }
        self.assertDictEqual(
            self.drive_sda.collect_data_in_config_check_format(), result
        )

    def test__str__(self):
        self.assertEqual(self.drive_sda.__str__(), "sda")

    def test__repr__(self):
        self.assertEqual(self.drive_sda.__repr__(), "sda")

    def test_is_drive_degraded(self):
        # Raising assert for method not implemented, valid are implemented
        # in derived class
        with self.assertRaises(NotImplementedError) as exp:
            self.drive_sda.is_drive_degraded()
        self.assertEqual(
            "Drive Degrade functionality is not implemented", str(exp.exception)
        )

    @patch.object(MockHost, "run")
    def test_check_lsiutil(self, mock):
        self.drive_sda.check_lsiutil()
        mock.assert_called_once_with("lsiutil")

    @patch.object(ScrtnyCli, "update_firmware_scrtnycli")
    @patch.object(ScrtnyCli, "scan_drive_scrtnycli")
    @patch.object(FileActions, "get_local_path")
    @patch.object(ScrtnyCli, "deploy_scrtnycli")
    def test_firmware_update_with_scrtnycli(
        self,
        mock_deploy_scrtnycli,
        mock_local_path,
        mock_scan_drive_scrtnycli,
        mock_firmware_scrtnycli,
    ):
        mock_local_path.return_value = "/mock/path"
        mock_deploy_scrtnycli.return_value = None
        cmd = "./scrtnycli.x86_64 -i 1 scan | grep Disk"
        self.host.update_cmd_map(
            cmd,
            "0   19  0   3   Disk       ATA      TOSHIBA MG08ACA1 CB58 5001B448B8B444FF",
        )
        mock_scan_drive_scrtnycli.return_value = (
            "0   19  0   3   Disk       ATA      TOSHIBA MG08ACA1 CB58 5001B448B8B444FF"
        )
        mock_firmware_scrtnycli.return_value = None
        self.drive_sdb.update_firmware_with_scrtnycli("/mock/path")
