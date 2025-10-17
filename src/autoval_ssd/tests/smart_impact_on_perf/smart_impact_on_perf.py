#!/usr/bin/env python3

# pyre-unsafe
import time
from pprint import pformat
from typing import Any, Dict

from autoval.lib.host.component.component import COMPONENT

from autoval.lib.test_utils.bg_runner import BgRunner
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_log import AutovalLog
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase


class DrivePerformanceImpact(StorageTestBase):
    """
    This script is used to validate the performace on the HDD/SSD.
    First the FIO write process is started and then when the FIO read is started
    the smart commands/nvme commands are run in the interval of
    1sec, 5sec, 1 min, 15min and 60 mins in the background.
    """

    def __init__(self, *args, **kwargs) -> None:
        """
        This method initializes the basic configuration for logging
        information, load and store the input details gathered from
        input/control(json) file.
        """
        super().__init__(*args, **kwargs)
        self.time_interval = self.test_control.get("time_interval", [60])
        self.performance_check = self.test_control.get(
            "performance_check",
            {
                "name": "nvme_command",
                "args": {"commands": "nvme_commands"},
                "interval": 1,
            },
        )
        self.precondition_loops = self.test_control.get("precondition_loops", 2)
        self.precondition_template = self.test_control.get(
            "precondition_template", "precondition.fio"
        )
        self.collect_telemetry_log = self.test_control.get(
            "collect_telemetry_log", False
        )
        self.bg_tests_obj = []

    def setup(self, *args, **kwargs) -> None:
        # self.storage_test_tools.extend(["fiosynth"])
        super().setup(*args, **kwargs)

        # Setup fio
        if self.test_drives:
            self.test_control["drives"] = self.test_drives
        if self.boot_drive:
            self.test_control["boot_drive"] = self.boot_drive
        self.fio = FioRunner(self.host, self.test_control)
        self.validate_no_exception(
            self.fio.test_setup,
            [],
            "Fio setup()",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

    def execute(self) -> None:
        """
        Test Flow:
        If collect_telemetry_log is true:
        1. Run the 'prep_flash.fio' job as a precondition
        2. Run the 'gen_randrw_70_30.fio' job as the main FIO job
        3. Run the main FIO workload 3 times:
           - First run: without background operations to collect telemetry
           - Second and third runs: collect telemetry while running the FIO job

        Otherwise:
        1.Start the bg runner operation in a loop for each time interval where the
          smart commands/nvme commands are started in the background.
        2.Start the FIO process.
        3.Once the FIO is completed,get the fio result
         and stop the bg runner process.
        """
        self.final_result = {}
        if self.collect_telemetry_log:
            self.run_telemetry_impact_on_perf()
        else:
            self.run_nvme_impact_on_perf()

    def run_telemetry_impact_on_perf(self) -> None:
        """
        1. Run the 'prep_flash.fio' job as a precondition
        2. Run the 'gen_randrw_70_30.fio' job as the main FIO job
        3. Run the main FIO workload 3 times:
           - First run: without background operations to collect telemetry
           - Second and third runs: collect telemetry while running the FIO job
        """
        # Run the prep_flash.fio job as precondition
        precondition_drives = self.fio.get_precondition_drives()
        if precondition_drives:
            self.fio.precondition_drives(
                drives=precondition_drives,
                precondition_loops=self.precondition_loops,
                precondition_template="prep_flash.fio",
                remote=False,
                precondition_params={
                    "BLKSIZE": "512K",
                    "DEPTH": "256",
                    "LOOPS": "1",
                },
            )
        self.ramptime = int(
            self.test_control.get("run_definition", {})
            .get("randrw", {})
            .get("args", {})
            .get("RAMPTIME", 0)
        )
        # Run the main FIO workload 3 times
        for run_count in range(3):
            interval = self.time_interval[0]
            # First run: without background operations
            if run_count == 0:
                fio_output = self.run_fio(self.fio)
            # Second and third runs: with background operations
            else:
                commands = self.performance_check["args"]["commands"]
                self.start_bg_operations(interval, sleep_time=True)
                AutovalLog.log_info(f"Running {commands} every {interval} seconds")
                fio_output = self.run_fio(self.fio)
                self.stop_bg_operations()
            # Checking if all drives are available
            self.check_block_devices_available()
            if fio_output:
                self.parse_fio_results(fio_output, interval, run_count)
        # pyre-fixme[61]: `fio_output` is undefined, or not always defined.
        if fio_output:
            AutovalLog.log_debug("Displaying FIO Metrics")
            AutovalLog.log_debug(pformat(self.final_result))
            self.check_errors()
            self.compare_results()
            self.compare_max_latency()

    def run_nvme_impact_on_perf(self) -> None:
        """
        1.Start the bg runner operation in a loop for each time interval where the
          smart commands/nvme commands are started in the background.
        2.Start the FIO process.
        3.Once the FIO is completed,get the fio result
         and stop the bg runner process.
        """
        max_time = max(self.time_interval)
        self.test_control["run_definition"]["randrw"]["args"]["RUNTIME"] = max_time
        fio = FioRunner(self.host, self.test_control)
        precondition_drives = fio.get_precondition_drives()
        if precondition_drives:
            fio.precondition_drives(
                drives=precondition_drives,
                precondition_loops=self.precondition_loops,
                precondition_template=self.precondition_template,
                remote=False,
            )
        commands = self.performance_check["args"]["commands"]
        for interval in self.time_interval:
            self.start_bg_operations(interval, sleep_time=False)
            AutovalLog.log_info(f"Running {commands} every {interval} seconds")
            fio_output = self.run_fio(fio)
            # Checking if all drives are available
            self.check_block_devices_available()
            if fio_output:
                self.parse_fio_results(fio_output, interval)
            self.stop_bg_operations()
        # pyre-fixme[61]: `fio_output` is undefined, or not always defined.
        if fio_output:
            AutovalLog.log_debug("Displaying FIO Metrics")
            AutovalLog.log_debug(pformat(self.final_result))
            self.check_errors()
            self.compare_results()

    def parse_fio_results(self, fio_output, time_interval, run_count=None) -> None:
        """
        This function will get the fio result after each fio read for each
        time interval of the smart command run and stored in the metrics
        dictionary.

        Parameters
        ----------
        fio_output: String
           fio output result
        time_interval: integer
           interval time to run smart commands
        run_count: integer, optional
           iteration number for telemetry impact tests
        """
        if self.collect_telemetry_log:
            self.final_result[f"iter{run_count}_{time_interval}sec"] = fio_output[
                "result"
            ]
        else:
            self.final_result[str(time_interval) + "sec"] = fio_output["result"]

    def start_bg_operations(self, time_interval, sleep_time: bool) -> None:
        """
        This function will start the smart command run in the background
        using the bg runner.

        Parameters
        ----------
        time_interval: integer
          time when to run the bg runner.
        """
        if sleep_time:
            AutovalLog.log_info(time.time())
            time.sleep(self.ramptime)
            AutovalLog.log_info(f"Sleeping for {self.ramptime} seconds")
        else:
            pass

        self.performance_check["args"]["enable_async_log_storing"] = False
        time_update = self.test_control.get("performance_check", self.performance_check)
        time_update["interval"] = time_interval
        _obg_ref = BgRunner(self.host, time_update)
        self.bg_tests_obj.append(_obg_ref)
        _obg_ref.start_bg_runner()

    def stop_bg_operations(self) -> None:
        """
        This function will stop the bg runner.
        """
        for obj in self.bg_tests_obj:
            obj.stop_bg_runner()
        for obj in self.bg_tests_obj:
            obj.wait_for_bg_runner_to_stop()

    def run_fio(self, fio):
        """
        FIO Job of the smart impact on performance of drives.
        This method executes the FIO start test method where the
        FIO process is started(creationg FIO job to scheduling
        it on the DUT.)

        Parameters
        ----------
        fio: FIO runner: object

        Returns
        -------
        out: fio output result: String
        """
        try:
            fio.start_test()
            out = fio.parse_results()
            return out
        except Exception as e:
            AutovalLog.log_info("Exception while running FIO: %s" % e)
            self.stop_bg_operations()

    def check_errors(self) -> None:
        """
        Go through each key in dictionary and find if there are any errors.
        If there is error, raise TestError for reporting.
        """
        combined_err = ""
        for key, value in self.final_result.items():
            if isinstance(value, list):
                for item in value:
                    if "error" in item and item["error"] != 0:
                        combined_err += "\n".join(str({key: item}))
        self.validate_condition(
            combined_err == "",
            "Fio job has warnigns or errors: %s" % combined_err,
            log_on_pass=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

    def compare_results(self) -> None:
        """
        Compare IOPS between time_intervals
        """
        read = {}
        write = {}
        for key, value in self.final_result.items():
            if isinstance(value, list):
                for item in value:
                    if "read_iops" in item:
                        if item["opt_filename"] in read:
                            read[item["opt_filename"]].update({key: item["read_iops"]})
                        else:
                            read[item["opt_filename"]] = {}
                            read[item["opt_filename"]].update({key: item["read_iops"]})
                    if "write_iops" in item:
                        if item["opt_filename"] in write:
                            write[item["opt_filename"]].update(
                                {key: item["write_iops"]}
                            )
                        else:
                            write[item["opt_filename"]] = {}
                            write[item["opt_filename"]].update(
                                {key: item["write_iops"]}
                            )
        self.validate_condition(
            len(read),
            "Read IOPS: %s" % read,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        self.validate_condition(
            len(write),
            "Write IOPS: %s" % write,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def compare_max_latency(self) -> None:
        """
        Compare max read and write latency between iterations 1 and 2, 1 and 3
        Validate that there is no more than 100ns difference
        """
        keys = list(self.final_result.keys())
        # Getting baseline results for iteration 0
        baseline_key = keys[0]
        baseline_results = self.final_result.get(baseline_key, [])
        baseline_metrics = {}
        for item in baseline_results:
            if isinstance(item, dict) and "opt_filename" in item:
                filename = item["opt_filename"]
                baseline_metrics[filename] = {
                    "read_max": item.get("read_max_lat", {}),
                    "write_max": item.get("write_max_lat", {}),
                }

        for iter_num in [1, 2]:
            telemetry_key = keys[iter_num]
            telemetry_results = self.final_result.get(telemetry_key, [])
            telemetry_metrics = {}
            AutovalLog.log_info(
                f"Comparing latency for Baseline fio without telemetry collection and Iteration {iter_num} fio job with telemtry collection"
            )
            for item in telemetry_results:
                if isinstance(item, dict) and "opt_filename" in item:
                    filename = item["opt_filename"]
                    telemetry_metrics[filename] = {
                        "read_max": item.get("read_max_lat", {}),
                        "write_max": item.get("write_max_lat", {}),
                    }
                    self.validate_latency_difference(
                        filename,
                        baseline_metrics,
                        telemetry_metrics,
                        "READ",
                    )
                    self.validate_latency_difference(
                        filename,
                        baseline_metrics,
                        telemetry_metrics,
                        "WRITE",
                    )

    def validate_latency_difference(
        self,
        filename: str,
        baseline_metrics: Dict[str, Any],
        telemetry_metrics: Dict[str, Any],
        latency_type: str,
    ) -> None:
        """
        Validates the latency difference between baseline and telemetry latency.
        Args:
            filename : Name of the Drive
            baseline_metrics : A Dictionary which contains the read and write max latency for each drives without bg operations
            telemetry_metrics : A Dictionary which contains the read and write max latency for each drives with bg operations
            latency_type : Type of latency to validate either Read or Write.
        Returns:
            None
        """
        baseline_latency = round(
            int(baseline_metrics[filename][f"{latency_type.lower()}_max"]) / 1000000, 2
        )
        telemetry_latency = round(
            int(telemetry_metrics[filename][f"{latency_type.lower()}_max"]) / 1000000, 2
        )
        AutovalLog.log_info(
            f"""Filename: {filename}
            Baseline {latency_type} latency max value: {baseline_latency}ms,
            Telemetry {latency_type} latency max value: {telemetry_latency}ms"""
        )
        latency_difference = round(telemetry_latency - baseline_latency, 2)
        self.validate_condition(
            latency_difference < 100,
            f"{latency_type} latency difference is: {latency_difference} ms < 100ms",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
            raise_on_fail=False,
        )

    def cleanup(self, *args, **kwargs) -> None:
        self.fio.test_cleanup()
        return super().cleanup(*args, **kwargs)
