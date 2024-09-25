# pyre-unsafe
import unittest
from unittest.mock import MagicMock, patch

from autoval.lib.connection.connection_utils import CmdResult
from autoval.lib.utils.autoval_exceptions import TestError
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeDeviceEnum, NVMeUtils
from autoval_ssd.unittest.mock.lib.mock_host import MockHost

CMD_MAP = [
    {"cmd": "nvme id-ctrl /dev/nvme0n1 -o json", "result": '{"vid": 5197}'},
    {"cmd": "nvme id-ns /dev/nvme0n1 -o json -n 1", "result": '{"nsze" : 123}'},
    {"cmd": "nvme list -o json", "file": "nvme_list.json"},
    {"cmd": "nvme list-ns /dev/nvme0n1", "result": "[   0]:0x1"},
    {
        "cmd": "nvme create-ns -f 0 /dev/nvme0 -s 123 -c 123",
        "result": "create-ns: Success",
    },
    {
        "cmd": "nvme create-ns -f 1 /dev/nvme0 -s 123 -c 123",
        "result": "create-ns: Success",
    },
    {"cmd": "nvme attach-ns /dev/nvme0 -n 123 -c 123", "result": "attach-ns: Success"},
    {"cmd": "nvme detach-ns /dev/nvme0 -n 123 -c 123", "result": "detach-ns: Success"},
    {"cmd": "nvme delete-ns /dev/nvme0n1 -n 1", "result": ""},
    {"cmd": "nvme reset /dev/nvme0n1", "result": ""},
    {"cmd": "nvme smart-log /dev/nvme0n1", "result": "temperature : 35 C"},
    {
        "cmd": "nvme id-ctrl /dev/nvme0n1 -H | grep -v fguid",
        "result": " NS Management and Attachment Supported",
    },
    {
        "cmd": "nvme get-feature /dev/nvme0 -f 0x6",
        "result": "Current value: 3",
    },
    {
        "cmd": "nvme ocp smart-add-log /dev/nvme0",
        "result": "NVME SUCCESS",
    },
]


class NvmeUtilsUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.host = MockHost(cmd_map=CMD_MAP)

    def test_format_nvme(self):
        # Scenario 1: with block size set
        dummy_host = MagicMock()
        NVMeUtils.format_nvme(
            dummy_host, "dummy_device", "dummy_secure_erase_option", 4096
        )
        dummy_host.run.assert_called_with(
            cmd="nvme format /dev/dummy_device -s dummy_secure_erase_option -r -b 4096",
            timeout=3610,
        )

        # Scenario 2: block size is not set
        dummy_host.reset()
        NVMeUtils.format_nvme(dummy_host, "dummy_device", "dummy_secure_erase_option")
        dummy_host.run.assert_called_with(
            cmd="nvme format /dev/dummy_device -s dummy_secure_erase_option -r",
            timeout=3610,
        )

        # Scenario 3: with lba format set
        dummy_host.reset()
        NVMeUtils.format_nvme(
            dummy_host,
            "dummy_device",
            "dummy_secure_erase_option",
            nvme_format_args=" -l 0",
        )
        dummy_host.run.assert_called_with(
            cmd="nvme format /dev/dummy_device -s dummy_secure_erase_option -r -l 0",
            timeout=3610,
        )

    def test_get_nvme_device_type(self):
        drives = {
            "xyz": NVMeDeviceEnum.INVALID,
            "nvme0": NVMeDeviceEnum.CHARACTER,
            "nvme0n1": NVMeDeviceEnum.BLOCK,
            "nvme0n1p1": NVMeDeviceEnum.PARTITION,
        }
        for dev, output in drives.items():
            device_type = NVMeUtils.get_nvme_device_type(dev)
            self.assertEqual(device_type, output)

    def test_get_id_ctrl(self):
        self.assertDictEqual(NVMeUtils.get_id_ctrl(self.host, "nvme0n1"), {"vid": 5197})

    def test_get_id_ns(self):
        self.assertDictEqual(
            NVMeUtils.get_id_ns(self.host, "nvme0n1", 1), {"nsze": 123}
        )
        with self.assertRaises(TestError) as exp:
            NVMeUtils.get_id_ns(self.host, "nvme0n1p1")
        self.assertRegex(str(exp.exception), r".*nvme0n1p1 is of type 3.*")
        with self.assertRaises(TestError) as exp:
            NVMeUtils.get_id_ns(self.host, "nvme0")
        self.assertRegex(
            str(exp.exception), r".*delete_ns: missing NSID for char dev nvme0"
        )

    def test_get_vendor_id(self):
        self.assertEqual(NVMeUtils.get_vendor_id(self.host, "nvme0n1"), 5197)

    def test_get_nvme_list(self):
        device = [
            {
                "DevicePath": "/dev/nvme0n1",
                "Firmware": "X123",
                "Index": 0,
                "ModelNumber": "Unknown",
                "ProductName": "Unknown device",
                "SerialNumber": "Sxxxxx",
                "UsedBytes": 366898667520,
                "MaximumLBA": 125026902,
                "PhysicalSize": 512110190592,
                "SectorSize": 4096,
            }
        ]
        self.assertListEqual(NVMeUtils.get_nvme_list(self.host), device)

    def test_get_from_nvme_list(self):
        self.assertEqual(
            NVMeUtils.get_from_nvme_list(self.host, "nvme0n1", "Firmware"), "X123"
        )
        with self.assertRaises(TestError) as exp:
            NVMeUtils.get_from_nvme_list(self.host, "nvme1n1", "Firmware")
        self.assertRegex(
            str(exp.exception), r".*Unable to find DevicePath for nvme1n1.*"
        )
        with self.assertRaises(TestError) as exp:
            NVMeUtils.get_from_nvme_list(self.host, "nvme0n1", field=None)
        self.assertRegex(str(exp.exception), r".*Unable to find None.*")

    def test_get_nvme_ns_map(self):
        self.assertDictEqual(
            NVMeUtils.get_nvme_ns_map(self.host, "nvme0n1", "Sxxxxx"),
            {"nvme0": ["nvme0n1"]},
        )
        with self.assertRaises(TestError) as exp:
            NVMeUtils.get_nvme_ns_map(self.host, "sda", "X123")
        self.assertRegex(str(exp.exception), r".*NVME drives not found.*")

    def test_get_nvme_temperature(self):
        self.assertListEqual(
            NVMeUtils.get_nvme_temperature(self.host, ["nvme0n1"]), [35]
        )
        self.assertListEqual(NVMeUtils.get_nvme_temperature(self.host, []), [])

    @patch.object(MockHost, "run")
    def test_get_write_cache(self, mock_object):
        mock_object.side_effect = [
            "Current value:0x0006",
            "NVMe Status:INVALID_FIELD: A reserved coded value",
        ]
        self.assertEqual(NVMeUtils.get_write_cache(self.host, "nvme0n1"), 6)
        self.assertEqual(NVMeUtils.get_write_cache(self.host, "nvme0n1"), None)

    def test_list_ns(self):
        self.assertListEqual(NVMeUtils.list_ns(self.host, "nvme0n1"), [1])

    def test_delete_ns(self):
        self.assertIsNone(NVMeUtils.delete_ns(self.host, "nvme0n1"))
        self.assertIsNone(NVMeUtils.delete_ns(self.host, "nvme0n1", [1]))
        with self.assertRaises(TestError) as exp:
            NVMeUtils.delete_ns(self.host, "nvme0n1p1")
        self.assertRegex(str(exp.exception), r".*nvme0n1p1 is of type 3.*")

    def test_create_ns(self):
        self.assertEqual(
            NVMeUtils.create_ns(self.host, "nvme0", 123, 123, 4096, 0),
            "create-ns: Success",
        )
        self.assertEqual(
            NVMeUtils.create_ns(self.host, "nvme0", 123, 123, 512, 0),
            "create-ns: Success",
        )
        with self.assertRaises(TestError) as exp:
            NVMeUtils.create_ns(self.host, "nvme0n1", 123, 123, 4096, 0)
        self.assertRegex(str(exp.exception), r".*nvme0n1 is of type 1.*")

        with self.assertRaises(TestError) as exp:
            NVMeUtils.create_ns(self.host, "nvme0n1", 123, 123, 512, 0)
        self.assertRegex(str(exp.exception), r".*nvme0n1 is of type 1.*")

    def test_attach_ns(self):
        self.assertEqual(
            NVMeUtils.attach_ns(self.host, "nvme0", 123, 123), "attach-ns: Success"
        )
        with self.assertRaises(TestError) as exp:
            NVMeUtils.attach_ns(self.host, "nvme0n1", 123, 123)
        self.assertRegex(str(exp.exception), r".*nvme0n1 is of type 1.*")

    def test_detach_ns(self):
        self.assertEqual(
            NVMeUtils.detach_ns(self.host, "nvme0", 123, 123), "detach-ns: Success"
        )
        with self.assertRaises(TestError) as exp:
            NVMeUtils.detach_ns(self.host, "nvme0n1", 123, 123)
        self.assertRegex(str(exp.exception), r".*nvme0n1 is of type 1.*")

    def test_reset(self):
        self.assertEqual(NVMeUtils.reset(self.host, "nvme0"), None)
        with self.assertRaises(TestError) as exp:
            NVMeUtils.reset(self.host, "nvme0n1")
        self.assertRegex(str(exp.exception), r".*nvme0n1 is of type 1.*")

    def test_get_nvmedrive_temperature(self):
        self.assertEqual(NVMeUtils.get_nvme_temperature(self.host, ["nvme0n1"]), [35])

    @patch.object(MockHost, "run_get_result")
    def test_is_read_only(self, mock_run):
        mock_blk_name = "nvme0n1"

        def critical_warning(stdout: str) -> CmdResult:
            return CmdResult(
                command="",
                stdout=stdout,
                stderr="",
                return_code=0,
                duration=1.0,
            )

        mock_run.side_effect = [
            critical_warning(stdout='{"critical_warning": 0}'),  # 0x0000
            critical_warning(stdout='{"critical_warning": 8}'),  # 0x1000
            critical_warning(stdout='{"critical_warning": 6}'),  # 0x0101
            critical_warning(stdout='{"critical_warning": 15}'),  # 0x1111
        ]
        self.host.is_container = False
        self.assertFalse(NVMeUtils.is_read_only(self.host, mock_blk_name))
        self.assertTrue(NVMeUtils.is_read_only(self.host, mock_blk_name))
        self.assertFalse(NVMeUtils.is_read_only(self.host, mock_blk_name))
        self.assertTrue(NVMeUtils.is_read_only(self.host, mock_blk_name))

    def test_get_namespace_support_drive_list(self):
        self.assertListEqual(
            NVMeUtils.get_namespace_support_drive_list(self.host, ["nvme0n1"]),
            ["nvme0n1"],
        )

    @patch.object(MockHost, "run")
    def test_set_thermal_management(self, mock_run):
        mock_run.side_effect = [
            "NVMe Status: ACTIVE",
            "NVMe Status:INVALID_FIELD: A reserved coded value",
        ]
        out = NVMeUtils.set_thermal_management(self.host, "dummy_device", 12)
        self.assertEqual(out, True)

        out = NVMeUtils.set_thermal_management(self.host, "dummy_device", 12)
        self.assertEqual(out, False)

    @patch.object(MockHost, "run_get_result")
    def test_get_id_ctrl_normal_data(self, mock) -> None:
        NVMeUtils.get_id_ctrl_normal_data(self.host, "nvme0n1")
        mock.assert_called_once_with(
            "nvme id-ctrl /dev/nvme0n1 -o normal | grep -v fguid"
        )

    @patch.object(MockHost, "run")
    def test_run_nvme_security_recv_cmd(self, mock_run):
        mock_run.return_value = """NVME Security Receive Command Success:0
       0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
0000: 00 00 00 d8 00 00 00 01 00 00 00 00 00 00 00 00 "................"""
        out = NVMeUtils.run_nvme_security_recv_cmd(self.host, "nvme1n1")
        self.host.run.assert_called_with(
            "nvme security-recv -p 0x1 -s 0x1 -t 256 -x 256 /dev/nvme1n1"
        )
        self.assertEqual(
            out,
            """NVME Security Receive Command Success:0
       0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
0000: 00 00 00 d8 00 00 00 01 00 00 00 00 00 00 00 00 "................""",
        )
