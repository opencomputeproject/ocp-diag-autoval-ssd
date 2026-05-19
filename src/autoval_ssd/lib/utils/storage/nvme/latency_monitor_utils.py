# (c) Meta Platforms, Inc. and affiliates. Confidential and proprietary.

# pyre-unsafe
import json
import os
import re
from datetime import datetime
from typing import Any, Optional, Union

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.file_actions import FileActions
from autoval.lib.utils.site_utils import SiteUtils
from autoval.lib.utils.uperf_test_util import ThresholdConfig
from autoval_ssd.lib.utils.fio.fio_synth_flash_utils import FioSynthFlashUtils
from autoval_ssd.lib.utils.storage.nvme.lmparser import LatencyMonitorLogParser
from autoval_ssd.lib.utils.storage.nvme.nvme_drive import NVMeDrive

LM_FIELDS_TO_VALIDATE_Hi5 = [
    "Active Bucket Counter: Bucket 0",
    "Active Bucket Counter: Bucket 1",
    "Active Bucket Counter: Bucket 2",
    "Active Bucket Counter: Bucket 3",
]

LM_FIELDS_TO_VALIDATE_DC = [
    "Active Bucket Counter: Bucket 2",
    "Active Bucket Counter: Bucket 3",
]

LM_FIELDS_TO_VALIDATE_IOGO = [
    "Active Bucket Counter: Bucket 1",
    "Active Bucket Counter: Bucket 2",
    "Active Bucket Counter: Bucket 3",
]

LM_FIELDS_TO_VALIDATE_UPQT = ["Active Bucket Counter: Bucket 3"]

LM_FIELDS_TO_VALIDATE_MAX_LATENCY = ["Active Bucket Counter: Bucket 0"]

MIN_LM_LOG_PAGE_VERSION = 1


