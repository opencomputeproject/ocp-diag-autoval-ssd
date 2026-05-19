#!/usr/bin/env python3

# pyre-unsafe
"""Test to validate NVME cli commands"""

import datetime
import importlib
import json
import os
import re
from pprint import pformat
from typing import Any, Optional

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.async_utils import AsyncJob, AsyncUtils
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.file_actions import FileActions
from autoval.lib.utils.site_utils import SiteUtils
from autoval_ssd.lib.utils.fio.fio_synth_flash_utils import FioSynthFlashUtils
from autoval_ssd.lib.utils.storage.nvme.fdp_utils import FDPUtils
from autoval_ssd.lib.utils.storage.nvme.latency_monitor_utils import LatencyMonitor
from autoval_ssd.lib.utils.storage.nvme.nvme_drive import NVMeDrive
from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase


class NvmeCli(StorageTestBase):
    """
    Test to validate if NVME spec commands are supported
    Validations done on all the NVME drives:
        Get the controller properties,
        Get the Firmware Log,
        Check Crypto Erase Support,
        Get Error Log Entries,
        Log the properties of the specified namespace,
        Get the operating parameters of the specified controller,
        identified by the Feature Identifier,
        Get Vendor Specific Internal Logs,
        Retrieve Command Effects Log.
        Get Vendor Specific drive up time,
        Get Smart log,
        Get/Set Power mode.
        validate capacity
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.drive_type = self.test_control.get("drive_type", None)
        self.drive_interface = self.test_control.get("drive_interface", None)
        self.crypto_erase = self.test_control.get("check_crypto_erase", True)
        self.arbitration_mechanism = self.test_control.get(
            "arbitration_mechanism", True
        )
        self.nvme_telemetry_log_timeout = self.test_control.get(
            "telemetry_log_timeout", 1200
        )
        # List of NVMECli commands to skip
        self.skip_commands = self.test_control.get("skip_commands", [])

        self.fdp_setup = self.test_control.get("fdp_setup", False)
        self.fdp_enabled = False
        self.comparand_nvme_version = self.test_control.get(
            "comparand_nvme_version", None
        )

    def execute(self) -> None:
        self.log_info("Test to run NVME Cli commands")
        first_nvme_version = NVMeUtils.get_nvme_version(self.host)
        first_nvmecli_command_output = self.run_nvme_cli_commands(first_nvme_version)
        if self.comparand_nvme_version:
            self.install_nvme_version(self.comparand_nvme_version)
            new_nvme_version = NVMeUtils.get_nvme_version(self.host)
            if first_nvme_version == new_nvme_version:
                self.validate_not_equal(
                    first_nvme_version,
                    new_nvme_version,
                    "Can't compare versions when the new version is the same as the current one",
                )
            else:
                new_nvme_cli_command_output = self.run_nvme_cli_commands(
                    new_nvme_version
                )
                self.compare_command_outputs(
                    first_nvme_version,
                    first_nvmecli_command_output,
                    new_nvme_version,
                    new_nvme_cli_command_output,
                )

    def run_nvme_cli_commands(self, nvme_version: str) -> list[dict]:
        """
        Run all nvme-cli commands for this test.

        Args:
            nvme_version: The version of nvme-cli currently installed.
        Returns:
            A list of dictionaries representing the output of each command that was run.
        """
        self.log_info(f"Running nvme-cli commands for version {nvme_version}")
        if self.skip_commands:
            self.log_info(f"Skipping NVMECli commands: {self.skip_commands}")
        command_outputs = AsyncUtils.run_async_jobs(
            [
                AsyncJob(
                    func=self.validate_nvme_drives,
                    args=[drive, nvme_version],
                )
                for drive in self.test_drives
            ]
        )
        if self.fdp_setup:
            self.validate_fdp()
        self.validate_latency_monitor()
        return command_outputs

    def validate_nvme_drives(self, drive: NVMeDrive, nvme_version: str) -> list[dict]:
        """
        This method performs a series of NVMe cli commands on the NVMe drive
        and performs validation using the output of each command that is run.
        The output is additionally saved so that it can be compared with an
        output for another version, if specified in the test control.

        Args:
            drive: The NVMe drive to validate.
            nvme_version: The version of nvme-cli currently installed.
        Returns:
            A list of dictionaries representing the output of each command that was run.
        """
        AutovalUtils.validate_condition(
            (not drive.check_readonly_mode()),
            "Check drive nvme is write mode enabled %s" % drive.block_name,
            raise_on_fail=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        self.methods_to_call = {
            "_get_fw_log": self._get_fw_log,
            "_get_smart_log": self._get_smart_log,
            "_get_error_log": self._get_error_log,
            "_get_nvme_ns_map": self._get_nvme_ns_map,
            "_get_id_ns": self._get_id_ns,
            "_get_feature": self._get_feature,
            "_get_effects_log": self._get_effects_log,
            "_get_vs_timestamp": self._get_vs_timestamp,
            "_validate_power_mode": self._validate_power_mode,
            "_validate_capacity": self._validate_capacity,
            "_check_oacs_device_self_test": self._check_oacs_device_self_test,
            "_get_internal_log": self._get_internal_log,
            "get_ocp_telemetry_string_log": lambda drive: drive.get_ocp_telemetry_string_log(),
            "get_ocp_error_recovery_log": lambda drive: drive.get_ocp_error_recovery_log(),
            "get_ocp_device_capability_log": lambda drive: drive.get_ocp_device_capability_log(),
            "get_ocp_unsupported_reqs_log": lambda drive: drive.get_ocp_unsupported_reqs_log(),
            "get_ocp_tcg_configuration_log": lambda drive: drive.get_ocp_tcg_configuration_log(),
        }
        command_outputs = []
        for method_name, method in self.methods_to_call.items():
            if method_name not in self.skip_commands:
                command_outputs.append(
                    {"method_name": method_name, "output": method(drive)}
                )
        drive.get_smartctl_output()
        drive.get_ocp_hardware_component_log(nvme_version)
        if self.crypto_erase:
            self._validate_crypto_erase_support(drive)
        if self.arbitration_mechanism:
            self._validate_arbitration_mechanism(drive)
        return command_outputs

    def _validate_arbitration_mechanism(self, drive: NVMeDrive) -> None:
        # Check arbitration_mechanism
        out = drive.get_arbitration_mechanism_status()
        if out:
            match = re.search(r"Arbitration Mechanism Selected\s+\(AMS\):\s+(.*)", out)
            if match:
                arbitration_mechanism = match.group(1)
                AutovalUtils.validate_condition(
                    "Round Robin" in arbitration_mechanism,
                    "%s: Arbitration Mechanism is %s"
                    % (drive.block_name, arbitration_mechanism),
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )
            else:
                AutovalUtils.validate_condition(
                    False,
                    "Arbitration Mechanism not found",
                    raise_on_fail=False,
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )
            # Check csts
            csts_match = re.search(r"csts\s+:\s+(0x[0-9a-fA-F]+|\d+)", out)
            if csts_match:
                csts = int(csts_match.group(1), 0)
                AutovalUtils.validate_equal(
                    csts,
                    1,
                    "{}: csts is {}".format(drive.block_name, csts),
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )
            else:
                AutovalUtils.validate_condition(
                    False,
                    "csts not found",
                    raise_on_fail=False,
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )

    def _validate_crypto_erase_support(self, drive: NVMeDrive) -> None:
        out = drive.get_crypto_erase_support_status()
        if out is False:
            self.log_info(
                "Skip Crypto Erase validation on boot drive and drives "
                "which dont support it"
            )
        else:
            AutovalUtils.validate_condition(
                out,
                "%s: Crypto Erase Supported" % drive,
                raise_on_fail=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )

    def _get_fw_log(self, drive: NVMeDrive) -> dict:
        """
        Runs the nvme fw-log command on the provided drive.

        Args:
            drive: The NVMe drive to run the command on.
        Returns:
            Output of the nvme fw-log command as a dict.
        """
        fw_log = {}
        out = drive.get_fw_log()
        try:
            fw_log = json.loads(out)
        except json.decoder.JSONDecodeError:
            fw_log = NVMeUtils.parse_json_string(out)

        self.validate_greater(
            len(fw_log),
            0,
            str(fw_log),
            raise_on_fail=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        return fw_log

    def _get_smart_log(self, drive: NVMeDrive) -> dict:
        """
        Runs the nvme smart-log command on the provided drive.

        Args:
            drive: The NVMe drive to run the command on.
        Returns:
            Output of the nvme smart-log command as a dict.
        """
        out = drive.get_smart_log()
        smart_log = out["smart-log"]
        self.validate_greater(
            len(smart_log),
            0,
            msg=f"smart-log from drive {str(drive)} has at least one entry.",
            raise_on_fail=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        return smart_log

    def _get_error_log(self, drive: NVMeDrive) -> dict:
        """
        Retrieves the error log from the given drive.

        Args:
            drive: The NVMe drive to run the command on.
        Returns:
            Output of the nvme error-log command as a dict.
        """
        out_json = {}
        out = drive.get_error_log()
        try:
            out_json = json.loads(out)
        except json.decoder.JSONDecodeError:
            out_json = NVMeUtils.parse_json_string(out)
        error_log = out_json["errors"]
        self.validate_non_empty_list(
            list(error_log),
            msg=f"error-log from drive {str(drive)} has at least one entry.",
            raise_on_fail=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        return error_log[0]

    def _get_id_ns(self, drive: NVMeDrive) -> dict:
        """
        This function retrieves identity namespace results for the given drive.

        Args:
            drive: The NVMe drive to run the command on.
        Returns:
            Output of the nvme id-ns command as a dict.
        """
        out = drive.get_id_ns()
        try:
            out_json = json.loads(out)
        except json.decoder.JSONDecodeError:
            out_json = NVMeUtils.parse_json_string(out)
        self.validate_greater(
            len(out_json),
            0,
            msg=f"ID Namespace log from drive {str(drive)} has at least one entry.",
            raise_on_fail=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        return out_json

    def _get_nvme_ns_map(self, drive: NVMeDrive) -> dict:
        """
        Runs the nvme list command on the provided drive.

        Args:
            drive: The NVMe drive to run the command on.
        Returns:
            Output of the nvme list command as a dict.
        """
        n_s = NVMeUtils.get_nvme_ns_map(
            self.host, drive.block_name, drive.serial_number
        )
        for _, value in n_s.items():
            self.validate_greater_equal(
                len(value),
                1,
                "namespace is %s" % value,
                raise_on_fail=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
        return n_s

    def _get_feature(self, drive: NVMeDrive) -> list[str]:
        """
        Runs the nvme get-feature command on the provided drive.

        Args:
            drive: The NVMe drive to run the command on.
        Returns:
            A list of strings containing the fetched operating parameters for each feature ID.
        """
        feature_info = drive.get_feature()
        self.validate_greater(
            len(feature_info),
            0,
            "Features have been taken",
            raise_on_fail=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        return feature_info

    def _get_internal_log(self, drive: NVMeDrive) -> Optional[bool]:
        """Gets Vendor Specific Log.

        This method gets the internal log in binary format for different
        vendors based on the drive.

        Parameters
        ----------
        drive : :obj: 'Class'
            Object of vendor class.
        Returns:
            Optional[bool]: True if the internal log has been taken, False otherwise.
            If the drive does not support internal log, None is returned.
        """
        try:
            status = drive.get_internal_log(self.nvme_telemetry_log_timeout)
            self.log_info(f"Internal log has {'' if status else 'not'} been taken")
            return status
        except NotImplementedError as exc:
            self.log_info(exc)

    def _get_effects_log(self, drive: NVMeDrive) -> Optional[dict]:
        """
        This method retrieves the ACS(Admin Command Set) and
        IOCS(I/O Command Set) logs of the drive.

        Args:
            drive (NVMeDrive): The drive from which to retrieve effects logs.

        Returns:
            Optional[Dict]: A dictionary containing the ACS and IOCS logs.
            If the drive does not support effects logs, None is returned.
        """
        try:
            out = drive.get_effects_log()
            self.validate_greater(
                len(out),
                0,
                msg=f"effects-log from drive {str(drive)} has at least one entry.",
                raise_on_fail=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
            return out
        except NotImplementedError as exc:
            self.log_info(exc)

    def get_test_params(self) -> str:
        params = "Drive type: {}, Drive interface: {}, Check crypto erase: {}".format(
            self.drive_type, self.drive_interface, self.crypto_erase
        )
        return params

    def _get_vs_timestamp(self, drive: NVMeDrive) -> Optional[int]:
        """Gets Vendor Specific Drive Timestamp.

        This method gets the drive up time for different
        vendors based on the drive.

        Parameters
        ----------
        drive : :obj: 'Class'
            Object of vendor class.
        Returns:
            Optional[int]: Drive up time in seconds. If the drive does not support
            vendor specific timestamp, None is returned.
        """
        try:
            out = drive.get_vs_timestamp()
            # Continue if NotImplementedError not raised
            seconds = float(out)
            years = seconds / (3600 * 24 * 365.0)
            try:
                time = str(datetime.timedelta(seconds=seconds))
            except Exception:
                time = "%s years" % years
            self.log_info(f"Drive up time {drive}: {time}")
            return out
        except NotImplementedError as exc:
            self.log_info(exc)
        except Exception as exc:
            raise TestError(
                "get_vs_timestamp failed for drive {}: {}".format(drive, str(exc)),
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

    def _validate_power_mode(self, drive) -> dict:
        """
        This method checks for the npss (Number of Power State Support)
        of the data drive. Current M.2 data SSD's have npss 0 or 1. For
        npss more than 1 and for the data drive capacity 2TB or 4TB the
        required power mode is set to reduce the power consumption by
        nvme and validates by get power mode.

        Args:
            drive: The NVMe drive object.
        Returns:
            The npss and power_modes of the drive as a dict.
        """
        npss = NVMeUtils.get_id_ctrl(self.host, drive.block_name)["npss"]
        output = {"npss": npss}
        if npss <= 1:
            AutovalLog.log_info(f"/dev/{drive} supported only one power-mode")
            return output
        power_modes = drive.get_drive_supported_power_modes()
        output["power_modes"] = power_modes
        for power_mode in power_modes:
            set_state = drive.set_power_mode(power_mode)
            get_state = drive.get_power_mode()
            AutovalUtils.validate_equal(
                get_state,
                set_state,
                f"Correct power-mode set on /dev/{drive}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
                raise_on_fail=False,
            )
        # Reverting the power state to 0
        set_state = drive.set_power_mode(0)
        get_state = drive.get_power_mode()
        AutovalUtils.validate_equal(
            set_state, get_state, f"Resetting power-mode PS0 on /dev/{drive} "
        )
        return output

    def _check_oacs_device_self_test(self, drive: NVMeDrive) -> Optional[dict]:
        """Validate Device self-test command support
        Method checks for  OACS field from id-ctrl and validates Device self-test command support

        Args:
            drive: The NVMe drive object.
        Returns:
            The oacs value of the drive as a dict.
        """
        oacs = NVMeUtils.get_id_ctrl(self.host, drive.block_name)["oacs"]
        self.log_info(f"Test to Check dev_self_test management {oacs} {hex(oacs)}")
        support_dev_self_test_management = oacs & 0x8
        AutovalUtils.validate_condition(
            support_dev_self_test_management == 0x8,
            f"Check dev_self_test management support SELF_TEST supported on /dev/{drive}",
            warning=True,
            log_on_pass=True,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        if support_dev_self_test_management == 0x0:
            AutovalLog.log_info(f"/dev/{drive} does not support self-test")
            return
        return oacs

    def _validate_capacity(self, drive: NVMeDrive) -> Optional[dict]:
        """Validate drive capacity
        Method checks for unvmcap and tnvmcap from id-ctrl and validates drive capacity

        Args:
            drive: The NVMe drive object.
        Returns:
            The oacs, tnvmcap and nsze values of the drive as a dict.
        """
        if str(drive) == self.boot_drive:
            # namespace_management not supported on boot drive`
            return
        oacs = NVMeUtils.get_id_ctrl(self.host, drive.block_name)["oacs"]
        support_namespace_management = oacs & 0x8
        AutovalUtils.validate_condition(
            support_namespace_management and 0x8,
            f"Check namespace management support on /dev/{drive}",
            warning=True,
            log_on_pass=True,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        if support_namespace_management == 0x0:
            return
        tnvmcap = NVMeUtils.get_id_ctrl(self.host, drive.block_name)["tnvmcap"]
        nsze = NVMeUtils.get_id_ns(self.host, drive.block_name)["nsze"]
        # Compare size
        AutovalUtils.validate_greater_equal(
            tnvmcap,
            nsze,
            f"Compare Total capacity tnvmcap and nsze on /dev/{drive}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        return {
            "oacs": oacs,
            "tnvmcap": tnvmcap,
            "nsze": nsze,
        }

    def validate_fdp(self) -> None:
        """
        Validates FDP support and performs setup and cleanup on single drive.
        """
        test_drives = [
            drive for drive in self.test_drives if drive.block_name != self.boot_drive
        ][:1]
        nvme_id_ctrls = NvmeResizeUtil.get_nvme_ctrls(
            self.host, test_drives, nvme_id_ctrl_filter="True"
        )
        # pyrefly: ignore [bad-argument-type]
        FDPUtils.validate_fdp_support(self.host, nvme_id_ctrls)
        # pyrefly: ignore [bad-argument-type]
        FDPUtils.fdp_setup(self.host, nvme_id_ctrls)
        AutovalLog.log_info("FDP setup completed")

        # pyrefly: ignore [bad-argument-type]
        FDPUtils.fdp_cleanup(self.host, nvme_id_ctrls)
        AutovalLog.log_info("FDP cleanup completed")

    def validate_latency_monitor(self) -> None:
        """
        Enables latency monitor, run the workload and validate the bucke counter on single drive.
        """
        nvme_version = NVMeUtils.get_nvme_version(self.host)
        if not NVMeUtils.compare_versions("2.9.0", nvme_version):
            self.log_info(
                "Skipping latency monitor test. Nvme version 2.9 or higher required for ocp lacteny monitor cmds"
            )
            return

        FioSynthFlashUtils.tool_setup(self.host)
        test_drives = [
            drive for drive in self.test_drives if drive.block_name != self.boot_drive
        ][:1]
        self.test_control["max_latency_lm_validation"] = True
        self.test_control["ocp_lm_commands"] = True
        workload = "Nvme_Cli_Wkld"
        work_dir = self.dut_logdir[self.host.hostname]
        self.latency_monitor = LatencyMonitor(
            host=self.host,
            test_drives=test_drives,
            test_control=self.test_control,
        )
        lm_enabled_drives = self.latency_monitor.enable(
            workload=workload, working_directory=work_dir
        )
        self.log_info(f"Running the {workload} Workload.")
        # Generate the run folder locations
        run_folder = f"test_{workload}"
        # Run synthflash
        for drive in test_drives:
            result_folder = f"{run_folder}_{drive.block_name}_results"
            device = f"/dev/{drive.block_name}"
            # Run workload
            cmd = f"cd {work_dir} && fiosynth -d {device} -w {workload} -f {result_folder} -n 1 -g y --lm"
            self.log_info(f"Starting command: {cmd}")
            # pyrefly: ignore [missing-attribute]
            self.host.run_get_result(cmd, timeout=70500)

        self.latency_monitor.collect_logs(workload, work_dir)
        self.latency_monitor.parse_and_validate_results(
            synth_workload_result_dir=work_dir,
            lm_enabled_drives=lm_enabled_drives,
        )
        self.latency_monitor.disable(working_directory=work_dir)

    def compare_command_outputs(
        self,
        first_nvme_version: str,
        first_nvme_version_outputs: list[dict],
        new_nvme_version: str,
        new_nvme_version_outputs: list[dict],
    ) -> None:
        """
        Compares the outputs of the commands that were saved for each nvme-cli version.
        Only the outputs of commands run on the last drive are compared.
        Cmds outputs with difference are saved to the results directory.

        Args:
            first_nvme_version: The first nvme-cli version to compare.
            first_nvme_version_outputs: The outputs of the commands for the first nvme-cli version.
            new_nvme_version: The new nvme-cli version to compare.
            new_nvme_version_outputs: The outputs of the commands for the new nvme-cli version.
        """
        self.log_info(
            f"Comparing the output of commands for the nvme-cli versions {first_nvme_version} and {new_nvme_version}"
        )
        output_str = (
            f"NVMe-CLI Version Comparison: {first_nvme_version} vs {new_nvme_version}\n"
        )
        output_str += "=" * 80 + "\n\n"

        for i in range(len(first_nvme_version_outputs[-1])):
            first_nvme_version_output = first_nvme_version_outputs[-1][i]
            new_nvme_version_output = new_nvme_version_outputs[-1][i]
            if (
                first_nvme_version_output["method_name"]
                != new_nvme_version_output["method_name"]
            ):
                self.log_warning(
                    f"Output comparison failed due to method name mismatch: {first_nvme_version_output['method_name']} != {new_nvme_version_output['method_name']}"
                )
                continue

            output_str += self._compare_and_format_output(
                first_nvme_version,
                first_nvme_version_output,
                new_nvme_version,
                new_nvme_version_output,
            )
        _result_dir = SiteUtils.get_resultsdir()
        dest_file_path = os.path.join(_result_dir, "nvme_cli_version_comparison.log")
        AutovalLog.log_info(f"Saving nvme comparison log to: {dest_file_path}")
        FileActions.write_data(dest_file_path, output_str, append=True)

    def _compare_and_format_output(
        self,
        first_nvme_version: str,
        first_nvme_version_output: Any,
        new_nvme_version: str,
        new_nvme_version_output: Any,
    ) -> str:
        """
        Compares two command outputs and formats the differences if any.

        Args:
            first_nvme_version: The first nvme-cli version.
            first_nvme_version_output: The output dict of the first command.
            new_nvme_version: The new nvme-cli version.
            new_nvme_version_output: The output dict of the new command.

        Returns:
            A formatted string containing the comparison results.
        """
        DeepDiff = importlib.import_module("deepdiff").DeepDiff
        output_str = ""
        first_output = first_nvme_version_output["output"]
        new_output = new_nvme_version_output["output"]
        diff = DeepDiff(
            first_output,
            new_output,
            verbose_level=1,
            ignore_order=True,
            ignore_numeric_type_changes=True,
        )

        if diff:
            filtered_diff = "\n".join(diff.keys())
            AutovalLog.log_warning(
                f"Output differs between {first_nvme_version} and {new_nvme_version} for {first_nvme_version_output['method_name']}: {filtered_diff}"
            )
            output_str += f"Method: {first_nvme_version_output['method_name']}\n"
            output_str += "-" * 40 + "\n"
            output_str += f"Original Output ({first_nvme_version}):\n"
            output_str += f"{pformat(first_output, width=80, indent=2)}\n\n"
            output_str += f"New Output ({new_nvme_version}):\n"
            output_str += f"{pformat(new_output, width=80, indent=2)}\n\n"
            output_str += "Differences:\n"
            output_str += f"{pformat(diff, width=80, indent=2)}\n"
            output_str += "\n" + "=" * 40 + "\n\n"
        else:
            AutovalLog.log_info(
                f"No output difference between {first_nvme_version} and {new_nvme_version} for {first_nvme_version_output['method_name']}"
            )
        return output_str

    def cleanup(self, *args, **kwargs) -> None:
        super().cleanup(*args, **kwargs)
