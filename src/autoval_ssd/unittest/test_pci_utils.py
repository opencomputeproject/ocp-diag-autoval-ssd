# pyre-unsafe
from unittest import mock, TestCase

from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils

from autoval_ssd.lib.utils.pci_utils import PciUtils
from autoval_ssd.unittest.mock.lib.mock_host import MockHost

MOCK_INPUT_PATH = "autoval_ssd/unittest/mock/util_outputs/"

CMD_MAP = [
    {"cmd": "lspci -v", "file": "lspci_vvv_1"},
    {"cmd": "ipmitool fru list", "result": "BIGSUR"},
    {"cmd": "lspci -vvv", "file": "lspci_vvv_3"},
    {"cmd": "cat /sys/block/nvme1/queue/rotational", "result": "0"},
    {"cmd": "ls -l /sys/block/nvme0n1", "result": "0000:01:00.0/nvme/nvme0/nvme0n1"},
    {"cmd": "ls -l /sys/block/nvme0n1", "result": "0000:01:00.0/nvme/nvme0/nvme0n1"},
    {"cmd": "setpci -s 01:00.0 CAP_EXP+0x28.w", "result": "0410"},
    {"cmd": "ls -l /sys/block/nvme1n1", "result": "0000:02:00.0/nvme/nvme0/nvme1n1"},
    {"cmd": "setpci -s 02:00.0 CAP_EXP+0x28.w", "result": None},
    {
        "cmd": "ls /sys/bus/pci/devices/",
        "result": "0000:00:00.0 0000:00:04.0 0000:00:04.1",
    },
    {"cmd": "cat /sys/bus/pci/devices/0000:00:00.0/device", "result": "0x2020"},
    {"cmd": "cat /sys/bus/pci/devices/0000:00:00.0/vendor", "result": "0x8086"},
    {"cmd": "cat /sys/bus/pci/devices/0000:00:00.0/class", "result": "0x060000"},
    {"cmd": "cat /sys/bus/pci/devices/0000:00:00.0/max_link_speed", "result": "8 GT/s"},
    {
        "cmd": "cat /sys/bus/pci/devices/0000:00:00.0/subsystem_vendor",
        "result": "0x8086",
    },
    {
        "cmd": "cat /sys/bus/pci/devices/0000:00:00.0/subsystem_device",
        "result": "0x0000",
    },
    {"cmd": "cat /sys/bus/pci/devices/0000:00:00.0/max_link_width", "result": 4},
    {
        "cmd": "cat /sys/bus/pci/devices/0000:00:00.0/current_link_speed",
        "result": "Unknown speed",
    },
    {"cmd": "cat /sys/bus/pci/devices/0000:00:00.0/current_link_width", "result": "0"},
    {
        "cmd": "cat /sys/bus/pci/devices/0000:00:00.0/aer* | grep -vP ' 0|^0$'",
        "result": "0",
    },
]


