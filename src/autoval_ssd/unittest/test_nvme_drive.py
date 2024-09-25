# pyre-unsafe
import copy
import json
import unittest
import unittest.mock as mock
from unittest.mock import call, patch

from autoval.lib.transport.ssh import SSHConn
from autoval.lib.utils.autoval_exceptions import TestError, TestStepError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_output import AutovalOutput
from autoval.lib.utils.file_actions import FileActions

from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.pci_utils import PciUtils
from autoval_ssd.lib.utils.storage.nvme.nvme_drive import NVMeDrive, OwnershipStatus
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.unittest.mock.lib.mock_host import MockHost

MOCK_BLOCK_NAME = "nvme1"
MOCK_NVME_LIST = [
    {
        "DevicePath": f"/dev/{MOCK_BLOCK_NAME}",
        "Firmware": "80003E00",
        "Index": 0,
        "ModelNumber": "HFS256GD9TNG-62A0A",
        "ProductName": "Non-Volatile memory controller: Unknown Device 0x1527",
        "SerialNumber": "MN95N637910306E2I",
        "UsedBytes": 3767201792,
        "MaximumLBA": 62514774,
        "PhysicalSize": 256060514304,
        "SectorSize": 4096,
    }
]
CMD_MAP = [
    {"cmd": "nvme id-ctrl /dev/nvme1 -o json", "file": "id_ctrl"},
    {"cmd": "nvme id-ctrl -H /dev/nvme1", "file": "id_ctrlH"},
    {"cmd": "nvme id-ctrl /dev/nvme1 -H | grep -v fguid", "file": "id_ctrlH"},
    {"cmd": "cat /sys/block/nvme1/queue/rotational", "result": "0"},
    {
        "cmd": "nvme get-log /dev/nvme1n1 --log-id=0xC0h --log-len=299",
        "file": "power_state_change_counter",
    },
    {
        "cmd": "nvme ocp smart-add-log /dev/nvme1 -o json",
        "file": "nvme_ocp_command.json",
    },
    {
        "cmd": "nvme smart-log /dev/nvme1 -o json",
        "result": """{
                    "critical_warning" : 0,
                    "temperature" : 307,
                    "avail_spare" : 100
                }""",
    },
]


# Decorator for common mocks.
def apply_mock(func):
    def mocking(*args, **kwargs):
        mock_host = MockHost(cmd_map=CMD_MAP)
        with mock.patch.object(
            SSHConn, "run", side_effect=mock_host.run
        ), mock.patch.object(NVMeUtils, "get_nvme_list", return_value=MOCK_NVME_LIST):
            func(*args, **kwargs)

    return mocking


class MockVendor(NVMeDrive):
    """Mock inheritence of MockNvmeDrive"""

    def __init__(self, host, block_name, config=None):
        super(MockVendor, self).__init__(host, block_name, config)

    def get_nand_write_param(self):
        """Mocking the nand write as vendor drive"""
        mock_vendor_dict = {
            "field": "Physical media units written_lo",
            "formula": "%s/%s" % ("NAND_WRITE", pow(1024, 3)),
        }
        return mock_vendor_dict