class LatencyMonitor:
    """
    Latency Monitor Utility class
    """

    def __init__(
        self,
        host: "Host",
        test_drives: list,
        test_control: dict,
        log_lm_commands: bool = True,
    ) -> None:
        """Initialize the Latency Monitor Utility class"""
        self.host = host
        self.test_drives = test_drives
        self.test_control = test_control
        self.log_lm_commands = log_lm_commands
        self.latency_outliers: dict[str, dict[str, int]] = {}

        self.lmparser = LatencyMonitorLogParser()
        self.dc_lm_validation = self.test_control.get("dc_lm_validation", False)
        self.ocp_lm_commands = self.test_control.get("ocp_lm_commands", False)
        self.upqt_lm_validation = self.test_control.get("upqt_lm_validation", False)
        self.max_latency_lm_validation = self.test_control.get(
            "max_latency_lm_validation", False
        )
        self.latency_monitor_config: dict[str, Any] = {"latency_monitor": []}
        json_path = "/cfg/drive_latency_monitor.json"
        try:
            abs_path = NVMeDrive.get_target_path()
            latency_monitor_config_path = abs_path + json_path
            with open(latency_monitor_config_path) as f:
                data = f.read()
                if data.strip() == "{}":  # check if file contains only {}
                    raise ValueError("Latency monitor json file is empty")
                self.latency_monitor_config = json.loads(data)
        except (FileNotFoundError, ValueError) as e:
            if not self.ocp_lm_commands:
                raise TestError(
                    message=f"{e}This test requires either test control parameter 'ocp_lm_commands: True' or drive_latency_monitor.json file to be present and populated with valid data.",
                    error_type=ErrorType.INPUT_ERR,
                )

    def get_namespace_controller(self, drive_namespace_name: str) -> str:
        """This method is used to replace the namespace in the drive name with the controller name
        Args:
            drive (str): The drive name(namespace).
        Returns:
            str: The edited drive name(controller).
        Example: nvme1n1 -> nvme1"""

        pattern = r"nvme(\d+)[a-z](\d+).*"
        replacement = r"nvme\1"
        return re.sub(pattern, replacement, drive_namespace_name)

    def get_lm_log_page_version(self, drive) -> int:
        """
        Get the LM log page 0xC3 version from the drive.

        Args:
            drive: The drive object to check.

        Returns:
            The log page version number
            Returns 0 if the log page is not supported or cannot be read.
        """
        device_name = self.get_namespace_controller(str(drive))

        if self.ocp_lm_commands:
            cmd = f"nvme ocp latency-monitor-log /dev/{device_name} -o json"
            result = self.host.run_get_result(cmd, ignore_status=True)

            if result.return_code == 0:
                try:
                    lm_data = json.loads(result.stdout)
                    return int(lm_data.get("Log Page Version", 0))
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass

        cmd = f"nvme get-log /dev/{device_name} -i 0xc3 -l 512"
        result = self.host.run_get_result(cmd, ignore_status=True)

        if result.return_code == 0:
            # Parse the hex dump output using lmparser
            byteregex = r"(?<!\S)[0-9a-fA-F]{2}(?!\S)"
            bytelist = re.findall(byteregex, result.stdout)
            if len(bytelist) >= 496:
                output_dict = self.lmparser.extract_json_output(
                    self.lmparser.OCP2_SCHEMA, bytelist
                )
                log_page_version = output_dict.get("Log Page Version")
                if log_page_version is not None and isinstance(log_page_version, int):
                    return log_page_version

        return 0

    def validate_lm_log_page_version(self, drive) -> bool:
        """
        Check if the drive supports LM log page 0xC3 with version >= MIN_LM_LOG_PAGE_VERSION.

        Args:
            drive: The drive object to check.

        Returns:
            True if the drive supports latency monitoring, False otherwise.
        """
        version = self.get_lm_log_page_version(drive)
        supported = version >= MIN_LM_LOG_PAGE_VERSION
        if self.log_lm_commands:
            AutovalLog.log_info(
                f"[{drive}]: LM log page version={version}, LM supported={supported}"
            )
        return supported

    def enable(self, workload: str, working_directory: str) -> list[str]:
        """
        This method is used to enable latency monitoring on the test drives for the specified workload
        Args:
            workload (str): The workload type.
            working_directory (str): The working directory.
        Returns:
            List[str]: A list of enabled drives.
        """
        lm_enabled_drives = []
        lm_flags = ""

        if self.ocp_lm_commands:
            try:
                threshold_obj_dict = ThresholdConfig().get_threshold(
                    filepath="autoval/thresholds/latency_monitor",
                    user_metric_list=[
                        "bucket_timer",
                        "bucket_a",
                        "bucket_b",
                        "bucket_c",
                        "bucket_d",
                    ],
                    user_criteria={
                        "workload": [workload],
                    },
                )
            except Exception:
                AutovalLog.log_info(
                    f"Latency monitor thresholds not found - skipping latency monitor for {workload}."
                )
                return lm_enabled_drives

            if threshold_obj_dict:
                t = threshold_obj_dict["bucket_timer"].value
                a = threshold_obj_dict["bucket_a"].value
                b = threshold_obj_dict["bucket_b"].value
                c = threshold_obj_dict["bucket_c"].value
                d = threshold_obj_dict["bucket_d"].value
                lm_flags = (
                    f"-t {t} -a {a} -b {b} -c {c} -d {d} -f 0 -w 0 -r 0 -l 0 -e 1"
                )

        for drive in self.test_drives:
            device_name = self.get_namespace_controller(str(drive))
            if self.ocp_lm_commands and lm_flags != "":
                ocp_lm_enable_cmd = f"nvme ocp set-latency-monitor-feature /dev/{device_name} {lm_flags}"
                out = self.host.run_get_result(  # noqa
                    cmd=ocp_lm_enable_cmd,
                    working_directory=working_directory,
                    ignore_status=True,
                )

                if out.return_code == 0:
                    if self.log_lm_commands:
                        AutovalLog.log_info(
                            f"LM enabled for drive {device_name} with cmd nvme ocp set-latency-monitor-feature"
                        )
                    if drive.is_lmparser_ocp_2_0_drive():
                        lm_enabled_drives.append(str(drive))
                    continue

            for lm_info in self.latency_monitor_config["latency_monitor"]:
                if drive.model in lm_info["supported_drive_models"]:
                    local_path = ""
                    if (
                        "latency_monitor_setting" in lm_info
                        and workload in lm_info["latency_monitor_setting"]
                    ):
                        local_path = FileActions.get_local_path(
                            self.host,
                            os.path.join(
                                SiteUtils.get_tool_path(),
                                lm_info["latency_monitor_setting"][workload],
                            ),
                        )
                        # Set appropriate setting to measure latency.
                        lm_set_cmd = self.latency_monitor_config[
                            "latency_monitor_pretest_cmd"
                        ]
                        cmd = lm_set_cmd.replace("DRIVE", device_name).replace(
                            "LM_SETTING", local_path
                        )
                        self.host.run(  # noqa
                            cmd=cmd, working_directory=working_directory
                        )
                        if self.log_lm_commands:
                            AutovalLog.log_info(
                                f"LM enabled for drive {device_name} with cmd {cmd}"
                            )
                        if drive.is_lmparser_ocp_2_0_drive():
                            lm_enabled_drives.append(str(drive))
        return lm_enabled_drives

    def collect_logs(
        self,
        workload: str,
        synth_workload_result_dir: str,
        block_size: str = "",
    ) -> None:
        """
        This method is used to collect latency montitor logs after the test.
        Args:
            workload (str): The workload type.
            synth_workload_result_dir (str): The directory containing the workload results.
            block_size (str): The block size. Default is an empty string.
        Returns:
            None
        """
        current_timestamp = str(datetime.now()).replace(" ", "_")
        for drive in self.test_drives:
            device_name = self.get_namespace_controller(str(drive))
            block_size = f"_{block_size}" if block_size else ""
            result_filename = f"{str(drive)}_{drive.serial_number}_{current_timestamp}_{workload}{block_size}_lm_log.txt"
            if self.ocp_lm_commands:
                ocp_lm_log_cmd = f"nvme ocp latency-monitor-log /dev/{device_name} -o json | tee {result_filename}"
                ocp_log_out = self.host.run_get_result(  # noqa
                    cmd=ocp_lm_log_cmd,
                    working_directory=synth_workload_result_dir,
                    ignore_status=True,
                )

                if ocp_log_out.return_code == 0:
                    if self.log_lm_commands:
                        AutovalLog.log_info(
                            f"LM collection for drive {device_name} with cmd nvme ocp latency-monitor-log"
                        )
                    continue

            for lm_info in self.latency_monitor_config["latency_monitor"]:
                if (
                    drive.model in lm_info["supported_drive_models"]
                    and workload in lm_info["latency_monitor_setting"]
                ):
                    lm_set_cmd = self.latency_monitor_config[
                        "latency_monitor_posttest_cmd"
                    ]
                    cmd = lm_set_cmd.replace("DRIVE", device_name).replace(
                        "RESULT_FILENAME", result_filename
                    )
                    self.host.run(  # noqa
                        cmd=cmd, working_directory=synth_workload_result_dir
                    )
                    if self.log_lm_commands:
                        AutovalLog.log_info(
                            f"LM collection for drive {drive} with cmd {cmd}"
                        )

    def disable(self, working_directory: str) -> None:
        """
        Disable latency monitor will disable latency monitor
        after completion of workload and latency log collection.
        This is not supported by all drives so it will run only on
        supported drive models.
        Args:
            working_directory: working directory to run the command
        Returns:
            None
        """
        for drive in self.test_drives:
            device_name = self.get_namespace_controller(str(drive))
            if self.ocp_lm_commands:
                ocp_lm_disable_cmd = f"nvme ocp set-latency-monitor-feature /dev/{device_name} -t 0 -a 0 -b 0 -c 0 -d 0 -f 0 -w 0 -r 0 -l 0 -e 0"

                out = self.host.run_get_result(  # noqa
                    ocp_lm_disable_cmd,
                    working_directory=working_directory,
                    ignore_status=True,
                )

                if out.return_code == 0:
                    if self.log_lm_commands:
                        AutovalLog.log_info(
                            f"LM disabled for drive {device_name} with cmd nvme ocp set-latency-monitor-feature"
                        )
                    continue

            for lm_info in self.latency_monitor_config["latency_monitor"]:
                if drive.model in lm_info["supported_drive_models"]:
                    local_path = ""
                    if (
                        "latency_monitor_disable_setting" in lm_info
                        and lm_info["latency_monitor_disable_setting"]
                    ):
                        local_path = FileActions.get_local_path(
                            self.host,
                            os.path.join(
                                SiteUtils.get_tool_path(),
                                lm_info["latency_monitor_disable_setting"],
                            ),
                        )
                    if "latency_monitor_disable_cmd" in lm_info:
                        # Disable latency monitor after log collection if supported.
                        for lm_disable_cmd in lm_info["latency_monitor_disable_cmd"]:
                            cmd = lm_disable_cmd.replace("DRIVE", device_name).replace(
                                "LM_DISABLE_SETTING", local_path
                            )
                            self.host.run(  # noqa
                                cmd, working_directory=working_directory
                            )
                            if self.log_lm_commands:
                                AutovalLog.log_info(
                                    f"LM disabled for drive {device_name} with cmd {cmd}"
                                )

    def parse_and_validate_results(
        self,
        synth_workload_result_dir: str,
        lm_enabled_drives: Optional[list[str]] = None,
        workload: str = "",
    ) -> None:
        """
        This method is used to get a text file from the synth_workload_result_dir,
        then parse the text file using the lmparse module to get a human-readable JSON file
        then convert that JSON file to a dict.
        Args:
            synth_workload_result_dir (str): The directory containing the workload results.
            lm_enabled_drives (Optional[List[str]]): The list of drives enabled for latency monitoring. Default is None.
            workload (str): The workload type. Default is an empty string.
        Returns:
            None
        Raises:
            TestError: If the block size is not specified in the file name for ioT6 workload.
        """
        validated_logs: list = []
        if lm_enabled_drives is None:
            lm_enabled_drives = []

        result_file_extension = ".log" if self.upqt_lm_validation else ".txt"

        text_path = FioSynthFlashUtils.find_file_paths(
            self.host, synth_workload_result_dir, file_extension=result_file_extension
        )
        for path in text_path:
            if path in validated_logs:
                continue
            for drive in lm_enabled_drives:
                if drive in path:
                    if self.upqt_lm_validation and "lm_after" not in path:
                        continue
                    result_file = path.replace("lm", "lmparser")
                    validated_logs.extend([path, result_file])
                    file = FileActions.read_data(path, host=self.host)
                    if self.ocp_lm_commands or self.upqt_lm_validation:
                        output_dict = json.loads(file)
                    else:
                        byteregex = r"(?<!\S)[0-9a-fA-F]{2}(?!\S)"
                        bytelist = re.findall(byteregex, file)

                        output_text = self.lmparser.extract_humanreadable_output(
                            self.lmparser.OCP2_SCHEMA, bytelist
                        )
                        FileActions.write_data(
                            path=result_file, contents=output_text, host=self.host
                        )
                        output_dict = self.lmparser.extract_json_output(
                            self.lmparser.OCP2_SCHEMA, bytelist
                        )
                    if workload == "ioT6":
                        match = re.search(r"\d+MB", path)
                        if match:
                            block_size = match.group()
                        else:
                            raise TestError(
                                "Block size should be specified in file name for ioT6 workload"
                            )
                        self.validate_results(
                            output_dict,
                            drive,
                            LM_FIELDS_TO_VALIDATE_IOGO,
                            workload,
                            block_size,
                        )
                    elif self.dc_lm_validation:
                        self.validate_results(
                            output_dict, drive, LM_FIELDS_TO_VALIDATE_DC
                        )
                    elif self.upqt_lm_validation:
                        self.validate_results(
                            output_dict, drive, LM_FIELDS_TO_VALIDATE_UPQT
                        )
                    elif self.max_latency_lm_validation:
                        self.validate_max_latency_results(
                            output_dict,
                            drive,
                            LM_FIELDS_TO_VALIDATE_MAX_LATENCY,
                        )
                    else:
                        self.validate_results(
                            output_dict, drive, LM_FIELDS_TO_VALIDATE_Hi5
                        )
                    break
        if workload == "ioT6":
            self.validate_iogo_10ms_results()

    def validate_results(
        self,
        output_dict: Union[dict[str, dict[str, int]], Any],
        drive: str,
        lm_field_to_validate: list[str],
        workload: str = "",
        block_size: str = "",
    ) -> None:
        """
        This method validates the lmparser output values.
        Args:
            output_dict (Dict): The dictionary containing the lmparser output values.
            drive (str): The drive name.
            lm_field_to_validate (List[str]): The list of fields to be validated.
            workload (str): The workload type. Default is an empty string.
            block_size (str): The block size. Default is an empty string.
        Returns:
            None
        Raises:
            TestError: If the specified key is not present in the lmparser output.
        """
        for output in lm_field_to_validate:
            if output in output_dict:
                if workload == "ioT6" and "Bucket 1" in output:
                    for key, value in output_dict[output].items():
                        if value != 0:
                            self.latency_outliers.setdefault(f"{drive}_{key}", {})[
                                block_size
                            ] = value
                else:
                    block_size_info = (
                        f" (block size: {block_size})" if block_size else ""
                    )
                    AutovalLog.log_info(
                        f"[{drive}]: lmparser Verification output {output}{block_size_info}"
                    )
                    for key, value in output_dict[output].items():
                        AutovalUtils.validate_equal(
                            value,
                            0,
                            msg=f"[{drive}]: {key}_Latency_Parser_value",
                            raise_on_fail=False,
                            component=COMPONENT.STORAGE_DRIVE,
                            error_type=ErrorType.LATENCY_ERR,
                        )
            else:
                raise TestError(f"The {output} key is not present in lmparser output")

    def validate_iogo_10ms_results(
        self,
    ) -> None:
        """
        This method validates the IOGO 10ms results by checking for latency outliers in the drives.
        Raises:
            ValidationError: If there are any drives with latency outliers exceeding 10ms for four or more file sizes.
        """
        drives_with_latency_outliers = []
        for key, value in self.latency_outliers.items():
            drive, op = key.split("_")
            if len(value) > 3:
                AutovalLog.log_info(
                    f"[Latency Monitor] Four or more file sizes with [{op} latency] exceeding 10ms in device [{drive}]\n File sizes with Outliers:{value}"
                )
                if drive not in drives_with_latency_outliers:
                    drives_with_latency_outliers.append(drive)
        AutovalUtils.validate_empty_list(
            drives_with_latency_outliers,
            msg=f"[Latency Monitor] Drives with latency outliers exceeding 10ms for four or more file sizes: {drives_with_latency_outliers}",
            raise_on_fail=True,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.LATENCY_ERR,
        )

    def validate_max_latency_results(
        self,
        output_dict: dict[str, dict[str, int]],
        drive: str,
        lm_field_to_validate: list[str],
    ) -> None:
        """
        This method validates the lmparser output values for Max Latency Workload.
        Args:
            output_dict: The dictionary containing the lmparser output values.
            drive: The drive name.
            lm_field_to_validate: The list of fields to be validated.
        Returns:
            None
        Raises:
            TestError: If the specified key is not present in the lmparser output.
        """
        for output in lm_field_to_validate:
            if output in output_dict:
                AutovalLog.log_info(f"[{drive}]: lmparser Verification output {output}")
                for key, value in output_dict[output].items():
                    if key == "Read":
                        AutovalUtils.validate_greater(
                            value,
                            0,
                            msg="[%s]: %s_Latency_Parser_value" % (drive, key),
                            raise_on_fail=False,
                            component=COMPONENT.STORAGE_DRIVE,
                            error_type=ErrorType.LATENCY_ERR,
                        )
            else:
                raise TestError(f"The {output} key is not present in lmparser output")