class PciUtilsUnittest(TestCase):
    def setUp(self) -> None:
        self.mock_host = MockHost(cmd_map=CMD_MAP)
        self.pci_utils = PciUtils()

    def test_get_lspci_output(self):
        """unit test for get_lspci_output"""
        # Without exclude
        out = self.pci_utils.get_lspci_output(self.mock_host, options="-v")
        self.assertIn(
            r"",
            out,
        )
        self.assertNotIn(
            r"00:00.7 Host bridge: Unknown Vendor DMI3 Registers (rev 04)",
            out,
        )
        # With exclude
        out = self.pci_utils.get_lspci_output(
            self.mock_host, options="-v", exclude=["DevSta", "Status"]
        )
        self.assertNotIn(
            r"Status: Cap+ 66MHz- UDF- FastB2B- ParErr- DEVSEL=fast >TAbort- ",
            out,
        )

    def test_get_lspci_verbose(self):
        """unit test for get_lspci_verbose"""
        # Validate BIGSUR condition
        cmd = "lspci -v"
        mock_output = "lspci_vvv_3"
        self.mock_host.update_cmd_map(cmd, mock_output)
        out = self.pci_utils.get_lspci_verbose(self.mock_host)
        self.assertIsInstance(out, dict)

        # Validate for else condition
        cmd = "ipmitool fru list"
        mock_output = " "
        self.mock_host.update_cmd_map(cmd, mock_output)
        out = self.pci_utils.get_lspci_verbose(self.mock_host)

    def test_compare_lspci_lnksta_lnkcap(self):
        """unit test for compare_lspci_lnksta_lnkcap"""
        lspci_out = (
            "3c:00.0 Non-Volatile memory controller: Unknown Vendor "
            "NVMe SSD "
            "Controller SM981/PM981/PM983 (prog-if 02 [NVM Express])\n"
            "     LnkCap: Port #0, Speed 8GT/s, Width x4, ASPM not supported\n"
            "     LnkSta: Speed 8GT/s, Width x4, TrErr- Train- SlotClk+ DLActive- "
            "BWMgmt- ABWMgmt-"
        )
        out = self.pci_utils.compare_lspci_lnksta_lnkcap(lspci_out)
        lspci_lnksta_lnkcap_output = "'cap_speed' 8GT compare to 'sta_speed' 8GT: PASS"
        self.assertIn(lspci_lnksta_lnkcap_output, out)

        # Validation for speed  mismatch case
        lspci_out = (
            "3c:00.0 Non-Volatile memory controller: Unknown Vendor "
            "NVMe SSD "
            "Controller SM981/PM981/PM983 (prog-if 02 [NVM Express])\n"
            "     LnkCap: Port #0, Speed 7GT/s, Width x4, ASPM not supported\n"
            "     LnkSta: Speed 8GT/s, Width x4, TrErr- Train- SlotClk+ DLActive- "
            "BWMgmt- ABWMgmt-"
        )
        out = self.pci_utils.compare_lspci_lnksta_lnkcap(lspci_out)
        lspci_lnksta_lnkcap_output = "'cap_speed' 7GT compare to 'sta_speed' 8GT: FAIL"
        self.assertIn(lspci_lnksta_lnkcap_output, out)

        # Validation for width mismatch case
        lspci_out = (
            "3c:00.0 Non-Volatile memory controller: Unknown Vendor "
            "NVMe SSD "
            "Controller SM981/PM981/PM983 (prog-if 02 [NVM Express])\n"
            "     LnkCap: Port #0, Speed 7GT/s, Width x6, ASPM not supported\n"
            "     LnkSta: Speed 8GT/s, Width x4, TrErr- Train- SlotClk+ DLActive- "
            "BWMgmt- ABWMgmt-"
        )
        out = self.pci_utils.compare_lspci_lnksta_lnkcap(lspci_out)
        lspci_lnksta_lnkcap_output = "'cap_width' x6 compare to 'sta_width' x4: FAIL"
        self.assertIn(lspci_lnksta_lnkcap_output, out)

        # Validation for speed and width is null
        lspci_out = (
            "3c:00.0 Non-Volatile memory controller: Unknown Vendor "
            "NVMe SSD "
            "Controller SM981/PM981/PM983 (prog-if 02 [NVM Express])\n"
            "     LnkCap: Port #0, Speed , Width , ASPM not supported\n"
            "     LnkSta: Speed , Width , TrErr- Train- SlotClk+ DLActive- "
            "BWMgmt- ABWMgmt-"
        )
        out = self.pci_utils.compare_lspci_lnksta_lnkcap(lspci_out)
        lspci_lnksta_lnkcap_output = (
            "'cap_speed' None compare to 'sta_speed' None: Failed"
        )
        self.assertIn(lspci_lnksta_lnkcap_output, out)

    def test_get_lnksta_lnkcap(self):
        """unit test for get_lnksta_lnkcap"""
        lspci_out = self.pci_utils.get_lspci_output(
            self.mock_host,
            options="-vvv",
            exclude=["DevSta", "Status"],
        )
        nvme_output = [
            {
                "dev_line": (
                    r"3b:00.0 Non-Volatile memory controller: Unknown Vendor "
                    r"NVMe SSD Controller SM981/PM981/PM983 (prog-if 02 "
                    r"[NVM Express])"
                ),
                "cap_speed": "8GT",
                "cap_width": "x4",
                "sta_speed": "8GT",
                "sta_width": "x4",
            },
            {
                "dev_line": (
                    r"3c:00.0 Non-Volatile memory controller: Unknown Vendor "
                    r"NVMe SSD Controller SM981/PM981/PM983 (prog-if 02 "
                    r"[NVM Express])"
                ),
                "cap_speed": "8GT",
                "cap_width": "x4",
                "sta_speed": "8GT",
                "sta_width": "x4",
            },
            {
                "dev_line": (
                    r"3d:00.0 Non-Volatile memory controller: Unknown Vendor "
                    r"NVMe SSD Controller SM981/PM981/PM983 (prog-if 02 "
                    r"[NVM Express])"
                ),
                "cap_speed": "8GT",
                "cap_width": "x4",
                "sta_speed": "8GT",
                "sta_width": "x4",
            },
        ]
        ethernet_output = [
            {
                "dev_line": (
                    r"5e:00.0 Ethernet controller: Unknown Vendor Technologies MT27710 "
                    r"Family"
                ),
                "cap_speed": "8GT",
                "cap_width": "x8",
                "sta_speed": "8GT",
                "sta_width": "x8",
            }
        ]
        out = self.pci_utils.get_lnksta_lnkcap(lspci_out, "nvm")
        self.assertListEqual(out, nvme_output)
        out = self.pci_utils.get_lnksta_lnkcap(lspci_out, "ethernet")
        self.assertListEqual(out, ethernet_output)

        # Validate whitespace line
        mock_lspci_out = " "
        out = self.pci_utils.get_lnksta_lnkcap(mock_lspci_out, "nvm")
        self.assertListEqual(out, [])

    def test_get_lnksta_lnkcap_port(self):
        """unit test for get_lnksta_lnkcap_port"""
        mock_lnksta_lnkcap_dict = {
            "dev": "01:00.0 Non-Volatile memory controller: Unknown Vendor "
            "NVMe SSD [NVM Express])",
            "cap_speed": "8GT",
            "cap_width": "x4",
            "secondary_port": "01:00.0",
            "sta_speed": "8GT",
            "sta_width": "x4",
        }
        cmd = "lspci -vvs 00:1d.0"
        mock_result = (
            "01:00.0 Non-Volatile memory controller: Unknown Vendor NVMe SSD "
            "[NVM Express])\n"
            "     Bus: primary=00, secondary=01, subordinate=01, sec-latency=0"
            "     LnkCap: Port #0, Speed 8GT/s, Width x4, ASPM not supported\n"
            "     LnkSta: Speed 8GT/s, Width x4, TrErr- Train- SlotClk+ DLActive- "
            "BWMgmt- ABWMgmt-"
        )
        self.mock_host.update_cmd_map(cmd, mock_result)
        out = self.pci_utils.get_lnksta_lnkcap_port(self.mock_host, "00:1d.0", "nvm")
        self.assertDictEqual(out, mock_lnksta_lnkcap_dict)

    def test_filter_data(self):
        """unit test for filter_data"""
        lspci_out = self.pci_utils.get_lspci_output(self.mock_host, options="-v")
        filters = [
            {
                "device_name": ".*",
                "filter": [
                    "MAbort\\S+",
                    "NonFatalErr\\S+",
                    "PresDet",
                    "Non-Fatal\\S*",
                    "Current De-emphasis Level:\\s\\S+",
                    "Address:\\s+\\S*",
                    "M3KTI.*",
                    "IRQ\\s+\\S*",
                    "BWMgmt\\S*",
                    "CEMsk:.*",
                    "CESta:.*",
                    "DevCtl:.*",
                    "AERCap:.*",
                    "UESta:.*",
                    "DLP- SDES.*",
                ],
            },
            {
                "device_name": "OSS USB 3.0 xHCI Controller",
                "filter": ["Address.*", "Interrupt:.*"],
            },
            {
                "device_name": "PMC-Sierra Inc",
                "filter": [
                    "LnkSta2:*",
                    "LinkEqualization\\S+",
                    "UEMsk:\\s+",
                    "DpcCtl:\\s+Trigger:\\d+",
                ],
            },
            {
                "device_name": "Processing accelerators",
                "filter": [
                    "LnkSta2:*",
                    "UEMsk:\\s+",
                    "Control: I/O.*",
                    "Ctrl:\\s+Enable.*",
                ],
            },
        ]
        # Validate the filters as list instance
        out = self.pci_utils.filter_data(output=lspci_out, filters=filters)
        self.assertIsInstance(out, str)

        # Validate the filters as str instance
        filters = [{"device_name": "Processing accelerators", "filter": "LnkSta2:*"}]
        out = self.pci_utils.filter_data(output=lspci_out, filters=filters)
        self.assertIsInstance(out, str)

        # To validate the empty string
        out = self.pci_utils.filter_data(output=lspci_out)
        self.assertFalse(out)

    @mock.patch.object(AutovalLog, "log_cmdlog")
    def test_get_device_details(self, mock_log_cmdlog):
        """unit test for get_device_details"""
        lspci_out = self.pci_utils.get_lspci_output(self.mock_host, options="-v")
        # Calling with output parameter
        mock_log_cmdlog.return_value = ""
        out = self.pci_utils.get_device_details(output=lspci_out)
        self.assertIsInstance(out, dict)

        # Calling without output parameter
        mock_output = self.mock_host._read_file("lspci_vvv_3")
        AutovalUtils.run_get_output = mock.Mock(return_value=mock_output)
        out = self.pci_utils.get_device_details()
        self.assertIsInstance(out, dict)

    def test_get_pci_for_devices(self):
        """unit test for get_pci_for_devices"""
        cmd = "lspci -vvv"
        mock_result = (
            "00:00.0 Host bridge: Unknown Vendor DMI3 Registers (rev 04)\n"
            "	Subsystem: Unknown Vendor Device 0000"
            "01:00.0 Host bridge: Unknown Vendor DMI3 Registers (rev 04)\n"
            "   Subsystem: Unknown Vendor Device 0000"
        )
        self.mock_host.update_cmd_map(cmd, mock_result)
        out = self.pci_utils.get_pci_for_devices(self.mock_host, ["00:00.0"])
        self.assertIn(r"00:00.0 Host bridge:", out)

    def test_get_nvme_drive_pcie_address(self):
        """unit test for get_nvme_drive_pcie_address"""
        output = self.pci_utils.get_nvme_drive_pcie_address(self.mock_host, "nvme0n1")
        self.assertEqual(output, "01:00.0")
        self.assertRaises(
            TestError,
            self.pci_utils.get_nvme_drive_pcie_address,
            self.mock_host,
            "nvme3n1",
        )

    def test_get_nvme_drive_pcie_completion_timeout_value(self):
        """unit test for get_nvme_drive_pcie_completion_timeout_value"""
        out = self.pci_utils.get_nvme_drive_pcie_completion_timeout_value(
            self.mock_host, "nvme0n1"
        )
        self.assertEqual(out, "0410")
        out = self.pci_utils.get_nvme_drive_pcie_completion_timeout_value(
            self.mock_host, "nvme1n1"
        )
        self.assertFalse(out)

    def test_set_nvme_drive_pcie_completion_timeout(self):
        self.pci_utils.set_nvme_drive_pcie_completion_timeout(
            self.mock_host, "nvme0n1", "0400"
        )

    def test_get_pcie_devices(self):
        """unit test for get_pcie_devices"""
        self.assertTrue(
            self.pci_utils.get_pcie_devices(
                self.mock_host, ["0000:00:00.0", "0000:00:04.1"]
            )
        )
        # Validate empty list
        self.assertFalse(
            self.pci_utils.get_pcie_devices(
                self.mock_host, ["0000:00:00.4", "0000:00:04.2"]
            )
        )

    def test_get_pcie_register_type(self):
        """unit test for get_pcie_register_type"""
        self.cmd_output_dict = {
            "cat /sys/bus/pci/devices/0000:00:00.0/device": 0x2020,
            "cat /sys/bus/pci/devices/0000:00:00.0/vendor": 0x8086,
            "cat /sys/bus/pci/devices/0000:00:00.0/class": 0x060000,
        }
        # Validate vendor
        out = self.pci_utils.get_pcie_register_type(
            self.mock_host, "0000:00:00.0", "vendor"
        )
        self.assertEqual(out, "0x8086")
        # Validate device
        out = self.pci_utils.get_pcie_register_type(
            self.mock_host, "0000:00:00.0", "device"
        )
        self.assertEqual(out, "0x2020")
        # Validate class
        out = self.pci_utils.get_pcie_register_type(
            self.mock_host, "0000:00:00.0", "class"
        )
        self.assertEqual(out, "0x060000")

    def test_get_pcie_link_speed(self):
        """unit test for get_pcie_link_speed"""
        out = self.pci_utils.get_pcie_link_speed(
            self.mock_host, "0000:00:00.0", "max_link_speed"
        )
        self.assertEqual(out, "8 GT/s")

    def test_get_pcie_device_id(self):
        """unit test for get_pcie_device_id"""
        out = self.pci_utils.get_pcie_device_id(self.mock_host, "0000:00:00.0")
        self.assertIsInstance(out, str)
        self.assertEqual(out, "0x2020")

    def test_get_pcie_vendor_id(self):
        """unit test for get_pcie_vendor_id"""
        out = self.pci_utils.get_pcie_vendor_id(self.mock_host, "0000:00:00.0")
        self.assertIsInstance(out, str)
        self.assertEqual(out, "0x8086")

    def test_get_pcie_class(self):
        """unit test for get_pcie_class"""
        out = self.pci_utils.get_pcie_class(self.mock_host, "0000:00:00.0")
        self.assertIsInstance(out, str)
        self.assertEqual(out, "0x060000")

    def test_get_pcie_subsystem_vendor(self):
        """unit test for get_pcie_subsystem_vendor"""
        out = self.pci_utils.get_pcie_subsystem_vendor(self.mock_host, "0000:00:00.0")
        self.assertIsInstance(out, str)
        self.assertEqual(out, "0x8086")

    def test_get_pcie_subsystem_device(self):
        """unit test for get_pcie_subsystem_device"""
        out = self.pci_utils.get_pcie_subsystem_device(self.mock_host, "0000:00:00.0")
        self.assertIsInstance(out, str)

    def test_get_pcie_link_width(self):
        """unit test for get_pcie_link_width"""
        out = self.pci_utils.get_pcie_link_width(
            self.mock_host, "0000:00:00.0", "max_link_width"
        )
        self.assertIsInstance(out, int)
        self.assertEqual(out, 4)
        out = self.pci_utils.get_pcie_link_width(
            self.mock_host, "0000:00:00.0", "current"
        )
        self.assertEqual(out, 0)

    def test_get_device_pci_registers(self):
        """unit test for get_device_pci_registers"""
        mock_pci_regs = {
            "device_id": "0x2020",
            "vendor_id": "0x8086",
            "class_id": "0x060000",
            "subsystem_vendor_id": "0x8086",
            "subsystem_device_id": "0x0000",
            "current_link_speed": "Unknown speed",
            "max_link_speed": "8 GT/s",
            "current_link_width": 0,
            "max_link_width": 4,
        }
        self.assertDictEqual(
            self.pci_utils.get_device_pci_registers(self.mock_host, "0000:00:00.0"),
            mock_pci_regs,
        )

    def test_expand_pci_addr(self):
        """unit test for expand_pci_addr"""
        out = self.pci_utils.expand_pci_addr("0000:00:00.0")
        self.assertEqual(out, "0000:00:00.0")
        out = self.pci_utils.expand_pci_addr("02:00.0")
        self.assertEqual(out, "0000:02:00.0")
        self.assertFalse(self.pci_utils.expand_pci_addr("02:00"))
        self.assertFalse(self.pci_utils.expand_pci_addr("02.0"))

    def test_pci_drive_slots(self):
        """unit test for pci_drive_slots"""
        cmd = "ls -F /sys/bus/pci/slots"
        mock_out = "15/  16/  17/  18/  2/  3/"
        expected_output = [15, 16, 17, 18, 2, 3]
        self.mock_host.update_cmd_map(cmd, mock_out)
        self.assertEqual(
            self.pci_utils.get_pci_drive_slots(self.mock_host), expected_output
        )

    @mock.patch.object(PciUtils, "get_pci_drive_slots", return_value=[17])
    def test_get_slot_address(self, mock_drive_slot):
        """unit test for get_slot_address"""
        cmd = "cat /sys/bus/pci/slots/17/address"
        mock_output = "0000:b4:00"
        self.mock_host.update_cmd_map(cmd, mock_output)
        expected_output = {17: "0000:b4:00"}
        self.assertEqual(
            self.pci_utils.get_slot_address(self.mock_host), expected_output
        )

    def test_get_slot_power(self):
        """unit test for get_slot_power"""
        cmd = "cat /sys/bus/pci/slots/17/power"
        mock_out = 1
        expected_output = 1
        self.mock_host.update_cmd_map(cmd, mock_out)
        self.assertEqual(
            self.pci_utils.get_slot_power(self.mock_host, 17), expected_output
        )

    def test_check_device_pcie_errors(self):
        self.assertIsNone(
            self.pci_utils.check_device_pcie_errors(self.mock_host, ["0000:00:00.0"])
        )