class NvmeDriveUnitTest(unittest.TestCase):
    """NvmeDrive Class unit test"""

    mock_block_name = MOCK_BLOCK_NAME
    mock_smart_log = {
        "vs-smart-add-log": {
            "PhysicallyWrittenBytes": "12279729139712",
            "Physically Read Bytes": "5221476478976",
            "Bad NAND Block Count (Raw Value)": "0",
            "Bad NAND Block Count (Normalized Value)": "100",
            "Uncorrectable Read Error Count": "0",
            "Soft ECC Error Count": "0",
            "SSD End to end Correction Count (Detected Errors)": "0",
            "SSD End to end Correction Count (Corrected Errors)": "0",
            "System Data Percentage Used": 0,
            "User Data Erase Count (Min)": 2,
            "User Data Erase Count (Max)": 8,
            "Refresh Count": "0",
            "Program Fail Count (Raw Value)": "0",
            "Program Fail Count (Normalized Value)": "100",
            "User Data Erase Fail Count (Raw Value)": "0",
            "User Data Erase Fail Count (Normalized Value)": "100",
            "System Area Erase Fail Count (Raw Value)": "0",
            "System Area Erase Fail Count (Normalized value)": "100",
            "Thermal Throttling Status": "0",
            "Thermal Throttling Count": "0",
            "PHY Error Count": "0",
            "Bad DLLP Count": "0",
            "Bad TLP Count": "0",
            "Reserved": "0",
            "Incomplete Shutdowns": "0",
            "% Free Blocks": "99",
            "PCIe Correctable Error Count (RTS)": "0",
            "PCIe Correctable Error Count (RRS)": "0",
            "XOR Recovery Count": "0",
        },
        "smart-log": {
            "critical_warning": 0,
            "temperature": 307,
            "avail_spare": 100,
            "spare_thresh": 10,
            "percent_used": 0,
            "data_units_read": 13898198,
            "data_units_written": 21210849,
            "host_read_commands": 459217404,
            "host_write_commands": 211574086,
            "controller_busy_time": 310,
            "power_cycles": 36,
            "power_on_hours": 842,
            "unsafe_shutdowns": 31,
            "media_errors": 0,
            "num_err_log_entries": 35,
            "warning_temp_time": 0,
            "critical_comp_time": 0,
            "temperature_sensor_1": 307,
            "temperature_sensor_2": 314,
            "temperature_sensor_3": 321,
            "thm_temp1_trans_count": 0,
            "thm_temp2_trans_count": 0,
            "thm_temp1_total_time": 0,
            "thm_temp2_total_time": 0,
        },
    }
    mock_ocp_output = {
        "ocp-smart-add-log": {
            "Physical media units written_hi": 0.0,
            "Physical media units written_lo": 39074645999616.0,
            "Physical media units read_hi": 0.0,
            "Physical media units read_lo": 36265469677568.0,
            "Bad user nand blocks - Raw": 0.0,
            "Bad user nand blocks - Normalized": 100.0,
            "Bad system nand blocks - Raw": 0.0,
            "Bad system nand blocks - Normalized": 100.0,
            "XOR recovery count": 0.0,
            "Uncorrectable read error count": 0.0,
            "Soft ecc error count": 1117.0,
            "End to end corrected errors": 0.0,
            "End to end detected errors": 0.0,
            "System data percent used": 0.0,
            "Refresh counts": 520628.0,
            "Max User data erase counts": 45.0,
            "Min User data erase counts": 16.0,
            "Number of Thermal throttling events": 0.0,
            "Current throttling status": 0.0,
            "PCIe correctable error count": 0.0,
            "Incomplete shutdowns": 0.0,
            "Percent free blocks": 1.0,
            "Capacitor health": 100.0,
            "Unaligned I/O": 0.0,
            "Security Version Number": 65537.0,
            "NUSE - Namespace utilization": 0.0,
            "PLP start count": 287.0,
            "Endurance estimate": 20100000.0,
            "Log page version": 2.0,
            "Log page GUID": 2.3372128010479164e38,
        },
        "smart-log": {
            "critical_warning": 0,
            "temperature": 307,
            "data_units_read": 13898198,
            "data_units_written": 21210849,
        },
    }

    @apply_mock
    def setUp(self):
        """initializing the required variables with the required data"""
        self.log = ""
        self.host = MockHost(cmd_map=CMD_MAP)
        self.nvme = NVMeDrive(self.host, self.mock_block_name)

    def update_cmd_map(self, cmd: str, mock_output: str, _file: bool = False):
        """This method will update the command map with the cmd values
        in case if the command is already present it would update the file
        or result value of the command."""
        for each_cmd_map in CMD_MAP:
            if each_cmd_map["cmd"] == cmd:
                if _file:
                    each_cmd_map["file"] = mock_output
                else:
                    each_cmd_map["result"] = mock_output
                return
        cmd_map_dict = {"cmd": cmd}
        if _file:
            cmd_map_dict["file"] = mock_output
        else:
            cmd_map_dict["result"] = mock_output
        CMD_MAP.append(cmd_map_dict)

    @apply_mock
    def test_get_arbitration_mechanism_status(self):
        """unit test for get_arbitration_mechanism_status"""
        cmd = f"nvme show-regs /dev/{self.mock_block_name} -H"
        mock_output = "Pass"
        self.update_cmd_map(cmd, mock_output)
        out = self.nvme.get_arbitration_mechanism_status()
        self.assertEqual(out, mock_output)

    @apply_mock
    def test_power_state_change_count(self):
        """unit test for get_power_state_change_counter"""
        # cmd = "nvme get-log /dev/nvme1n1 --log-id=0xC0h --log-len=299"
        cmd = f"nvme get-log /dev/{self.mock_block_name} --log-id=0xC0h --log-len=299"
        moc_file = "power_state_change_counter"
        self.update_cmd_map(cmd, moc_file, True)
        out = self.nvme.get_power_state_change_counter()
        mock_output = 9876543
        self.assertEqual(out, mock_output)

    def test_get_nvme_id_ctrl(self) -> None:
        """unit test for get_nvme_id_ctrl"""
        cmd = f"nvme id-ctrl /dev/{self.mock_block_name} | grep -v fguid"
        mock_output = "Pass"
        self.update_cmd_map(cmd, mock_output)
        out = self.nvme.get_nvme_id_ctrl()
        self.assertEqual(out, mock_output)

    @patch.object(NVMeDrive, "get_nvme_id_ctrl")
    def test_get_nvme_id_ctrl_apsta(self, get_nvme_id_ctrl) -> None:
        """Unit test for get_nvme_id_ctrl_apsta"""
        get_nvme_id_ctrl.return_value = "apsta     : 0"
        out = self.nvme.get_nvme_id_ctrl_apsta()
        self.assertEqual(out, get_nvme_id_ctrl.return_value)

    def test_get_ocp_smart_log(self):
        self.host.update_cmd_map(
            cmd="nvme ocp smart-add-log /dev/nvme1 -o json",
            mock_output="nvme_ocp_command.json",
            is_file=True,
        )
        out = self.nvme.get_ocp_smart_log()["ocp-smart-add-log"]
        expected = self.mock_ocp_output["ocp-smart-add-log"]
        self.assertEqual(out, expected)

    def test_get_nvme_id_ctrl_fw_revision(self):
        """unit test for get_nvme_id_ctrl_fw_revision"""
        cmd = f"nvme id-ctrl /dev/{self.mock_block_name} | grep fr"
        out = """fr        : P1FB006
                    frmw      : 0x2"""
        self.update_cmd_map(cmd, out)
        out = self.nvme.get_nvme_id_ctrl_fw_revision()
        mock_output = "P1FB006"
        self.assertEqual(out, mock_output)

    def test_get_nvme_id_ctrl_mtfa(self):
        """unit test for get_nvme_id_ctrl_mtfa"""
        cmd = f"nvme id-ctrl /dev/{self.mock_block_name} | grep mtfa"
        out = "mtfa      : 250"
        self.update_cmd_map(cmd, out)
        out = self.nvme.get_nvme_id_ctrl_mtfa()
        mock_output = 250
        self.assertEqual(out, mock_output)

    def test_get_nvme_controllers(self):
        """unit test for get_nvme_controllers"""
        cmd = "lspci | grep 'Non-Volatile memory controller:'"
        mock_output = "Pass"
        self.update_cmd_map(cmd, mock_output)
        out = self.nvme.get_nvme_controllers()
        self.assertEqual(out, mock_output)

    @apply_mock
    def test_get_fw_log(self):
        """unit test for get_fw_log"""
        cmd = f"nvme fw-log /dev/{self.mock_block_name} -o json"
        mock_output = "Pass"
        self.update_cmd_map(cmd, mock_output)
        out = self.nvme.get_fw_log()
        self.assertEqual(out, mock_output)

    @apply_mock
    def test_get_crypto_erase_support_status(self) -> None:
        """unit test for get_crypto_erase_support_status"""
        cmd = "nvme id-ctrl /dev/nvme1 -H | grep -v fguid"
        mock_output_valid = "Mock output with Crypto Erase Supported for the drive"
        mock_output_invalid = "Mock output with Secure Erase Supported for the drive"
        self.update_cmd_map(cmd, mock_output_valid)
        # Asserting if the return is true for Crypto Erase Support
        out = self.nvme.get_crypto_erase_support_status()
        self.assertTrue(out)
        # Asserting if the return is False in case no Crypto Erase Support
        self.update_cmd_map(cmd, mock_output_invalid)
        out = self.nvme.get_crypto_erase_support_status()
        self.assertFalse(out)

    @apply_mock
    def test_get_error_log(self):
        """unit test for get_error_log"""
        cmd = f"nvme error-log /dev/{self.mock_block_name} -o json"
        mock_output = "Pass"
        self.update_cmd_map(cmd, mock_output)
        out = self.nvme.get_error_log()
        self.assertEqual(out, mock_output)

    @apply_mock
    def test_get_id_ns(self):
        """unit test for get_id_ns"""
        cmd = f"nvme id-ns /dev/{self.mock_block_name} -o json"
        mock_output = "Pass"
        self.update_cmd_map(cmd, mock_output)
        out = self.nvme.get_id_ns()
        self.assertEqual(out, mock_output)

    @apply_mock
    def test_get_bs_size(self):
        """unit test for get_bs_size"""
        cmd = f"nvme id-ns /dev/{self.mock_block_name} -H"
        mock_output_valid = (
            "LBA Format  0 : Metadata Size: 0   bytes - Data Size"
            ": 512 bytes - Relative Performance: 0 Best (in use)\n"
            "LBA Format  1 : Metadata Size: 0   bytes - Data Size: "
            "4096 bytes - Relative Performance: 0 Best"
        )
        mock_output_invalid = (
            "LBA Format  1 : Metadata Size: 0   bytes - "
            "Data Size: 4096 bytes - Relative Performance: 0 Best"
        )
        bytes_used = 512
        self.update_cmd_map(cmd, mock_output_valid)
        # Assert if the expected bytes in use of drive is returned
        out = self.nvme.get_bs_size()
        self.assertEqual(out, bytes_used)
        # Assert if the TestError is raised in case output does not have bytes in use
        self.update_cmd_map(cmd, mock_output_invalid)
        self.assertRaises(TestError, self.nvme.get_bs_size)

    @apply_mock
    def test_get_bs_size_list(self):
        """unit test for get_bs_size_list"""
        cmd = f"nvme id-ns /dev/{self.mock_block_name} -H"
        mock_output_valid = (
            "LBA Format  0 : Metadata Size: 0   bytes - Data Size: 512 bytes - "
            "Relative Performance: 0 Best (in use)\n"
            "LBA Format  1 : Metadata Size: 0   "
            "bytes - Data Size: 4096 bytes - Relative Performance: 0 Best"
        )
        bytes_list = [512, 4096]
        self.update_cmd_map(cmd, mock_output_valid)
        # Assert if all the bytes in the output are returned as list
        out = self.nvme.get_bs_size_list()
        self.assertListEqual(out, bytes_list)
        # Assert if the TestError is raised in case the bytes are not
        # part of output
        mock_output_invalid1 = "LBA Format  0 : Metadata Size: 0  "
        self.update_cmd_map(cmd, mock_output_invalid1)
        self.assertRaises(TestError, self.nvme.get_bs_size_list)
        # Assert if the TestError is raised in case of empty output
        mock_output_invalid2 = ""
        self.update_cmd_map(cmd, mock_output_invalid2)
        self.assertRaises(TestError, self.nvme.get_bs_size_list)

    @apply_mock
    def test_get_feature(self):
        """unit test for get_feature"""
        for feature in self.nvme.FEATURE_IDS:
            cmd = f"nvme get-feature /dev/{self.mock_block_name} -f {feature} -H"
            mock_output = (
                f"get-feature:{feature} (Arbitration), Current value:0x3030302\n"
                "High Priority Weight   (HPW): 4\n"
                "Medium Priority Weight (MPW): 4\n"
                "Low Priority Weight    (LPW): 4\n"
                "Arbitration Burst       (AB): 4"
            )
            self.update_cmd_map(cmd, mock_output)
        out = self.nvme.get_feature()
        # Asserting if the return type is list
        self.assertIsInstance(out, list)
        # Asserting if the list contains the all Features output
        # by validating the length
        self.assertEqual(len(out), len(self.nvme.FEATURE_IDS))
        # Asserting by passing Feature ID's as input
        mock_feature_ids = ["oxaseer"]
        cmd = f"nvme get-feature /dev/{self.mock_block_name} -f 'oxaseer' -H"
        mock_output = (
            "get-feature:oxaseer (Arbitration), Current value:0x3030302\n"
            "High Priority Weight   (HPW): 4\n"
            "Medium Priority Weight (MPW): 4\n"
            "Low Priority Weight    (LPW): 4\n"
            "Arbitration Burst       (AB): 4"
        )
        self.update_cmd_map(cmd, mock_output)
        out = self.nvme.get_feature(mock_feature_ids)
        self.assertEqual(len(out), len(mock_feature_ids))

    def get_logger(self, out: str, ocp_log=False):
        """method will override the Autoval.log_info"""
        self.log += out

    @apply_mock
    @mock.patch.object(AutovalLog, "log_info")
    def test_get_write_amplification(self, mock_log):
        """unit test for get_write_amplification and calculate_waf"""
        mock_log.side_effect = self.get_logger
        smart_before = copy.deepcopy(self.mock_ocp_output)
        smart_after = copy.deepcopy(self.mock_ocp_output)
        # Asserting if the lifetime Write amp is calculated if smart after
        # has Physical media units written_lo and data_units_written
        # Re-initialize the log output to empty
        nvme = MockVendor(self.host, self.mock_block_name)
        self.log = ""
        nvme.get_write_amplification(smart_before, smart_after)
        self.assertRegex(
            self.log,
            r"Lifetime WAF for drive nvme\d+ is \d+\.\d+",
        )
        # Test hex values
        formula = nvme.get_nand_write_param()
        smart_before["ocp-smart-add-log"][formula["field"]] = 130048
        smart_after["ocp-smart-add-log"][formula["field"]] = 130560
        self.log = ""
        nvme.get_write_amplification(smart_before, smart_after)
        self.assertRegex(
            self.log,
            r"Lifetime WAF for drive nvme\d+ is \d+\.\d+",
        )

    @apply_mock
    def test_calculate_waf(self):
        """unit test for caluculate_waf"""
        nvme = MockVendor(self.host, self.mock_block_name)
        formula = nvme.get_nand_write_param()
        mock_hwrite = 400.0
        mock_nwrite = 5000.0
        out = nvme.calculate_waf(mock_hwrite, mock_nwrite, formula)
        self.assertTrue(out[0])
        mock_hwrite = 0
        # validate the test in case of ZeroDivisionError
        out = nvme.calculate_waf(mock_hwrite, mock_nwrite, formula)
        self.assertFalse(out[0])
        self.assertEqual(ZeroDivisionError, out[1].__class__)

    def test_convert_nand_write(self):
        """unit test for convert_nand_write"""
        nand_string = "12,345.1234"
        nand_int = 1234
        nand_float = 12.34
        nand_invalid = "123.abc"
        # Asserting if the string nand_write is converted to float
        out = self.nvme.convert_nand_write(nand_string)
        self.assertIsInstance(out, float)
        self.assertNotEqual(out, nand_string)
        # Asserting if string is not passed it returns the input passed
        out = self.nvme.convert_nand_write(nand_int)
        self.assertNotIsInstance(out, float)
        self.assertEqual(out, nand_int)
        out = self.nvme.convert_nand_write(nand_float)
        self.assertEqual(out, nand_float)
        # Asserting if the error is raised
        self.assertRaises(TestError, self.nvme.convert_nand_write, nand_invalid)

    def test_get_drive_name(self):
        """unit test for get_drive_name"""
        # Assert if the
        out = self.nvme.get_drive_name()
        self.assertEqual(out, self.mock_block_name)

    @apply_mock
    @mock.patch.object(json, "dumps")
    @mock.patch.object(AutovalOutput, "add_measurement")
    @mock.patch.object(FileActions, "get_local_path")
    @mock.patch.object(AutovalLog, "log_info")
    @mock.patch.object(NVMeDrive, "validate_firmware_update")
    @mock.patch.object(DiskUtils, "get_boot_drive")
    @mock.patch.object(NVMeDrive, "is_sed_drive")
    def test_update_firmware(
        self,
        mock_sed,
        mock_boot,
        mock_validate,
        mock_log,
        mock_local_path,
        mock_add_measurement,
        mock_json_dumps,
    ):
        """unit test for update_firmware"""
        mock_log.side_effect = self.get_logger
        mock_validate.return_value = "pass"
        mock_boot.return_value = "mock1"
        mock_sed.return_value = True
        fw_version = "aaaa.bb"
        fw_bin_loc = "bin/mock loc"
        mock_local_path.return_value = fw_bin_loc
        cmd = f"nvme fw-activate {self.mock_block_name} --slot=0 --action=1"
        mock_output = "Success committing firmware action:1 slot:0"
        self.update_cmd_map(cmd, mock_output)
        cmd = f"nvme fw-download {self.mock_block_name} -f {fw_bin_loc}"
        mock_output = "Firmware download success"
        self.update_cmd_map(cmd, mock_output)
        # Executing the method passing slots as none fWversion which is not equal
        # to the fW version in the mocked json file
        self.nvme.update_firmware(fw_version, fw_bin_loc)
        # Asserting if the fw_activation history dependent methods are called
        # for an SED drive
        # Executing the method passing more than one slots fWversion which
        # is not equal to the fW version in the mocked json file
        mock_fw_slots_data = [1, 2, 3]
        mock_sed.reset_mock(return_value=True)
        mock_boot.reset_mock(return_value=True)
        self.nvme.update_firmware(fw_version, fw_bin_loc, fw_slots=mock_fw_slots_data)
        # Asserting if the update is skipped if firmware is already in place
        self.log = ""
        mock_sed.reset_mock(return_value=True)
        mock_boot.reset_mock(return_value=True)
        self.nvme.update_firmware("80003E00", fw_bin_loc)
        self.assertIn("Device already updated with latest version", self.log)
        # Asserting if the fw_activation history dependent methods are not called
        # if firmware is already activated and is force update is false
        self.assertFalse(
            all(
                [
                    mock_sed.called,
                    mock_boot.called,
                ]
            )
        )
        # FW update Action 2
        self.log = ""
        mock_sed.reset_mock(return_value=True)
        mock_boot.reset_mock(return_value=True)
        mock_fw_slots_data = [0, 1, 2]
        self.nvme.fw_activate = mock.Mock(return_value=None)
        self.nvme.update_firmware(
            fw_version, fw_bin_loc, fw_slots=mock_fw_slots_data, action=2
        )
        self.assertIn("Firmware update action 2 does not support the update", self.log)
        self.nvme.fw_activate.assert_has_calls(
            calls=[
                call("nvme1", "bin/mock loc", 1, action=0, nvme_admin_io=True),
                call("nvme1", "bin/mock loc", 1, 2, False),
                call("nvme1", "bin/mock loc", 2, action=0, nvme_admin_io=True),
                call("nvme1", "bin/mock loc", 2, 2, False),
            ]
        )

    @apply_mock
    @mock.patch.object(NVMeDrive, "get_smart_log")
    def test_collect_data(self, mock_smart_log):
        """unit test for collect_data"""
        mock_smart_log.return_value = self.mock_smart_log
        collect_output = self.nvme.collect_data()
        self.assertIsInstance(collect_output, dict)
        mock_nvme_list = MOCK_NVME_LIST[0]
        self.assertEqual(collect_output["firmware"], mock_nvme_list.get("Firmware"))
        self.assertEqual(
            collect_output["serial_number"], mock_nvme_list.get("SerialNumber")
        )
        self.assertEqual(collect_output["type"], self.nvme.type.value)
        self.assertEqual(collect_output["interface"], self.nvme.interface.value)
        self.assertEqual(collect_output["model"], mock_nvme_list.get("ModelNumber"))
        self.assertEqual(collect_output["manufacturer"], "GenericNVMe")

    @apply_mock
    def test_get_vs_timestamp(self):
        """unit test for get_vs_timestamp"""
        cmd = f"nvme get-feature /dev/{self.mock_block_name} -f 0xe -H"
        mock_output_invalid = (
            "get-feature:0xe (Timestamp), Current value:00000000\n"
            "0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f\n"
            '0000: b3 fd 31 96 74 01 02 00                          "..1.t..."'
        )
        mock_output_valid = "get-feature:0xe The timestamp is : 1600248189"
        self.update_cmd_map(cmd, mock_output_valid)
        out = self.nvme.get_vs_timestamp()
        self.assertTrue(out)
        self.update_cmd_map(cmd, mock_output_invalid)
        self.assertRaises(NotImplementedError, self.nvme.get_vs_timestamp)

    @apply_mock
    @mock.patch.object(PciUtils, "get_nvme_drive_pcie_address")
    @mock.patch.object(PciUtils, "get_lspci_output")
    @mock.patch.object(NVMeDrive, "get_smart_log")
    def test_drive_health_check(self, mock_smart_log, mock_lspci, mock_drive_pcie):
        """unit test for drive_health_check."""
        mock_lspci.return_value = " Fatal+"
        mock_drive_pcie.return_value = "pass"
        mock_smart_log.return_value = self.mock_smart_log
        self.nvme.drive_health_check()
        mock_smart = copy.deepcopy(self.mock_smart_log)
        # Changing the critical warning value to be >0
        mock_smart["smart-log"]["critical_warning"] = 1
        mock_smart_log.return_value = mock_smart
        self.assertRaises(TestError, self.nvme.drive_health_check)
        # Changing the lscpi output and asserting if the error
        # is raised if Fatal+ pattern is not found
        mock_lspci.return_value = " Fatal-"
        self.assertRaises(TestError, self.nvme.drive_health_check)

    @apply_mock
    @mock.patch.object(AutovalLog, "log_info")
    @mock.patch.object(NVMeDrive, "get_smart_log")
    def test_drive_erase_count(self, mock_smart_log, mock_log):
        """unit test for dirve_erase_count"""
        mock_smart_log.return_value = self.mock_smart_log
        mock_log.side_effect = self.get_logger
        # Valid case
        self.nvme.drive_erase_count()
        # invalid case 1
        # Asserting if the Error is not raised if the delta is > 2000
        self.log = ""
        mock_smart = copy.deepcopy(self.mock_smart_log)
        mock_smart["vs-smart-add-log"]["User Data Erase Count (Max)"] = 3000
        mock_smart_log.return_value = mock_smart
        self.nvme.drive_erase_count()
        self.assertRegex(self.log, r"FAILED.*User-data Erase Count delta")
        # invalid case 2
        # Asserting key error is not raised
        del mock_smart["vs-smart-add-log"]["User Data Erase Count (Max)"]
        self.nvme.drive_erase_count()

    @mock.patch.object(NVMeDrive, "get_firmware_version")
    def test_is_drive_degraded(self, mock_firmware):
        """unit test for is_drive_degraded"""
        # valid case
        mock_firmware.return_value = "80003E00"
        self.nvme.is_drive_degraded()
        # invalid case
        mock_firmware.return_value = "ERRORMOD"
        self.assertRaises(TestError, self.nvme.is_drive_degraded)

    @apply_mock
    @patch.object(NVMeDrive, "get_nvme_id_ctrl")
    def test_get_fw_slots(self, get_nvme_id_ctrl) -> None:
        """unit test for get_fw_slots"""
        get_nvme_id_ctrl.return_value = (
            "[3:1] : 0x3   Number of Firmware Slots"
            "[0:0] : 0x1   Firmware Slot 1 Read-Only"
        )
        # Assert if the read only slot 1 is removed from total 3
        # slots
        out = self.nvme.get_fw_slots()
        validate_out = [0, 2]
        self.assertListEqual(out, validate_out)
        # Assert if No of slots are 0 Test error is raised
        get_nvme_id_ctrl.return_value = "[3:1] : 0x0   Number of Firmware Slots\n"
        self.assertRaises(TestStepError, self.nvme.get_fw_slots)
        # Assert if default slot 0 is picked up if the
        # No of slots is not part of the output
        get_nvme_id_ctrl.return_value = "mock output"
        validate_out = [0]
        out = self.nvme.get_fw_slots()
        self.assertListEqual(out, validate_out)

    @apply_mock
    @patch.object(NVMeDrive, "get_nvme_id_ctrl")
    def test_get_drive_supported_power_modes(self, get_nvme_id_ctrl) -> None:
        get_nvme_id_ctrl.return_value = (
            "ps    4 : mp:0.0050W non-operational enlat:5000 exlat:44000 rrt:4 rrl:4\n"
            "ps    2 : mp:1.90W operational enlat:0 exlat:0 rrt:2 rrl:2\n"
            "ps    3 : mp:0.0800W non-operational enlat:10000 exlat:2500 rrt:3 rrl:3"
        )
        self.assertEqual(self.nvme.get_drive_supported_power_modes(), [2])

    @apply_mock
    def test_get_power_mode(self):
        cmd = f"nvme get-feature /dev/{self.mock_block_name} -f 0x2"
        mock_output_valid = "get-feature:0x2 (Power Management), Current value:0x000001"
        self.update_cmd_map(cmd, mock_output_valid)
        self.assertEqual(self.nvme.get_power_mode(), 1)
        mock_output_invalid = ""
        # TestError when values mismatch.
        self.update_cmd_map(cmd, mock_output_invalid)
        self.assertRaises(TestError, self.nvme.get_power_mode)

    @apply_mock
    def test_set_power_mode(self):
        feature = 1
        cmd = f"nvme set-feature /dev/{self.mock_block_name} -f 0x2 -v {feature}"
        mock_output_valid = "set-feature:01 (Power Management), value:0x000001"
        mock_output_invalid = ""
        self.update_cmd_map(cmd, mock_output_valid)
        self.assertEqual(self.nvme.set_power_mode(feature), 1)
        # TestError when no pattern match.
        self.update_cmd_map(cmd, mock_output_invalid)
        self.assertRaises(TestError, self.nvme.set_power_mode, feature)

    @apply_mock
    @mock.patch.object(NVMeUtils, "run_nvme_security_recv_cmd")
    @mock.patch.object(NVMeDrive, "is_sed_drive")
    @mock.patch.object(MockHost, "run")
    def test_get_tcg_ownership_status(self, mock_host, mock_sed, mock_security):
        """Unittest for get_tcg_ownership_status."""
        mock_sed.return_value = True
        valid_sed = (
            "/dev/nvme1 SED -2- KXG6AZNV512G vendor SAMPLE              AGFE5102"
        )
        sec_recv_notset = b"00 ef bf bd 00 00 00 00 10 00 04 02 10 0c 00 00 00"
        sec_recv_set = sec_recv_notset[:42] + b"01" + sec_recv_notset[44:]
        sec_recv_blocked = sec_recv_notset[:42] + b"02" + sec_recv_notset[44:]
        sec_recv_invalid = sec_recv_notset[:42] + b"03" + sec_recv_notset[44:]
        sec_recv_not_sup = sec_recv_notset[:42] + b"  " + sec_recv_notset[44:]
        # validating the Status SET
        mock_security.return_value = sec_recv_set.decode()
        mock_host.side_effect = [valid_sed, sec_recv_set.decode()]
        out = self.nvme.get_tcg_ownership_status()
        self.assertEqual(repr(OwnershipStatus.SET), repr(out))
        # validating the Status NOT SET
        mock_host.reset_mock(side_effect=True)
        mock_host.side_effect = [valid_sed, sec_recv_notset.decode()]
        mock_security.return_value = sec_recv_notset.decode()
        out = self.nvme.get_tcg_ownership_status()
        self.assertEqual(repr(OwnershipStatus.NOT_SET), repr(out))
        # validating the Status BLOCKED
        mock_host.reset_mock(side_effect=True)
        mock_host.side_effect = [valid_sed, sec_recv_blocked.decode()]
        mock_security.return_value = sec_recv_blocked.decode()
        out = self.nvme.get_tcg_ownership_status()
        self.assertEqual(repr(OwnershipStatus.BLOCKED_AND_NOT_SET), repr(out))
        # validating the Status Not Supported
        mock_host.reset_mock(side_effect=True)
        mock_host.side_effect = [valid_sed, sec_recv_not_sup.decode()]
        mock_security.return_value = sec_recv_not_sup.decode()
        self.assertRaises(TestError, self.nvme.get_tcg_ownership_status)
        # IF Drive is not a SED drive
        mock_sed.reset_mock(return_value=True)
        mock_sed.return_value = False
        mock_security.return_value = sec_recv_invalid.decode()
        self.assertRaises(TestError, self.nvme.get_tcg_ownership_status)

    def test_get_manufacturer(self):
        out = self.nvme.get_manufacturer()
        self.assertEqual(out, "GenericNVMe")

    @mock.patch.object(NVMeDrive, "get_nvme_id_ctrl_fw_revision")
    def test_check_new_firmware_current_firmware(
        self, mock_get_nvme_id_ctrl_fw_revision
    ):
        mock_get_nvme_id_ctrl_fw_revision.return_value = "dummy_ver+1"
        self.nvme.check_new_firmware_current_firmware("dummy_ver")
