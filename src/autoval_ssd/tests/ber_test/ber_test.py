#!/usr/bin/env python3

# pyre-unsafe
import json
import math
import os
import time

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalLog, AutovalUtils
from autoval.lib.utils.file_actions import FileActions

from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase
from autoval_ssd.lib.utils.switchtec_utils import SwitchtecUtils


class BerTest(StorageTestBase):
    """
    Bit Error Rate test used to check PCIe link integrity. We use 90,000 seconds
    by default, but this can be changed in the control file.

    Parameters for this test are:

    'workload': The location of the fio job file in GlusterFS.
    'nvme_devices': The number of NVMe devices that must be tested.  Usually
        there are 30 devices (twice the number of x4 downlinks).
    'runtime': fio job runtime in seconds
    'nvme_delay': delay between NVMe smart log requests.  Do not change from
        the default without a good reason.
    'switchtec_delay': delay between SEL log requests.  Do not change from
        the default without a good reason.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.nvme_delay = self.test_control.get("nvme_delay", 120)
        self.run_definition = self.test_control.get("run_definition", None)
        self.runtime = self.test_control.get("runtime", 900)
        self.switchtec_delay = self.test_control.get("switchtec_delay", 72)
        self.switchtec_devices = []
        self.fio_runner = None

    def get_test_params(self) -> str:
        params = "Fio-Job Runtime: {}, Switchtec-delay: {}, " "Nvme-delay: {},".format(
            self.runtime, self.switchtec_delay, self.nvme_delay
        )
        return params

    def storage_test_setup(self) -> None:
        self.storage_test_tools.extend(["switchtec"])
        super().storage_test_setup()

    def smart_refresh_count_value(self, drive):
        smart_log = drive.get_smart_log()
        try:
            vs_smart_log = smart_log["vs-smart-add-log"]
            vs_smart_log = {
                "".join(c.lower() for c in key if c.isalnum()): val
                for key, val in vs_smart_log.items()
            }
            for key, val in vs_smart_log.items():
                if "refreshcount" in key:
                    return val
        except KeyError as keyerr:
            AutovalLog.log_info(f"Couldn't find Key - {keyerr}")

    def execute(self) -> None:
        # Get vs smart attribute value for refresh count
        self.log_info("Getting refresh count value before test.")
        refresh_count_before = {}  # noqa
        for drive in self.test_drives:
            refresh_count_value = self.smart_refresh_count_value(drive)
            if refresh_count_value:  # noqa
                refresh_count_before[drive] = refresh_count_value

        self.switchtec_devices = SwitchtecUtils().get_switchtec_devices(self.host)
        length = len(self.switchtec_devices)
        if length:
            self.log_info(
                "Found %s switchtec devices: %s" % (length, self.switchtec_devices)
            )
            for device in self.switchtec_devices:
                self.log_info("Running on device /dev/%s" % device)
                self._execute_test(switchtec_device=device)
        else:
            self.log_info("switchtec device not found")
            self._execute_test(switchtec_device=None)

        # get refresh Count after the test execution
        self.log_info("Getting refresh count value after test.")

        for drive in self.test_drives:
            refresh_count_after_value = self.smart_refresh_count_value(drive)
            if refresh_count_after_value:  # noqa
                self.validate_equal(
                    refresh_count_after_value,
                    refresh_count_before[drive],
                    "Validation of refresh count after and before execution of the"
                    "BER test of drive %s" % (drive),
                    warning=True,
                    raise_on_fail=False,
                    component=COMPONENT.STORAGE_DRIVE,  # comment
                    error_type=ErrorType.DRIVE_ERR,
                )

    def _execute_test(self, switchtec_device=None) -> None:
        ber_threads = []
        # collect NVMe-smart Log periodically
        ber_threads.append(
            AutovalThread.start_autoval_thread(
                self.gen_nvme_smart_log, self.runtime, self.nvme_delay
            )
        )

        # collect switchtec logs periodically
        if switchtec_device is not None:
            ber_threads.append(
                AutovalThread.start_autoval_thread(
                    self.sel_psxapp,
                    switchtec_device,
                    self.runtime,
                    self.switchtec_delay,
                )
            )
        # Run Fio job
        ber_threads.append(AutovalThread.start_autoval_thread(self.run_fio_job))
        # check for bit errors in NVMe smart-log
        AutovalThread.wait_for_autoval_thread(ber_threads)
        self.check_for_bit_errors()

    def gen_nvme_smart_log(self, runtime, nvme_delay) -> None:
        """Periodically collect NVMe smart log data. Arguments:
        Args:
            runtime (int or str): run time in seconds
            nvme_delay (int): delay between log operations"""
        self.log_info("Collecting NVMe smart logs.")
        nvme_dev_cnt = len(self.test_drives)
        cycles = int(
            math.ceil(int(runtime) / (int(nvme_delay) + 0.1 * int(nvme_dev_cnt)))
        )
        # make sure at least two log files are always collected
        # even in short test runs
        if cycles < 2:
            cycles = 2
        self.log_info("Target to run %s cycles of save_drive_logs" % cycles)
        for i in range(1, 1 + cycles):
            self.log_info("Running %s cycle of save_drive_logs" % i)
            self.save_drive_logs_async(self.test_drives)
            time.sleep(nvme_delay)
            self.log_info("NVMe smart logging completed successfully.")

    def run_fio_job(self) -> None:
        self.log_info("starting FIO Job.")
        if self.test_drives:
            self.test_control["drives"] = self.test_drives
        if self.boot_drive:
            self.test_control["boot_drive"] = self.boot_drive
        self.fio_runner = FioRunner(self.host, self.test_control)
        self.validate_no_exception(
            self.fio_runner.test_setup,
            [],
            "Fio setup()",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )
        self.validate_no_exception(
            self.fio_runner.start_test,
            [],
            "Fio run()",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

    def sel_psxapp(self, device, runtime, switchtec_delay) -> None:
        """Periodically gather switchtec event logs.
        Args:
            device: switchtec_device
            runtime (int or str): run time in seconds
            switchtec_delay: delay between log operations"""
        cycles = int(math.floor(int(runtime) / float(switchtec_delay)))
        self.log_info("Target to run %s cycles of get_switchtec_event_counter" % cycles)
        past_counter = {}
        for i in range(1, 1 + cycles):
            self.log_info("Running %s cycle of get_switchtec_event_counter" % i)
            counter = SwitchtecUtils().get_switchtec_event_counter(self.host, device)
            if past_counter and counter:
                diff = AutovalUtils.compare_configs(past_counter, counter)
                AutovalUtils.validate_empty_diff(
                    diff,
                    "Check switchtec_events between cycles",
                )
            past_counter = counter
            time.sleep(switchtec_delay)
        self.log_info("SEL and sensor data gathered successfully.")

    def check_for_bit_errors(self) -> None:
        """Check for bit errors in an I/O test.  This function looks
        through the files in the NVMe log directory to find the first and last
        log files.  Then the error counts in the initial and final logs are
        compared.  If they are different, then an error must have occurred
        at some point during the test.

        Args:
            nvmelogdir: location of log files to review
        """
        nvme_logdir = os.path.join(self.resultsdir, "SMART")
        nvme_logs = FileActions.ls(nvme_logdir)
        nvme_logs.sort()
        nvme_start_logdir = nvme_logs[0]
        nvme_end_logdir = nvme_logs[-1]
        self.log_info("Checking the error bit in SMART log")
        num_err_log_entries_before = []
        num_err_log_entries_after = []
        for drive in self.test_drives:
            drive_log = drive.serial_number + ".json"
            log_start = os.path.join(nvme_logdir, nvme_start_logdir, drive_log)
            log_end = os.path.join(nvme_logdir, nvme_end_logdir, drive_log)
            # get the smart log lines showing:
            # media_errors (line 14) and num_err_log_entries (line 15)
            error_lines_start = self._check_log(log_start)
            num_err_log_entries_before.append(error_lines_start[1])
            error_lines_end = self._check_log(log_end)
            num_err_log_entries_after.append(error_lines_end[1])
            # 1 error is acceptable
            self.validate_greater_equal(
                1,
                error_lines_end[0] - error_lines_start[0],
                "%s: Check for media errors before-after test" % drive.serial_number,
                raise_on_fail=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
            self.validate_greater_equal(
                error_lines_end[1],
                error_lines_start[1],
                "%s: Check for num_err_log_entries before-after test"
                % drive.serial_number,
                raise_on_fail=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
            self.validate_greater_equal(
                1,
                error_lines_end[2] - error_lines_start[2],
                "%s: Check for critical_warning before-after test"
                % drive.serial_number,
                raise_on_fail=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
        # Check difference is the same on all drives for num_err_log_entries
        diff = []
        for i in range(len(num_err_log_entries_before)):
            diff.append(num_err_log_entries_after[i] - num_err_log_entries_before[i])
        self.validate_equal(
            len(set(diff)),
            1,
            "Check for num_err_log_entries for all drives",
            raise_on_fail=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def _check_log(self, log):
        error_lines = []
        with FileActions.file_open(log, "r") as fin:
            data = json.load(fin)
            error_lines.append(data["SMART"]["smart-log"]["media_errors"])
            error_lines.append(data["SMART"]["smart-log"]["num_err_log_entries"])
            error_lines.append(data["SMART"]["smart-log"]["critical_warning"])
        return error_lines

    def cleanup(self, *args, **kwargs) -> None:
        try:
            if self.fio_runner:
                self.fio_runner.test_cleanup()
        finally:
            super().cleanup(*args, **kwargs)

