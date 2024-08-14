#!/usr/bin/env python3

# pyre-unsafe
"""FioSynthFlash test runs Synthetics workloads on HDD and SSD drives"""
import re
from typing import Dict, List

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.file_actions import FileActions

from autoval_ssd.lib.utils.fio.fio_synth_flash_utils import FioSynthFlashUtils
from autoval_ssd.lib.utils.storage.nvme.latency_monitor_utils import LatencyMonitor
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase
from autoval_ssd.lib.utils.storage.storage_utils import StorageUtils

PERFORMANCE_METRICS = {
    "RandomRead": ["Read_IOPS"],
    "RandomWrite": ["Write_IOPS"],
    "SeqRead": ["Read_BW"],
    "SeqWrite": ["Write_BW"],
    "70_30": ["Read_IOPS", "Write_IOPS"],
}

FIO_SYNTH_FLASH_WORKLOAD_SUITES = "/usr/local/fb-FioSynthFlash/wkldsuites/%s"
FIO_SYNTH_FLASH_WORKLOAD_SUITES_BACKUP: str = (
    FIO_SYNTH_FLASH_WORKLOAD_SUITES + ".backup"
)

OCP_2_6_WORKLOADS = [
    "USSDT_Workload_loop_OCP2.6",
    "HE_Flash_Short_wTRIM_1H22",
]


