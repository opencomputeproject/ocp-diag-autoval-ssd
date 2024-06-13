#!/usr/bin/env python3

# pyre-unsafe
"""library to manage nvme drive"""
import json
import os
import re
import time
from enum import Enum
from time import sleep
from typing import Dict, List

from autoval.lib.host.component.component import COMPONENT

from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import AutovalFileNotFound, TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.decorators import retry
from autoval.lib.utils.file_actions import FileActions
from autoval.lib.utils.generic_utils import GenericUtils
from autoval.lib.utils.result_handler import ResultHandler
from autoval.lib.utils.site_utils import SiteUtils

from autoval_ssd.lib.utils.disk_utils import DiskUtils

from autoval_ssd.lib.utils.pci_utils import PciUtils
from autoval_ssd.lib.utils.storage.drive import Drive, DriveInterface
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils


DEFAULT_VALIDATE_CONFIG = "nvme_validate.json"


def _strip_white_spaces_from_keys(mapping: dict) -> None:
    """
    Recursively remove white spaces from key names of a dictionary in place

    Args:
        mapping: Dictionary to be modified
    """
    for k, v in list(mapping.items()):
        _k = k.strip()
        if _k != k:
            mapping[_k] = v
            del mapping[k]
        if isinstance(v, dict):
            _strip_white_spaces_from_keys(v)


class OwnershipStatus(Enum):
    """Class for drive ownership"""

    SET = "Set"
    NOT_SET = "Not Set"
    BLOCKED_AND_SET = "Blocked and set"
    BLOCKED_AND_NOT_SET = "Blocked and not set"
    BLOCKED = "Blocked"


