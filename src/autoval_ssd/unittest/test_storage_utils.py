# pyre-ignore-all-errors

import unittest
from unittest.mock import Mock, patch

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.file_actions import FileActions
from autoval_ssd.lib.utils.storage.nvme.nvme_drive import NVMeDrive
from autoval_ssd.lib.utils.storage.storage_device_factory import StorageDeviceFactory
from autoval_ssd.lib.utils.storage.storage_utils import StorageUtils
from autoval_ssd.unittest.mock.lib.mock_host import MockHost

CMD_MAP = [
    {"cmd": "cat /proc/mdstat", "result": "md125 : active raid0 sda1[1] nvme0n1p1[0]"},
    {
        "cmd": "nvme ocp vs-smart-add-log /dev/nvme0n1 --json",
        "file": "nvme_smartaddlog.json",
    },
    {"cmd": "nvme list", "result": "/dev/nvme0n1"},
    {"cmd": "cat /sys/block/nvme0n1/queue/rotational", "result": "0"},
    {"cmd": "nvme list -o json", "file": "nvme_list.json"},
    {"cmd": "nvme id-ctrl /dev/nvme0n1 -o json", "file": "id_ctrl.json"},
    {"cmd": "nvme smart-log /dev/nvme0n1", "result": "temperature : 33 C"},
    {"cmd": "nvme smart-log /dev/nvme0n1 -o json", "file": "nvme_smartlog.json"},
    {
        "cmd": "lsblk -J",
        "result": """{
   "blockdevices": [
      {"name": "nvme0n1", "maj:min": "259:0", "rm": "0", "size": "238.5G", "ro": "0", "type": "disk", "mountpoint": null,
         "children": [
            {"name": "nvme0n1p1", "maj:min": "259:1", "rm": "0", "size": "243M", "ro": "0", "type": "part", "mountpoint": "/boot/efi"},
            {"name": "nvme0n1p2", "maj:min": "259:2", "rm": "0", "size": "488M", "ro": "0", "type": "part", "mountpoint": "/boot"},
            {"name": "nvme0n1p3", "maj:min": "259:3", "rm": "0", "size": "1.9G", "ro": "0", "type": "part", "mountpoint": "[SWAP]"},
            {"name": "nvme0n1p4", "maj:min": "259:4", "rm": "0", "size": "235.9G", "ro": "0", "type": "part", "mountpoint": "/"}
         ]
      }
   ]
}""",
    },
    {"cmd": "cat /sys/module/nvme_core/parameters/io_timeout", "result": "30"},
    {"cmd": "sudo echo 8 > /sys/module/nvme_core/parameters/io_timeout", "result": ""},
    {
        "cmd": "nvme ocp smart-add-log /dev/nvme0n1 -o json",
        "file": "nvme_ocp_command.json",
    },
]