class FioSynthFlash(StorageTestBase):
    """
    Perform fio_synth workload on the entire capacity of each
    drive. If drive_filter is mentioned, do either HDD only or all drives.
    """

    def __init__(self, *args, **kwargs) -> None:
        """
        Attributes Setup Information
        @att synth_options         : additional fiosynth option to go on command.
        @att workload              : which type of workload for fiosynthflash.
        @att fio_synth_params      : the parameters for fio_synth-flash
        @att synth_result_dir      : the result directory for fiosynthflash
        @att formatted_test_result : the test_result formatted output
        @att ocp_lm_commands       : enable/disable use of ocp lm commands

        """
        super().__init__(*args, **kwargs)
        self.workload = self.test_control["workload"]
        self.fio_synth_params = self.test_control.get("fio_synth_params", {})
        self.raid = self.fio_synth_params.get("raid", None)
        self.synth_options = self.fio_synth_params.get("synth_options", None)
        self.synth_result_dir = None
        self.test_results = []
        self.formatted_test_result = {"hdd": {}, "ssd": {}}
        self.format_drives = self.test_control.get("format_drives", None)
        self.ignore_error = self.fio_synth_params.get("ignore_error", False)
        self.in_parallel = self.fio_synth_params.get("parallel", False)
        self.synth_verify = self.fio_synth_params.get("synth_verify", False)
        self.skip_latency_monitor = self.test_control.get("skip_latency_monitor", True)
        self.latency_monitor = None

    def get_test_params(self) -> str:
        params = "raid {} test_drive_filter {} synth_options {}".format(
            self.raid, self.test_drive_filter, self.synth_options
        )
        return params

    def remove_string_run_from_key(self, key: str) -> str:
        """remove string from key"""
        temp_key = re.sub(r"_run\d+", "", key)
        return temp_key

    def check_relevant(self, key) -> bool:
        """Chedck if key is relevant to test"""
        lowered_key = {k.lower(): v.lower() for k, v in key.items() if v}
        for filtered_key in PERFORMANCE_METRICS:
            if (filtered_key.lower() in lowered_key) and (
                any(
                    each_op in lowered_key
                    for each_op in [
                        w.lower() for w in PERFORMANCE_METRICS[filtered_key]
                    ]
                )
            ):
                return True
        return False

    def filter_data(self, data) -> Dict:
        """
        Filter out the only data it needs for test_result.json.
        Here, we are also removing the string "run1".

        @param data: This data is already formatted as dictionary.
            Please use output of load_csvfile function first.

        Sample Input:
        {
            "RandomRead_QD001_run1:Read_IOPS" : 15.10783, <-- Relevant
            "RandomRead_QD001_run1:Mean_Read_Latency" : 15.10783, <-- Not Relevant
            ...
        }
        Sample Output:
        {
            "RandomRead_QD001:Read_IOPS" : 15.10783,
            ...
        }
        """
        filtered_data = {}
        for key in data:
            if self.check_relevant(key):
                filtered_key = self.remove_string_run_from_key(key)
                filtered_data[filtered_key] = data[key]
        return filtered_data

    def convert_test_result_format(self, data, time) -> List:
        """
        convert the dictionary into test_result format.

        @param data: the dictionary data from output in load_csvfile function
        @param time: the time stamp

        output will be a list of lists where
        [
            [
                "RandomRead_QD001:Read_IOPS" : 15.10783,
                "0.0",
                1573701165.2449567
            ],
            ...
        ]
        """
        result = []
        for key in data:
            temp_list = [key, data[key], time]
            result.append(temp_list)
        return result

    def run_fiosynth_parser(self, file_path: str, drive_serial_num, time) -> Dict:
        """
        parent function of formatting the csvfile to dictionary and into
        test_control format. Return the formatted dictionary data.

        @param file_path: csvfile result path
        @param drive_serial_num: drive serial number
        @param time: time stamp
        """
        final_format = {}
        data = FileActions.read_data(file_path, csv_file=True, host=self.host)
        data = self.filter_data(data)
        final_format[drive_serial_num] = self.convert_test_result_format(data, time)
        return final_format

    def collect_drive_performance_data(self, data) -> None:
        """
        Summary:
            Collect performance data given from the fio_synth resultfiles.
            Format/Parse them into test_result format and update to
            formatted_test_result.

        Step 1: Run run-fiosynth_parser which collects the data from csv
                to json and format it into test_result format.
        Step 2: Depending on the drive_type, update the formatted data
                into self.formatted_test_result variable.

        @param data:
            The format of this data is list. In each item of the list,
            we expect to have a tuple of
            (drive_object, filepath, and timestamp, command)

            if it was not ran in parallel, then the tuple must be
            (filepath, timestamp, command); thus, checking if it ran in
            parallel so that it can repopulate the drive.
        """
        temp_data = []
        AutovalLog.log_info("[FioSynthFlash Log] Collecting drive performance data")
        if not self.in_parallel:
            for csv_filepath, current_time, cmd, error in data:
                for drive in self.test_drives:
                    temp_data.append((drive, csv_filepath, current_time, cmd, error))
        else:
            temp_data = data
        for drive, csv_filepath, current_time, _cmd, _error in temp_data:
            fio_synth_test_result_data = self.run_fiosynth_parser(
                file_path=csv_filepath,
                drive_serial_num=drive.serial_number,
                time=current_time,
            )
            drive_type = drive.get_type().value
            self.formatted_test_result[drive_type].update(fio_synth_test_result_data)
        AutovalLog.log_info(
            "[FioSynthFlash Log] Collected all the data from csvfiles successfully."
        )
        self.test_results = temp_data

    def check_errors(self) -> None:
        """
        Summary:
            The data already contains a list of error file directories in
            each tuple of list.
            Go through each error list and find if there are any errors.
            If there is error, raise TestError for reporting.
        """
        for drive, _csv_filepath, _current_time, _cmd, error in self.test_results:
            if error:
                combined_err = "\n".join(error)
                raise TestError(
                    "Fio job at %s has warnigns or errors.\n "
                    "Please check these json files:\n %s"
                    % (drive.block_name, combined_err),
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.TOOL_ERR,
                )

    # Override
    def setup(self, *args, **kwargs) -> None:
        StorageUtils.change_nvme_io_timeout(
            host=self.host, test_phase="setup()", new_timeout=8
        )
        self.storage_test_tools.extend(["fiosynth"])
        super().setup(*args, **kwargs)
        self.synth_result_dir = FioSynthFlashUtils.setup_synth_resultdir(
            self.host, self.dut_logdir[self.host.hostname]
        )

    def execute(self) -> None:
        """
        Step 1: Execute each workload and store the result into
                self.fiosynth_results
        Step 2: Visit each csvfiles and collect the performance data
                in test_results format and store it into dictionary
                called self.formatted_test_result
        Step 3: Update the self.formatted_test_result dictionary
                into the result_handler.
        """
        # Hosts should not have a mix of OCP2.6 and non-OCP2.6 drives
        has_ocp_2_6_drives = False
        has_non_ocp_2_6_drives = False
        for drive in self.test_drives:
            if hasattr(drive, "is_ocp_2_6_drive"):
                if drive.is_ocp_2_6_drive():
                    has_ocp_2_6_drives = True
                else:
                    has_non_ocp_2_6_drives = True
                if has_ocp_2_6_drives and has_non_ocp_2_6_drives:
                    raise TestError(
                        "Both OCP2.6 and non-OCP2.6 drives are available on the host",
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.DRIVE_ERR,
                    )
        # Workload should match drive in terms of OCP2.6 vs non-OCP2.6
        for workload in self.workload:
            if workload in OCP_2_6_WORKLOADS:
                if has_non_ocp_2_6_drives:
                    raise TestError(
                        "Running OCP2.6 workload on non-OCP2.6 drives",
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.DRIVE_ERR,
                    )
            else:
                if has_ocp_2_6_drives:
                    raise TestError(
                        "Running non-OCP2.6 workload on OCP2.6 drives",
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.DRIVE_ERR,
                    )
        if self.synth_verify and (not self.in_parallel):
            msg = f"Current setting synth_verify={self.synth_verify},"
            msg += f" parallel={self.in_parallel}"
            raise TestError(
                f"synth verify is only supported with fiosynth parallel run, {msg}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )
        if self.format_drives:
            StorageUtils.format_all_drives(self.test_drives)

        # backup workload loop stress json for restore at test end.
        for workload_type in self.workload:
            if not FileActions.exists(
                f"{FIO_SYNTH_FLASH_WORKLOAD_SUITES_BACKUP}" % (workload_type),
                host=self.host,
            ):
                FileActions.copy(
                    f"{FIO_SYNTH_FLASH_WORKLOAD_SUITES}" % (workload_type),
                    f"{FIO_SYNTH_FLASH_WORKLOAD_SUITES_BACKUP}" % (workload_type),
                    overwrite=True,
                    host=self.host,
                )
        if not self.skip_latency_monitor:
            self.latency_monitor = LatencyMonitor(
                host=self.host,
                test_drives=self.test_drives,
                test_control=self.test_control,
            )
        # Run FioSynthFlash
        lm_enabled_drives: List[str] = []
        for workload_type in self.workload:
            if not self.has_workload_precondition(workload_type):
                AutovalLog.log_info(f"Skipping {workload_type} precondition test ...")
                continue
            AutovalLog.log_info(f"Starting {workload_type} precondition test ...")
            # prepare workload precondition.
            (
                workload_name,
                synth_precond_result_dir,
            ) = self.prepare_workload_precondition(workload_type)
            if self.latency_monitor:
                lm_enabled_drives = self.latency_monitor.enable(
                    workload=workload_type, working_directory=self.synth_result_dir
                )
            test_result = FioSynthFlashUtils.start_fio_synth_flash(
                host=self.host,
                workload=workload_type,
                resultsdir=synth_precond_result_dir,
                options=self.fio_synth_params,
                test_drive_filter=self.test_drive_filter,
                test_drives=self.test_drives,
                ignore_error=self.ignore_error,
                lm_enabled_drives=lm_enabled_drives,
            )
            if lm_enabled_drives and self.latency_monitor:
                self.latency_monitor.collect_logs(
                    workload=workload_type,
                    synth_workload_result_dir=synth_precond_result_dir,
                )

                self.latency_monitor.parse_and_validate_results(
                    synth_workload_result_dir=synth_precond_result_dir,
                    lm_enabled_drives=lm_enabled_drives,
                )
                self.latency_monitor.disable(working_directory=self.synth_result_dir)
            self.collect_drive_performance_data(test_result)
        self.result_handler.add_test_results(self.formatted_test_result)
        self.check_errors()

        # Run FioSynthFlash workload loop stress test
        for workload_type in self.workload:
            AutovalLog.log_info(f"Starting {workload_type} work load stress test ...")
            # copy workload stress json file.
            (
                workload_name,
                synth_workload_result_dir,
            ) = self.prepare_workload_stress(workload_type)
            if not self.skip_latency_monitor:
                lm_enabled_drives = self.latency_monitor.enable(
                    workload=workload_type, working_directory=self.synth_result_dir
                )
            test_result = FioSynthFlashUtils.start_fio_synth_flash(
                host=self.host,
                workload=workload_type,
                resultsdir=synth_workload_result_dir,
                options=self.fio_synth_params,
                test_drive_filter=self.test_drive_filter,
                test_drives=self.test_drives,
                ignore_error=self.ignore_error,
                lm_enabled_drives=lm_enabled_drives,
            )
            if lm_enabled_drives and self.latency_monitor:
                self.latency_monitor.collect_logs(
                    workload=workload_type,
                    synth_workload_result_dir=synth_workload_result_dir,
                )
                self.latency_monitor.parse_and_validate_results(
                    synth_workload_result_dir=synth_workload_result_dir,
                    lm_enabled_drives=lm_enabled_drives,
                )
                self.latency_monitor.disable(
                    working_directory=self.synth_result_dir,
                )
            self.collect_drive_performance_data(test_result)

        self.result_handler.add_test_results(self.formatted_test_result)
        self.check_errors()

    def has_workload_precondition(self, workload_type) -> bool:
        """Checks if workload has precondition job"""
        workload_type_json_data = FileActions().read_data(
            f"{FIO_SYNTH_FLASH_WORKLOAD_SUITES}" % (workload_type),
            json_file=True,
            host=self.host,
        )
        if (
            workload_type_json_data.get("pre", None)
            and workload_type_json_data["precondition_cycles"] > 0
        ):
            return True
        return False

    def prepare_workload_precondition(self, workload_type):
        """Run nvme drives precondition job"""
        workload_name = f"{workload_type}_precond"
        synth_precond_result_dir = f"{self.synth_result_dir}/{workload_name}/"
        FileActions().mkdirs(synth_precond_result_dir, host=self.host)

        workload_type_backup_json_data = FileActions().read_data(
            f"{FIO_SYNTH_FLASH_WORKLOAD_SUITES_BACKUP}" % (workload_type),
            json_file=True,
            host=self.host,
        )
        # remove workload loop stress test details from json and overwrite to workload json
        workload_type_backup_json_data["def"] = []
        FileActions().write_data(
            f"{FIO_SYNTH_FLASH_WORKLOAD_SUITES}" % (workload_type),
            workload_type_backup_json_data,
            host=self.host,
        )
        return (workload_name, synth_precond_result_dir)

    def prepare_workload_stress(self, workload_type):
        """Run workload stress job"""
        workload_name = f"{workload_type}_stress_test"
        synth_workload_result_dir = f"{self.synth_result_dir}/{workload_name}/"
        FileActions().mkdirs(synth_workload_result_dir, host=self.host)
        workload_type_json_data = FileActions().read_data(
            f"{FIO_SYNTH_FLASH_WORKLOAD_SUITES_BACKUP}" % (workload_type),
            json_file=True,
            host=self.host,
        )
        # remove workload loop precondition details from json
        workload_type_json_data.pop("pre", None)
        workload_type_json_data["precondition_cycles"] = 0
        workload_type_json_data.pop("precondition_first_cycle_only", None)
        FileActions().write_data(
            f"{FIO_SYNTH_FLASH_WORKLOAD_SUITES}" % (workload_type),
            workload_type_json_data,
            host=self.host,
        )
        return (workload_name, synth_workload_result_dir)

    # Override
    def cleanup(self, *args, **kwargs) -> None:
        try:
            AutovalLog.log_info("[FioSynthFlash Log] Restoring workload json file.")
            for workload_type in self.workload:
                # restore workload loop json file
                FileActions.move(
                    f"{FIO_SYNTH_FLASH_WORKLOAD_SUITES_BACKUP}" % workload_type,
                    f"{FIO_SYNTH_FLASH_WORKLOAD_SUITES}" % workload_type,
                    host=self.host,
                )
                if self.latency_monitor:
                    self.latency_monitor.disable(
                        working_directory=self.synth_result_dir,
                    )
        except Exception as exe:
            AutovalLog.log_info(
                f"[FioSynthFlash Log] workload json file restore failed: {str(exe)}"
            )
        finally:
            StorageUtils.change_nvme_io_timeout(
                host=self.host, test_phase="cleanup()", new_timeout=30
            )
            super().cleanup(*args, **kwargs)