class NVMeDrive(Drive):
    """Main class for nvme drive"""

    FEATURE_IDS = [
        "0x1",
        "0x2",
        "0x4",
        "0x5",
        "0x7",
        "0x8",
        "0x9",
        "0xA",
        "0xB",
        "0xE",
    ]
    NVMECLI_MANUFACTURER = None

    def __init__(self, host, block_name, config=None) -> None:
        """
        Class for storing data and interacting with NVME drives

        @param Host host: host object
        @param String block_name: drive name in /dev/ path
        @param String config: name of json file that control how drive data is
            validated. NVMe configs are in directory
            NVME validate config are placed in two directories in
                /autoval_ssd/cfg
                    - cfg/nvme_smart
                    - cfg/nvme_smart_fdi
        """
        super().__init__(host, block_name, config=config)
        if config is None:
            config = DEFAULT_VALIDATE_CONFIG
        self.interface = DriveInterface.NVME
        self.serial_number = self.get_serial_number()
        self.model = self._get_model()
        self.manufacturer = self.get_manufacturer()
        self.vid = NVMeUtils.get_vendor_id(host, block_name)
        self.reboot_models = self.get_reboot_models()
        self.subsystem_reset_models = self.get_susbsystem_reset_models()
        self.tooling_owned_models = self.get_tooling_owned_models()
        self.id_ctrl = self.get_id_ctrl()
        self.vendor_entry = None
        self.smart_log_keys = None
        self.validate_config = self.load_config(config)
        self.fw_ns_action_model_map = {}
        self.fw_update_reset_req_models = []
        self.fw_commit_timer_before = None
        self.fw_commit_timer_after = None
        self.command_timer_before = None
        self.admin_command_timer_after = None
        self.io_command_timer_after = None
        self.admin_command = None
        self.io_command = None
        self.fw_ver = None
        self.current_fw_ver = None
        self.fw_ns_slots_models_map = {}
        self.ocp_2_6_drives: List = []
        self.workload_target_drives: List = []
        self.lmparser_ocp_2_0_drives = {}
        self.cfg_dir = ""

    def get_smart_log_keys(self) -> None:
        """
        Method to get list of applicable smart log keys for a drive
        """
        if not self.smart_log_keys:
            smart_log = self.get_smart_log()
            self.smart_log_keys = self._flatten_validate_config_dict(smart_log).keys()

    def load_config(self, config_file: str) -> Dict:
        """
        @param config_file
        @return config for smart validation
        """
        config = {}
        self.cfg_dir = self._get_config_dir(config_file)
        relative_cfg_file_path = os.path.join(self.cfg_dir, config_file)
        relative_cfg_file_path = "/cfg/" + relative_cfg_file_path
        abs_path = self.get_target_path()
        nvme_cfg_path = abs_path + relative_cfg_file_path
        content = FileActions.read_data(nvme_cfg_path, json_file=True)
        config.update(content["nvme"])
        self.get_smart_log_keys()
        config = self._flatten_validate_config_dict(config)
        validate_config = {
            key: config[key] for key in self.smart_log_keys if key in config
        }
        return validate_config

    def get_target_path(self) -> str:
        """
        Returns the path of the target path which is used to get the cfg path in the autoval-oss
        """
        # Get the absolute path of the current file
        target_path = ""
        current_file_path = os.path.abspath(__file__)
        try:
            pattern = r"^(/.*?)/lib"
            match = re.search(pattern, current_file_path)
            if match:
                target_path = match.group(1)
        except Exception:
            raise AutovalFileNotFound("The required file path is not found")
        return target_path

    def _get_config_dir(self, ext_file) -> str:
        """
        JSON files specific for Flash Data Integirty tests are placed in
            nvme_smart_fdi. Other files go in nvme_smart.

        @param string ext_file: NVME json file name
        @return string: directory with config file
        """
        if "fdi" in ext_file:
            return "nvme_smart_fdi"
        return "nvme_smart"

    def _filter_vendor_config(self, config):
        """
        Only get validate instructions for specific for this drive vendor

        @param {} config: dictionary contains validate instructions
            for a specified vendor
        @return {}: filtered dictionary
        """
        return config.get(self.manufacturer, {})

    def _flatten_validate_config_dict(self, config):
        """
        Reduce config with nested comparing instructions, like this
            {
                "smart-log": {"item_1": "==", ...  },
                "<vendor_name>": {
                    "vs-smart-add-log": {"item_a": "<", ...  }
                }
            }
        to
            { "item_1": "==", "item_a": "<", ...  }
        """
        flat = {}
        for each in config:
            if isinstance(config[each], dict):
                flat.update(self._flatten_validate_config_dict(config[each]))
            else:
                flat[each] = config[each]
        return flat

    def get_arbitration_mechanism_status(self):
        """
        Method to get the controller properties
        """
        nvme_drive = "/dev/%s" % self.block_name
        cmd = "nvme show-regs %s -H" % nvme_drive
        out = AutovalUtils.validate_no_exception(
            self.host.run,
            [cmd],
            "Run '%s'" % cmd,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        return out

    def get_nvme_read(self):
        """
        Method to run nvme read command
        """
        nvme_drive = f"/dev/{self.block_name}"
        cmd = f"nvme read {nvme_drive} --data-size=520 --prinfo=1"
        out = AutovalUtils.validate_no_exception(
            self.host.run,
            [cmd],
            f"Run '{cmd}'",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        return out

    def get_nvme_id_ctrl(self, human_readable=None, grep: str = "-v fguid") -> str:
        """
        Method to get nvme_id_ctrl command output
        """
        nvme_drive = f"/dev/{self.block_name}"
        cmd = f"nvme id-ctrl {nvme_drive} "
        if human_readable:
            cmd += "-H "
        if grep:
            cmd += f"| grep {grep}"
        out = AutovalUtils.validate_no_exception(
            self.host.run,
            [cmd],
            f"Run '{cmd}'",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        return out

    def get_nvme_id_ctrl_apsta(self) -> str:
        """
        Method to get apsta from nvme id-ctrl command
        """
        return self.get_nvme_id_ctrl(self, grep="apsta")

    def get_nvme_id_ctrl_fw_revision(self) -> str:
        """
        Method to get firmware revision from id-ctrl command
        """
        out = self.get_nvme_id_ctrl(grep="fr")
        match = re.search(r"fr\s+:\s+(.*)", out)
        if match:
            fw_version = match.group(1)
            return str(fw_version)
        else:
            raise TestError(
                "Fw revision not found for %s" % self.block_name,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.FIRMWARE_ERR,
            )

    def get_nvme_id_ctrl_mtfa(self) -> int:
        """
        Mathod to get the Maximum Time For Activation value from id-ctrl command
        """
        out = self.get_nvme_id_ctrl(grep="mtfa")
        match = re.search(r"mtfa\s+:\s+(.*)", out)
        if match:
            mtfa = match.group(1)
            return int(mtfa)
        else:
            raise TestError(
                f"mtfa not found for {self.block_name}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

    def get_nvme_controllers(self):
        """
        Method to get the nvme controllers
        """
        cmd = "lspci | grep 'Non-Volatile memory controller:'"
        out = AutovalUtils.validate_no_exception(
            self.host.run,
            [cmd],
            "Run '%s'" % cmd,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.PCIE_ERR,
        )
        return out

    def get_fw_log(self):
        """
        Method to retrieve the firmware log for the specified device
        """
        nvme_drive = "/dev/%s" % self.block_name
        cmd = "nvme fw-log %s -o json" % nvme_drive
        out = AutovalUtils.validate_no_exception(
            self.host.run,
            [cmd],
            "Run '%s'" % cmd,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        return out

    def get_crypto_erase_support_status(self) -> bool:
        """
        Method to validate if the drive has crypto erase support
        """
        out = self.get_nvme_id_ctrl(human_readable=True)
        if re.search(r"Crypto Erase Supported", out) is not None:
            return True
        AutovalLog.log_info(
            "%s drive on the DUT does not support crypto erase " % self.block_name
        )
        return False

    def get_error_log(self):
        """
        Method to retrieve specified number of error log entries from a given device
        """
        nvme_drive = "/dev/%s" % self.block_name
        cmd = "nvme error-log %s -o json" % nvme_drive
        out = AutovalUtils.validate_no_exception(
            self.host.run,
            [cmd],
            "Run '%s'" % cmd,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        return out

    def get_id_ns(self):
        """
        Method to log the properties of the specified namespace
        """
        nvme_drive = "/dev/%s" % self.block_name
        cmd = "nvme id-ns %s -o json" % nvme_drive
        out = self.host.run(cmd=cmd)
        return out

    def get_size(self, param) -> int:
        """
        Get Size.

        This method is used to fetch the nuse or nsze value from the
        nvme id-ns /dev/xxxx command

        Parameters
        ----------
        param: str : String value to get the nuse or nsze

        Returns
        -------
        size: nvme id-ns output result: Integer
        """
        out = self.get_id_ns()
        out_json = json.loads(out)
        size = out_json[param]
        return size

    def get_bs_size(self) -> int:
        """
        Get current formatted block size
        """
        nvme_drive = "/dev/%s" % self.block_name
        cmd = "nvme id-ns %s -H" % nvme_drive
        out = AutovalUtils.validate_no_exception(
            self.host.run,
            [cmd],
            "Run '%s'" % cmd,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        match = re.search(r".*\s+(\d+)\s+bytes.*(in\s+use)", out)
        if match:
            current = match.group(1)
            return int(current)
        raise TestError(
            "Block size not found for %s" % self.block_name,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def get_bs_size_list(self):
        """
        Get list of supported block sizes
        """
        nvme_drive = "/dev/%s" % self.block_name
        cmd = "nvme id-ns %s -H" % nvme_drive
        out = AutovalUtils.validate_no_exception(
            self.host.run,
            [cmd],
            "Run '%s'" % cmd,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        if out:
            bs_list = re.findall(r".*\s+(\d+)\s+bytes\s+", out)
            if bs_list:
                bs_list = [int(i) for i in bs_list]
                return bs_list
        raise TestError(
            "List of block size not found for %s" % self.block_name,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def get_feature(self, feature_id=None, queue_id=None):
        """
        Method to get the operating parameters of the specified controller
        identified by the Feature Identifier.
        """
        # according to the nvme specs
        if feature_id is not None:
            feature_ids = feature_id
        else:
            feature_ids = NVMeDrive.FEATURE_IDS
        nvme_drive = "/dev/%s" % self.block_name
        features_info = []
        for _id in feature_ids:
            if queue_id:
                cmd = f"nvme get-feature {nvme_drive} -f {_id} -H {queue_id}"
            else:
                cmd = f"nvme get-feature {nvme_drive} -f {_id} -H"
            out = self.host.run_get_result(cmd=cmd).stdout  # noqa
            feature_info = ",".join([s.strip() for s in out.splitlines()])
            features_info.append(feature_info)
        return features_info

    def get_capacity(self, unit: str = "byte"):
        """Return drive capacity"""
        _byte = NVMeUtils.get_from_nvme_list(self.host, self.block_name, "PhysicalSize")
        return DiskUtils.convert_from_bytes(_byte, unit)

    def get_serial_number(self):
        """Return drive serial_number"""
        return NVMeUtils.get_from_nvme_list(self.host, self.block_name, "SerialNumber")

    def _get_model(self):
        return NVMeUtils.get_from_nvme_list(self.host, self.block_name, "ModelNumber")

    def get_firmware_version(self):
        """Return drive FW version"""
        return NVMeUtils.get_from_nvme_list(self.host, self.block_name, "Firmware")

    def get_manufacturer(self) -> str:
        """Return drive manufacturer"""
        return "GenericNVMe"

    @retry(tries=3, sleep_seconds=30)
    def get_smart_log(self):
        """Return drive smart log"""
        cmd = "nvme smart-log /dev/%s -o json" % self.block_name
        output = self.host.run(cmd=cmd)
        try:
            log = json.loads(output)
        except json.decoder.JSONDecodeError:
            raise TestError(
                f"Failed to convert to JSON: {output}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )
        smart_log = {"smart-log": log}
        smart_log.update(self.get_ocp_smart_log())
        return smart_log

    def get_ocp_smart_log(self) -> Dict:
        """
        Collect OCP smart log and return it.
        """
        cmd = "nvme ocp smart-add-log /dev/%s -o json" % self.block_name
        try:
            out = self.host.run(cmd)
            log = json.loads(out)
            result = GenericUtils.flatten_dict(log)
        except json.decoder.JSONDecodeError:
            raise TestError(
                f"Failed to convert to JSON: {out}",  # pyre-fixme
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )
        except Exception:
            AutovalLog.log_info(
                f"ocp-smart-add-log is not supported on the drive {self.block_name} ({self.model})."
            )
            return {}
        for k, v in result.items():
            if isinstance(v, int):
                result[k] = float(v)
            elif isinstance(v, str):
                try:
                    result[k] = float(int(v, 16))
                except Exception:
                    result[k] = v
        return {"ocp-smart-add-log": result}

    def get_internal_log(self) -> bool:
        """Return drive internal log.
        Args:
        ----
        None

        Returns:
        -------
        bool: The completion status of internal log file generation.
        """
        dut_logdir = SiteUtils.get_dut_logdir(self.host.hostname)
        cmd = "nvme ocp internal-log /dev/%s" % self.block_name
        ret = self.host.run_get_result(
            cmd=cmd, ignore_status=True, working_directory=dut_logdir
        )
        if ret.return_code != 0:
            AutovalLog.log_info(f"WARNING: command '{cmd}' failed with error code")
            return False
        return True

    def get_effects_log(self):
        """Gets Effects Log.

        This method retrieves the command effects log for the specified drive.

        Returns
        -------
        out : Dictionary
            Value of Admin Command Sets and I/O Command Sets.

        Raises
        ------
        TestStepError
            When fails to retrieve the command effects log.
        """
        cmd = "nvme effects-log /dev/%s -o json" % self.block_name
        out = self.host.run(cmd=cmd)
        return json.loads(out)

    def get_id_ctrl(self):
        """Return id_ctrl"""
        return NVMeUtils.get_id_ctrl(self.host, self.block_name)

    def get_reboot_models(self) -> None:
        """Return drive model for reboot after fw update"""
        # can be provided in the vendor subclass
        return

    def get_susbsystem_reset_models(self) -> None:
        """Return drive model for reboot after fw update"""
        # can be provided in the vendor subclass
        return

    def get_tooling_owned_models(self) -> None:
        """Return models owned by tooling to bypass sed ownership test"""
        # can be provided in the vendor subclass
        return

    def supports_flash_temp_check(self) -> bool:
        """Return whether the drive supports flash temp check"""
        # can be provided in the vendor subclass
        return True

    def get_nand_write_param(self) -> Dict[str, str]:
        """Return nand_write params"""
        # Can be provided in vendor subclass
        return {}

    def get_bit_error_ratio_param(self):
        """Get BER params"""
        # TODO: implement when moving bit_error_ratio_test to Autoval
        return {}

    def get_vs_nand_stat_log(self) -> None:
        """Return vs_nand_stat log"""
        # Can be provided in vendor subclass
        return

    def get_write_amplification(
        self, smart_before: Dict[str, Dict], smart_after: Dict[str, Dict]
    ) -> bool:
        """
        Method to calculate the Flash Write Amplification
        HOST and NAND write bytes are captured before and after test
        to determine total logical and physical write bytes.
        @params: smart_before | Smart data before the test
        @type: dict
        @params: smart_after | Smart data after the test
        @type: dict
        """
        host_write_before = smart_before["smart-log"]["data_units_written"]
        host_write_after = smart_after["smart-log"]["data_units_written"]
        host_delta = host_write_after - host_write_before
        write_amplification = {}
        nand_write_formula = {}
        if (
            "ocp-smart-add-log" not in smart_before
            and "ocp-smart-add-log" not in smart_after
        ):
            return False
        nand_write_formula = {
            "field": "Physical media units written_lo",
            "formula": f"NAND_WRITE/{pow(1024, 3)}",
        }

        nand_write_before = smart_before["ocp-smart-add-log"][
            nand_write_formula["field"]
        ]
        nand_write_after = smart_after["ocp-smart-add-log"][nand_write_formula["field"]]
        nand_delta = nand_write_after - nand_write_before

        # Calculate lifetime Write amp
        write_amplification["lifetime_write_amplification"] = 0
        if host_write_after and nand_write_after:
            waf, error = self.calculate_waf(
                host_write_after, nand_write_after, nand_write_formula
            )
            if waf:
                AutovalLog.log_info(
                    "Lifetime WAF for drive %s is %s" % (self.block_name, waf)
                )
                write_amplification["lifetime_write_amplification"] = waf
                waf = {
                    "name": self.block_name,
                    "write_amplification": waf,
                    "serial_number": self.serial_number,
                    "model": self.manufacturer,
                }
                result_handler = ResultHandler()
                result_handler.update_test_results({self.block_name: waf})
            if error:
                AutovalLog.log_info(
                    "Cannot calculate WAF for drive %s due to %s"
                    % (self.block_name, error)
                )
        AutovalUtils.validate_range(
            write_amplification["lifetime_write_amplification"],
            1.0,
            20.0,
            "WAF expected range",
            warning=True,
        )

        # Calculate Write amp for the currently running test
        write_amplification["test_write_amplification"] = 0
        waf, error = self.calculate_waf(host_delta, nand_delta, nand_write_formula)
        AutovalLog.log_info(
            "WAF during this test for drive %s: %s" % (self.block_name, waf)
        )
        write_amplification["test_write_amplification"] = waf
        if error:
            AutovalLog.log_info(
                "Cannot calculate WAF for drive %s due to %s" % (self.block_name, error)
            )
        AutovalLog.log_info("Drive %s: %s" % (self.block_name, write_amplification))
        return True

    def calculate_waf(self, h_write, n_write, nand_write_formula):
        """
        Method to calculate the Write Amplification factor from the
        Host write and Nand Write
        @params: h_write | host_delta
            (difference of data units written before and after the test)
        @params: n_write | nand_delta
            (difference of nand units written before and after the test)
        @params: nand_write_formula | vendor specific nand write field
        @Returns: Write Amplication Factor
        """
        try:
            host_write = int(h_write) * 512 * 1000 / pow(1024, 3)
            value = (
                nand_write_formula["formula"]
                .replace("NAND_WRITE", str(n_write))
                .replace("value", str(n_write))
                .split("/")
            )
            nand_writes = self._str_to_float(value[0]) / self._str_to_float(value[1])
            waf = nand_writes / host_write
        except ZeroDivisionError as exc:
            return None, exc
        return waf, None

    def _str_to_float(self, value) -> float:
        """Helper function for complex formula"""
        match = re.search(r"(\d+)\s*\**\s*(\d*)", value)
        # pyre-fixme[16]: Optional type has no attribute `group`.
        if match.group(2):
            total = float(match.group(2)) * float(match.group(1))
        else:
            total = float(match.group(1))
        return total

    def convert_nand_write(self, nand_write) -> float:
        """Convert nand write to float"""
        if isinstance(nand_write, str):
            if "," in nand_write:
                nand_write = nand_write.replace(",", "")
            try:
                nand_write = float(nand_write)
            except Exception as exc:
                raise TestError(
                    "Failed convert %s to float: %s" % (nand_write, exc),
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.TOOL_ERR,
                )
        return nand_write

    def get_drive_name(self):
        """
        Get NVMe drive name without the namespace part
            e.g. "nvme1n1" -> "nvme1"
        @return string
        """
        match = re.search(r"(nvme\d+)", self.block_name)
        if not match:
            _msg = "Failed to get NVMe drive name from block name %s" % self.block_name
            raise TestError(
                _msg,
                error_type=ErrorType.NVME_ERR,
            )
        return match.group(1)

    def collect_data(self):
        data = {
            "SMART": self.get_smart_log(),
            "firmware": self.get_firmware_version(),
            "serial_number": self.serial_number,
            "type": self.type.value,
            "interface": self.interface.value,
            "model": self.model,
            "manufacturer": self.manufacturer,
            "id_ctrl": self.id_ctrl,
            "capacity": self.get_capacity(),
            "id_ns": self.get_id_ns(),
        }
        _strip_white_spaces_from_keys(data)
        return data

    def update_firmware(self, *args, **kwargs) -> None:
        """Update Firmware for NVMe Drives.
        This method updates the drive firmware using below parameters.

        Parameters
        ----------
        *args: :obj: `List` of :obj: `str`
            fw_version - Firmware version to upgrade
            fw_bin_loc - Binary path
        **kwargs:
            ``fw_slots``:
                Slots to install firmware (`List` of `int`)
            ``actions``:
                Provide param for nvme fw-activate --action option
                (`int`)
            ``force``:
                Provide boolean for force install (`bool`)
        """
        if len(args) == 0 and len(kwargs) == 0:
            raise TestError(
                "No parameters found for firmware update",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.INPUT_ERR,
            )
        # positional arg[0] will have firmware version and
        # arg[1] will have firmware binary location.
        expected_fw_version = args[0]
        fw_bin_loc = args[1]
        fw_slots = kwargs.get("fw_slots", [])
        action = kwargs.get("action", 1)
        force = kwargs.get("force", False)
        nvme_admin_io = kwargs.get("nvme_admin_io", False)
        drive_name = self.get_drive_name()
        AutovalLog.log_info(f"+++Nvme firmware update with action {action}")
        # not supported actions
        ns_action_list = self.get_fw_update_ns_actions()
        if action in ns_action_list:
            AutovalLog.log_info(
                f"+++ Skipping the Firmware update because update with "
                f"action {action} is not supported in the drive "
                f"{self.serial_number} of model {self.model}."
            )
            return
        fw_ver = self.get_firmware_version()
        if not force and expected_fw_version == fw_ver:
            AutovalLog.log_info(
                "Device already updated with latest version: %s" % fw_ver
            )
            return
        fw_bin_loc = FileActions.get_local_path(self.host, fw_bin_loc)
        if not isinstance(fw_slots, list) or len(fw_slots) == 0:
            fw_slots = self.get_fw_slots()
            ns_fw_slots = self.fw_ns_slots_models_map.get(self.model, [])
            if ns_fw_slots:
                AutovalLog.log_info(
                    f"Removing the Not Supported Slots : {ns_fw_slots} from firmware slots : {fw_slots}"
                )
                fw_slots = [i for i in fw_slots if i not in ns_fw_slots]
        if action == 2:
            AutovalLog.log_info(
                f"Skipping update on slot0. Firmware update action {action} "
                "does not support the update on slot 0 as this will pick any random"
                " slot and will activate the firmware downloaded on that slot which"
                " might not be the expected version."
            )
            fw_slots.remove(0)
        AutovalUtils.validate_non_empty_list(
            fw_slots,
            f"Validate the supported slots for the firmware action {action} "
            "are not none",
            warning=True,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.FIRMWARE_ERR,
        )
        for fw_slot in fw_slots:
            AutovalLog.log_info(
                f"Performing update on drive {drive_name} slot: {fw_slot}"
            )
            self._fw_download(drive_name, fw_bin_loc)
            if nvme_admin_io:
                """
                for nvme_admin_io, we have commit, admin and IO timers to check the how long
                commit action, admin and IO commands take and validate them. We do not require timers for
                general flash_firmware_update test. Hence, including an if else condition here.
                """
                fw_ver = self.get_nvme_id_ctrl_fw_revision()  # noqa
                self.fw_commit_timer_before = time.perf_counter()  # noqa
                if action == 2:
                    # As per the nvme spec action 2 will only avtivates the
                    # firmware which is already present on the slot. So
                    # downloading the firmware on the slot using action 0.
                    # Action 0: Downloaded image replaces the existing image,
                    # if any, in the specified Firmware Slot. The
                    # newly placed image is not activated.
                    self.fw_activate(
                        drive_name,
                        fw_bin_loc,
                        fw_slot,
                        action=0,
                        nvme_admin_io=nvme_admin_io,
                    )
                self.fw_activate(drive_name, fw_bin_loc, fw_slot, action, nvme_admin_io)
                if self.reboot_models and self.model in self.reboot_models:
                    AutovalLog.log_info(
                        f"Rebooting as the {self.serial_number} {self.model} "
                        "requires reboot after firmware update."
                    )
                    self.host.oob.cycle()
                elif action != 2:
                    # All the actions except action 3 requires reset of the drive
                    # for the updated firmware version to reflect.
                    if action != 3:
                        AutovalLog.log_info(
                            f"Resetting as the {self.serial_number} {self.model} "
                            f"requires reset for action {action}"
                        )
                        self.reset()
                self.fw_commit_timer_after = time.perf_counter()  # noqa
                self.command_timer_before = time.perf_counter()  # noqa
                self.admin_command = self.get_nvme_id_ctrl()  # noqa
                self.admin_command_timer_after = time.perf_counter()  # noqa
                self.io_command = self.get_nvme_read()  # noqa
                self.io_command_timer_after = time.perf_counter()  # noqa

            elif nvme_admin_io is False:
                if action == 2:
                    # As per the nvme spec action 2 will only avtivates the
                    # firmware which is already present on the slot. So
                    # downloading the firmware on the slot using action 0.
                    # Action 0: Downloaded image replaces the existing image,
                    # if any, in the specified Firmware Slot. The
                    # newly placed image is not activated.
                    self.fw_activate(
                        drive_name,
                        fw_bin_loc,
                        fw_slot,
                        action=0,
                        nvme_admin_io=True,
                    )
                self.fw_activate(
                    drive_name,
                    fw_bin_loc,
                    fw_slot,
                    action,
                    nvme_admin_io,
                )
                # Checking if the drive model requires reboot after update.
                if self.reboot_models and self.model in self.reboot_models:
                    AutovalLog.log_info(
                        f"Rebooting as the {self.serial_number} {self.model} "
                        "requires reboot after firmware update."
                    )
                    self.host.oob.cycle()
                elif action != 2:
                    # All the actions except action 3 requires reset of the drive
                    # for the updated firmware version to reflect.
                    if action != 3:
                        AutovalLog.log_info(
                            f"Resetting as the {self.serial_number} {self.model} "
                            f"requires reset for action {action}"
                        )
                        self.reset()
            self.validate_firmware_update(expected_fw_version)

    def _fw_download(self, drive_name, file_name) -> None:
        """
        This method downloads the firmware binary file that is
        to be updated for the drive.

        Parameters
        ----------
        drive_name : String
            The drive name on which the firmware to be updated.
        file_name : String
            Firmware binary path.
        """
        cmd = f"nvme fw-download /dev/{drive_name} -f '{file_name}'"
        AutovalLog.log_info(self.host.run(cmd=cmd))  # noqa

    def fw_activate(
        self,
        drive_name: str,
        file_name: str,
        fw_slot: List[int],
        action: int,
        nvme_admin_io=True,
    ) -> None:
        """
        This method activates the downloaded firmware binary file on
        the drive.

        Parameters
        ----------
        drive_name : String
            The drive name on which the firmware to be updated.
        file_name : String
            Firmware binary path.
        fw_slot : :obj: 'List' of :obj: 'Integer'
            Firmware slots to update.
        action : Integer
            Provides param for nvme fw-activate --action option.
        nvme_admin_io: Boolean
            Flag to indicate whether to wait or not.
        """
        cmd = "nvme fw-activate /dev/%s --slot=%d --action=%d" % (
            drive_name,
            fw_slot,
            action,
        )
        AutovalLog.log_info(
            f"Flashing device {drive_name}, serial {self.serial_number} "
            f"with {file_name} on slot: {fw_slot}"
        )
        try:
            AutovalLog.log_info(self.host.run(cmd=cmd))  # noqa
        except Exception as exc:  # thrift.py run() throws base Exception
            if (
                "firmware requires subsystem reset"
                or "firmware requires any controller reset" in str(exc)
            ):
                AutovalLog.log_info(
                    "Activation firmware is successful, but required reset"
                )
            else:
                AutovalLog.log_info("Unknown exception occured: %s" % exc)
        if not nvme_admin_io:
            self.post_fw_activate()

    def post_fw_activate(self) -> None:
        """
        This method decides the time to wait to complete the fw activation
        """
        sleep_time = 10
        AutovalLog.log_info(f"Waiting for {sleep_time} seconds")
        sleep(sleep_time)

    def get_vs_timestamp(self) -> int:
        """Get timestamp in seconds:

        get-feature:0xe (Timestamp), Current value:00000000
        The timestamp is : 1588708604426
        The Timestamp was initialized with a value using a Set Features command.
        The controller counted time in ms continuously since value was initialized.
        By default since midnight, 01-Jan-1970, UTC
        """
        out = self.get_feature(feature_id=["0xe"])
        match = re.search(r"The timestamp is\s+:\s+(\d+)", out[0])
        if match:
            time_ms = float(match.group(1))
            time = int(time_ms / 1000.0)
            return time
        raise NotImplementedError(
            "Get vendor time-stamp is not implemented for this vendor"
        )

    def reset(self) -> None:
        drive_name = self.get_drive_name()
        if self.subsystem_reset_models and self.model in self.subsystem_reset_models:
            self.subsystem_reset(drive_name)
        else:
            if self.get_fw_update_reset_req_models():
                sleep_time = 30
            else:
                sleep_time = 10
            out = self.host.run(
                cmd="nvme reset /dev/%s" % drive_name, ignore_status=True
            )
            if "dropped connection" in out:
                sleep_time += 5
            AutovalLog.log_info(f"Waiting for {sleep_time} secs after the reset")
            sleep(sleep_time)

    def get_fw_update_reset_req_models(self) -> bool:
        """
        Get Firmware Update Reset Req Models.
        This method will return True if the model required reset.
        """
        return self.model in self.fw_update_reset_req_models

    def subsystem_reset(self, drive_name) -> None:
        AutovalLog.log_info("Waiting for 20 seconds before subsystem-reset")
        sleep(20)
        AutovalLog.log_info("Running subsystem-reset")
        self.host.run(
            cmd="nvme subsystem-reset /dev/%s" % drive_name, ignore_status=True
        )

    def nvme_flush(self) -> None:
        """
        Method to commit data and metadata associated
        with given namespaces to nonvolatile media
        """
        nvme_drive = "/dev/%s" % self.block_name
        cmd = "nvme flush %s" % nvme_drive
        AutovalUtils.validate_no_exception(
            self.host.run,
            [cmd],
            "Run '%s'" % cmd,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )

    def get_write_cache(self):
        """
        Method to get the write cache value on the drive.
        """
        return NVMeUtils.get_write_cache(self.host, self.block_name)

    def enable_write_cache(self, save: bool = False) -> None:
        """
        Method to enable write cache on the drive.

        @param boolean save: Used to maintain uniform interface with SASDrive.
        """
        NVMeUtils.enable_write_cache(self.host, self.block_name)

    def disable_write_cache(self, save: bool = False) -> None:
        """
        Method to disable the write cache on the drive.

        @param boolean save: Used to maintain uniform interface with SASDrive.
        """
        NVMeUtils.disable_write_cache(self.host, self.block_name)

    def format_drive(self, secure_erase_option: int = 0) -> None:
        """Format Drive

        To perform secure erase operation on NVMe drive.
        """
        return NVMeUtils.format_nvme(self.host, self.block_name, secure_erase_option)

    def get_drive_temperature(self) -> int:
        """Get Drive Temperature

        Collect the temperature on NVMe drive.
        """
        return NVMeUtils.get_nvmedrive_temperature(self.host, self.block_name)

    def check_readonly_mode(self) -> bool:
        """Check Read only Mode

        To check the drive is in Read only mode.
        """
        return NVMeUtils.is_read_only(self.host, self.block_name)

    def drive_health_check(self) -> None:
        """
        This function checks if the drive under test has fatal error support
        and critical warnings

        Raises
        ------
        TestError
              When the drive does not support fatal error or
              critical warning more than zero.
        """
        pci_addr = PciUtils().get_nvme_drive_pcie_address(self.host, self.block_name)
        cmd = "-s " + pci_addr + " -vvv"
        out = PciUtils().get_lspci_output(self.host, options=cmd)
        # Search Fatal and FatalErr it output & validate it was set
        pattern = re.search(r"\s+(Fatal\-|Fatal\+|FatalErr\-|FatalErr\+)", out)
        if pattern:
            output = pattern.group(1).strip()
            if output == "Fatal-" or output == "FatalErr-":
                AutovalUtils.validate_condition(
                    False,
                    "Fatal/FatalErr has not set in lspci output, check the drive %s"
                    % self.block_name,
                    raise_on_fail=False,
                    warning=True,
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.PCIE_ERR,
                )
        else:
            AutovalUtils.validate_condition(
                False,
                "Did not find Fatal/FatalErr in the lspci output, check the drive %s"
                % self.block_name,
                raise_on_fail=False,
                warning=True,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.PCIE_ERR,
            )
        # Search UnsuppReg in uncorrectable error status & validate it was set
        pattern = re.search(r"\s+(UnsuppReg\-|UnsuppReg\+|UnsupReg\-|UnsupReg\+)", out)
        if pattern:
            output = pattern.group(1).strip()
            if output == "UnsuppReg-" or output == "UnsupReg-":
                AutovalLog.log_info(
                    "Warning - UnsuppReg has not set in lspci output, check the drive %s"
                    % self.block_name
                )
        else:
            AutovalLog.log_info(
                "Warning: Did not find UnsuppReg in lspci output, check the drive %s"
                % self.block_name
            )
        smart_log = self.get_smart_log()
        critical_warning = smart_log["smart-log"]["critical_warning"]
        if critical_warning > 0:
            raise TestError(
                f"The {self.manufacturer} drive {self.serial_number}"
                f" found {critical_warning} critical warning.",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

    def drive_erase_count(self) -> None:
        """
        This function calculates the delta value between the minimum and
        maximum erase count. If the delta value is greater than 500 then
        raise TestError.
        """
        smart_log = self.get_smart_log()
        try:
            min_erase = smart_log["vs-smart-add-log"]["User Data Erase Count (Min)"]
            max_erase = smart_log["vs-smart-add-log"]["User Data Erase Count (Max)"]
            delta = max_erase - min_erase
            # TODO: define valid requirenments for D22741551
            AutovalUtils.validate_less(
                delta,
                500,
                raise_on_fail=False,
                log_on_pass=False,
                msg=f"/dev/{self.block_name}: User-data Erase Count delta",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
        except KeyError:
            pass

    def get_fw_update_ns_actions(self) -> List[int]:
        """Get Firmware update non supported actions.
        This method will return the list of actions which are
        not supported on the model.
        Returns
        -------
        ns_actions_list : :obj:List of integers.
             list of not supported actions from the pre defined
             vendor specific dictionary, would return empty if
             the model is not defined in the dictionary.
        """
        # get the list of not supported actions.
        # empty list means all actions are supported
        ns_actions_list = self.fw_ns_action_model_map.get(self.model, [])
        return ns_actions_list

    def is_drive_degraded(self) -> None:
        """
        Is Drive degraded.

        This method will check if the nvme drive is degraded,
        by checking if the drive firmware version is having any
        "error*" string match.

        Raises
        ------
        TestError
              When the drive firmware version is not as expected.
        """
        pattern = r"(?i)^error.*$"
        firmware = self.get_firmware_version().lower()
        match = re.match(pattern, firmware)
        if match:
            raise TestError(
                f"The {self.manufacturer} drive {self.serial_number} found degraded.",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

    def get_fw_slots(self) -> List[int]:
        """Get available FW slots"""
        nvme_drive = "/dev/%s" % self.block_name
        out = self.get_nvme_id_ctrl(human_readable=True)
        match = re.search(r"(0x\d)\s+Number of Firmware Slots", out)
        if match:
            slots = list(range(int(match.group(1), 16)))
        else:
            return [0]
        # Remove read-only slot from list if exists
        match2 = re.search(r"(0x\d)\s+Firmware Slot\s.*\sRead-Only", out)
        if match2:
            slot = int(match2.group(1), 16)
            AutovalLog.log_info(
                f"WARNING: Slot {slot} is read-only on drive {nvme_drive}"
            )
            slots.remove(slot)
        AutovalUtils.validate_greater(
            len(slots),
            0,
            "Number of FW slots for drive %s" % nvme_drive,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.FIRMWARE_ERR,
        )
        return slots

    def get_drive_supported_power_modes(self):
        """
        :Get available supported power mode
        ...
        :return: drive supported power modes.
        :rtype: list
        """
        out = self.get_nvme_id_ctrl()
        match = re.findall(r"ps\s+(\d+)\s+:\s+.*W\s+operational\s+.*", out)
        drive_supported_power_modes = [int(val) for val in match]
        AutovalUtils.validate_greater(
            len(drive_supported_power_modes),
            0,
            f"Number of supported power mode {drive_supported_power_modes} for drive /dev/{self.block_name}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        return drive_supported_power_modes

    def get_power_state_change_counter(self) -> int:
        """Get Power State Change Counter.
        This method gets the Power State Change Counter value from Log page LID=0xC0h (Bytes 299:292)
        by issuing nvme get-log <device>  -i 0xc0
        and extract the Power State Change counter value from std_out.
        cmd = nvme get-log /dev/nvme1n1 --log-id=0xC0h --log-len=299
        Sample return value in this case would be : 9876543
        """

        # Command to get Power state change counter (PSCC)
        cmd = f"nvme get-log /dev/{self.block_name} --log-id=0xC0h --log-len=299"
        out = self.host.run(cmd=cmd)  # noqa

        # save PSCC value
        for line in out.splitlines():
            match = re.search(r"^0120:\s.*\b", line)

        # match = <re.Match object; span=(0, 38), match='0120: 00 00 01 02 03 04 05 06 07 08 09'>
        # to extract PSSC from match
        power_state_change_count_value = match.group(0)

        # To extract PSSC value from bytes 292:299
        power_state_change_count_value = list(
            power_state_change_count_value.split(" ")[5:]
        )
        # convert char to int
        power_state_change_count_value = [
            int(item) for item in power_state_change_count_value
        ]
        # reverse the bytes to read the PSSC value [3, 4, 5, 6, 7, 8, 9] -->[9, 8, 7, 6, 5, 4, 3]
        power_state_change_count_value.reverse()
        # convert this into int number - 9876543
        strings = [str(integer) for integer in power_state_change_count_value]
        a_string = "".join(strings)
        power_state_change_count_value = int(a_string)
        AutovalLog.log_info(power_state_change_count_value)
        # sample return value would be - 9876543
        return power_state_change_count_value

    def get_power_mode(self) -> int:
        """Get Power Mode.

        This method gets the current value of the power mode
        using the power management feature of the drive.

        Returns
        -------
        match.group(1) : String
            Get feature value that gives current power-mode of
            the drive. Eg: "6".

        Raises
        ------
        TestError
            When fails to match the get-feature output with the
            given pattern.
        """
        cmd = "nvme get-feature /dev/%s -f 0x2" % self.block_name
        out = self.host.run(cmd=cmd)  # noqa
        match = re.search(r"value:\s*(\S+)", out)
        if match:
            return int(match.group(1), 16)
        raise TestError(
            "Failed to get power mode",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def set_power_mode(self, feature_value: int) -> int:
        """Set Power Mode.

        This method sets the value of the power mode using
        the power management feature of the drive.

        Returns
        -------
        feature_value : String
            Set feature value that gives current power-mode of
            the drive. Eg: "5".

        Raises
        ------
        TestError
            - When fails to set the power mode.
            - When fails to match the set-feature output with the
              given pattern.
        NotImplementedError
            - When the power mode is not supported by the drive.
        """

        cmd = "nvme set-feature /dev/%s -f 0x2 -v %s" % (
            self.block_name,
            feature_value,
        )
        out = self.host.run(cmd=cmd)  # noqa
        match = re.search(r"value:\s*(\S+)", out)
        if match:
            if int(match.group(1), 16) == feature_value:
                return feature_value
        # Drive supports feature value only within the available
        # number of power states.
        raise TestError(
            f"The power-mode {feature_value} is not set",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def is_sed_drive(self) -> bool:
        """
        Is SED Supported drive.

        This method will Check if the drive supports SED and as per OPAL 2.0 spec.
        """
        from autoval_ssd.lib.utils.sed_util import SedUtils

        return SedUtils.get_sed_support_status(self.host, self.block_name)

    def get_tcg_ownership_status(self) -> OwnershipStatus:
        """Get the TCG ownership status.

        This method will check if the TCG ownership is taken or not.
        Note: Logic is based on https://www.internalfb.com/diff/D26582194

        Returns
        -------
        status: :Enum :obj of OwnershipStatus
           Ownership status.

        Raises
        ------
        TestError:
           1. If drive is not a SED drive.
           2. Block SID Authentication TPer not found.
        """
        if not self.is_sed_drive():
            raise TestError(
                f"Drive: {self.block_name} is not an SED drive "
                "to check for the TCG ownership",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
        out = NVMeUtils.run_nvme_security_recv_cmd(self.host, self.block_name)
        # https://trustedcomputinggroup.org/wp-content/uploads/TCG_Storage_Architecture_Core_Spec_v2.01_r1.00.pdf
        match = re.search(r"04\s02\s\S{2}\s\S{2}\s(\S{2})\s", out)
        # looking for the feature code 0402 to identify the c_pin
        if match:
            byte_0xA8_int = int(match.group(1))
            sid_state = byte_0xA8_int & 1
            sid_auth_blocked_state = (byte_0xA8_int >> 1) & 1
            if sid_state and not sid_auth_blocked_state:
                return OwnershipStatus.SET
            if sid_auth_blocked_state and sid_state:
                return OwnershipStatus.BLOCKED_AND_SET
            if sid_auth_blocked_state and not sid_state:
                return OwnershipStatus.BLOCKED_AND_NOT_SET
            if not sid_state and not sid_auth_blocked_state:
                return OwnershipStatus.NOT_SET
        raise TestError(
            f"Byte 0xA8 value not recognized for {self.block_name}. {out}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def is_fw_history_supported(self) -> bool:
        """
        Returns True if firmware activation history is supported by this drive.
        """
        return True

    def validate_fw_commit_timer(self, fw_commit_timer_after, fw_commit_timer_before):
        fw_commit_timer = fw_commit_timer_after - fw_commit_timer_before
        # Maximum Time For Activation
        mtfa = self.get_nvme_id_ctrl_mtfa()
        if mtfa != 0:
            expected_commit_timer = mtfa * 100
            AutovalUtils.validate_less(
                fw_commit_timer,
                expected_commit_timer,
                f"fw_commit_timer: {fw_commit_timer} and expected_commit_timer (mtfa * 100) {expected_commit_timer}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.FIRMWARE_ERR,
            )
        else:
            AutovalUtils.validate_condition(
                0,
                f"Maximum Time for Firmware Activation (mtfa) is : {mtfa} and hence expected_commit_timer (mtfa * 100) is not calculated.",
                warning=True,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.FIRMWARE_ERR,
            )

    def validate_admin_command_timer(
        self, admin_command_timer_after, command_timer_before
    ):
        admin_completion_timer = admin_command_timer_after - command_timer_before
        AutovalUtils.validate_less(
            admin_completion_timer,
            10,
            f"Check if admin_completion_timer: {admin_completion_timer} is less than 10 seconds",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def validate_io_command_timer(self, io_command_timer_after, command_timer_before):
        io_completion_timer = io_command_timer_after - command_timer_before
        AutovalUtils.validate_less(
            io_completion_timer,
            10,
            f"Check if io_command_completion_timer: {io_completion_timer} is less than 10 seconds",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def check_admin_command_success(self, admin_command):
        new_fw_ver = self.get_nvme_id_ctrl_fw_revision()
        match = re.search(r"fr\s+:\s+(.*)", admin_command)
        fw_version = str(match.group(1))
        AutovalUtils.validate_equal(
            fw_version,
            new_fw_ver,
            "Admin command validation",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def check_io_command_success(self, io_command):
        check_success = [value for value in io_command.split(" ") if value == "Success"]
        if check_success:
            AutovalUtils.validate_equal(
                check_success[0],
                "Success",
                "io command validation",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

    def check_new_firmware_current_firmware(self, fw_ver):
        current_fw_ver = self.get_nvme_id_ctrl_fw_revision()
        AutovalUtils.validate_not_equal(
            fw_ver,
            current_fw_ver,
            f"Older firmware version {fw_ver} and current firmware version {current_fw_ver}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.FIRMWARE_ERR,
        )

    def is_ocp_2_6_drive(self) -> bool:
        return self.model in self.ocp_2_6_drives

    def get_workload_target_status(self) -> bool:
        """
        Get workload target status

        If this drive model is capable of reaching the current performance expectations
        in workoad targets then True is returned.
        """
        return self.model in self.workload_target_drives or self.is_ocp_2_6_drive()

    def is_lmparser_ocp_2_0_drive(self) -> bool:
        """Returns True if drive model-firmware combination is suitable for OCP 2.0 LM parsing"""
        if self.model in self.lmparser_ocp_2_0_drives.get("AnyFW", []):
            return True
        fw_ver = self.get_firmware_version()
        if fw_ver in self.lmparser_ocp_2_0_drives:
            if self.model in self.lmparser_ocp_2_0_drives[fw_ver]:
                return True
        return False