class StorageUtilsUnitTest(unittest.TestCase):

    def setUp(self) -> None:
        self.host = MockHost(cmd_map=CMD_MAP)
        self.nvme0n1 = NVMeDrive(self.host, "nvme0n1")

    def mock_log(self, log) -> None:
        """Mock AutovalLog"""
        self.log = log

    def test_get_test_drives(self):
        """Unittest for Get Test Drives"""
        self.assertEqual(
            StorageUtils().get_test_drives(self.host, drive_type="md"),
            {"md125": "md125"},
        )
        with patch.object(StorageDeviceFactory, "_get_host", return_value=self.host):
            self.assertIsInstance(
                StorageUtils().get_test_drives(self.host, drives=["nvme0n1"])[
                    "nvme0n1"
                ],
                NVMeDrive,
            )
            self.assertIsInstance(
                StorageUtils().get_test_drives(
                    self.host,
                    drive_type="ssd",
                    drive_interface="nvme",
                    drives=["nvme0n1"],
                )["nvme0n1"],
                NVMeDrive,
            )

    @patch.object(StorageUtils, "save_drive_logs_async")
    def test_save_drive_logs(self, mock_async):
        """Unittest for Save Drive Logs"""
        mock_async.return_value = Mock()
        with patch.object(StorageDeviceFactory, "_get_host", return_value=self.host):
            StorageUtils().save_drive_logs(self.host, "/logs", block_names=["nvme0n1"])
        mock_async.assert_called_once()
        with self.assertRaises(TestError) as exp:
            StorageUtils().save_drive_logs(self.host, "/logs")
        self.assertRegex(str(exp.exception), r"Valid drive parameter not included")

    @patch.object(FileActions, "mkdirs")
    @patch.object(FileActions, "write_data")
    @patch.object(NVMeDrive, "collect_data")
    def test_save_single_drive_log(self, mock_data, mock_write_data, mock_make_dir):
        """Unittest for Save Single Drive log"""
        mock_make_dir.return_value = True
        mock_write_data.return_value = True
        mock_data.return_value = Mock()
        self.assertIsNone(
            StorageUtils().save_single_drive_log((self.nvme0n1, "00:01", "/tmp/logs"))
        )
        mock_make_dir.assert_called_once()
        mock_write_data.assert_called_once()
        with self.assertRaises(TestError) as exp:
            StorageUtils().save_single_drive_log([])
        self.assertRegex(str(exp.exception), r".*Drive logging requires Tuple.*")

    @patch.object(AutovalLog, "log_info")
    def test_print_drive_summary(self, mock_loginfo):
        """Unittest for Print Drive Summary"""
        mock_loginfo.side_effect = self.mock_log
        self.assertIsNone(StorageUtils().print_drive_summary([self.nvme0n1]))
        self.assertRegex(self.log, r"X123: nvme0n1")

    def test_group_drive_by_attr(self):
        """Unittest for Group Drive by Attributes"""
        self.assertEqual(
            StorageUtils().group_drive_by_attr("model", [self.nvme0n1]),
            {"Unknown": ["nvme0n1"]},
        )
        self.assertNotEqual(
            StorageUtils().group_drive_by_attr("", []), {"Unknown": ["Unknown"]}
        )

    def test_group_drive_by_firmware(self):
        """Unittest for Group drive by Firmware"""
        self.assertEqual(
            StorageUtils().group_drive_by_firmware([self.nvme0n1]),
            {"X123": ["nvme0n1"]},
        )
        self.assertNotEqual(
            StorageUtils().group_drive_by_firmware([]), {"Unknown": ["Unknown"]}
        )

    def test_get_all_drives_temperature(self):
        """Unittest for Get All Drives Temperature"""
        self.assertEqual(
            StorageUtils.get_all_drives_temperature([self.nvme0n1]), {"nvme0n1": 33}
        )

    @patch.object(AutovalLog, "log_debug")
    @patch.object(AutovalUtils, "validate_equal")
    @patch.object(FileActions, "exists")
    @patch.object(AutovalLog, "log_info")
    def test_change_nvme_io_timeout(
        self, mock_log_info, mock_file_exists, mock_validate_equal, mock_log_debug
    ):
        """Unittest for change NVME IO timeout value"""
        nvme_io_timeout_file_absolute_path = (
            "/sys/module/nvme_core/parameters/io_timeout"
        )
        # Pass test case where file exist , Argument  passed is also integer
        mock_file_exists.return_value = True
        StorageUtils.change_nvme_io_timeout(self.host, "startup()", 8)
        mock_validate_equal.assert_called_with(
            "30",
            "8",
            " In startup() phase - Validate NVME IO timeout value",
            component=COMPONENT.SSD,
            error_type=ErrorType.DRIVE_ERR,
        )
        # Pass test case where file does not exist , Argument  passed is also integer
        mock_file_exists.return_value = False
        StorageUtils.change_nvme_io_timeout(self.host, "startup()", 8)
        mock_log_debug.assert_called_with(
            f"{nvme_io_timeout_file_absolute_path} NVME io_timeout file does not exist in DUT , Creating file"
        )
        mock_validate_equal.assert_called_with(
            "30",
            "8",
            " In startup() phase - Validate NVME IO timeout value",
            component=COMPONENT.SSD,
            error_type=ErrorType.DRIVE_ERR,
        )

    @patch.object(AutovalUtils, "validate_equal")
    @patch.object(AutovalLog, "log_info")
    def test_validate_persistent_event_log_support(
        self, mock_log, mock_validate_equal
    ) -> None:
        mock_cmd = "nvme get-log -i 0xd --lpo=480 --lsp=0 -l 32 /dev/nvme0n1"
        mock_cmd_output = 'Device:nvme0n1 log-id:13 namespace-id:0xffffffff\n       0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f\n0000: fe ff 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ".7.............."\n0010: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "................"'
        mock_log.side_effect = self.mock_log
        self.host.update_cmd_map(mock_cmd, mock_cmd_output)
        StorageUtils().validate_persistent_event_log_support(self.host, "nvme0n1")  # type: ignore
        mock_cmd_output_2 = 'Device:nvme0n1 log-id:13 namespace-id:0xffffffff\n       0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f\n0000: fe 37 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ".7.............."\n0010: 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "................"'
        self.host.update_cmd_map(mock_cmd, mock_cmd_output_2)
        StorageUtils().validate_persistent_event_log_support(self.host, "nvme0n1")  # type: ignore
        mock_validate_equal.assert_called_with(
            1,
            0,
            "Not supported Persistent Event log type list is ['Set Feature Event Support']",
            component=COMPONENT.SSD,
            error_type=ErrorType.DRIVE_ERR,
        )
