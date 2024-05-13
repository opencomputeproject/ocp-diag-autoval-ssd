# Copyright (c) 2016-present, Facebook, Inc.
# All rights reserved.
#
# Description     : This test validates the performance of drive using fio job.
# TestCase IDs    : USSDT_009
# ==============================================================================
#!/usr/bin/env python3

# pyre-unsafe
from pprint import pformat
from threading import Event
from time import sleep

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import CmdError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalUtils

from autoval_ssd.lib.utils.filesystem_utils import FilesystemUtils
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.sed_util import SedUtils
from autoval_ssd.lib.utils.storage.nvme.nvme_drive import NVMeDrive
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase


class FioFb(StorageTestBase):
    """
    FioFb uses the Fio tool which is a public domain tool for testing drives and
    NVME's. This test validates performance by stressing the drives by creating
    and running the fio jobs.
    """

    def setup(self, *args, **kwargs) -> None:
        super().setup(*args, **kwargs)
        self.enable_periodic_drive_monitor = self.test_control.get(
            "enable_periodic_drive_monitor", False
        )
        if self.enable_periodic_drive_monitor:
            self.end_of_test = Event()
            self.monitor_thread = AutovalThread.start_autoval_thread(
                self.start_periodic_drive_monitor,
                end_of_test=self.end_of_test,
            )

    def execute(self) -> None:
        """Executes FIO job.

        This method installs, creates and runs the fio job on the DUT.

        Raises
        ------
        TestStepError
            - When fails to install FIO rpm.
            - When fails to start, run and save results for FIO run.
        """
        if self.test_drives:
            self.test_control["drives"] = self.test_drives
        if self.boot_drive:
            self.test_control["boot_drive"] = self.boot_drive
        fio_runner = FioRunner(self.host, self.test_control)
        self.validate_no_exception(
            fio_runner.test_setup,
            [],
            "Fio setup()",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )
        fio_runner.start_test()
        self.validate_no_exception(
            fio_runner.test_cleanup,
            [],
            "Fio cleanup()",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

    # pyre-fixme[14]: `cleanup` overrides method defined in `StorageTestBase`
    #  inconsistently.
    def cleanup(self) -> None:
        """Cleanup for FioFb.

        This method erase the filesystem from the device,
        which was created to run fio jobs and raise exception for any errors.
        Also collects and saves the DUT and OpenBMC Configurations and compares
        between the pre and post test configurations, and saves the test
        result and command metrics information.

        Raises
        ------
        TestStepError
            - When failes to erase filesystem.
            - When fails to collect the logs from DUT/OpenBMC.

        """
        if self.enable_periodic_drive_monitor:
            self.end_of_test.set()
            AutovalThread.wait_for_autoval_thread([self.monitor_thread])
        # Cleanup all drives except boot drive
        drives = [d for d in self.test_drives if str(d) != str(self.boot_drive)]
        # Exclude emmc as well
        drives = [d for d in drives if str(d) != "mmcblk0"]
        for device in drives:
            mnt = "/mnt/fio_test_%s" % device.block_name
            AutovalUtils.validate_no_exception(
                FilesystemUtils.clean_filesystem,
                [self.host, device.block_name, mnt],
                "Clean drive %s" % device,
                raise_on_fail=False,
                log_on_pass=False,
                component=COMPONENT.SYSTEM,
                error_type=ErrorType.DRIVE_ERR,
            )
        super(FioFb, self).cleanup()

    def get_test_params(self) -> str:
        params = ""
        run_definitions = self.test_control.get("run_definition", {})
        FioRunner.check_run_definition_format(run_definitions)
        for job, job_def in run_definitions.items():
            args = pformat(job_def.get("args"))
            template = job_def.get("template")
            params += (
                f"Fio job: {job}. Fio template: {template} \n"
                f"Template arguments: {args}"
            )
        return params

    def is_enclosure_util_supported(self) -> bool:
        """
        Checks if the enclosure utility is supported on the host.
        Args:
            None
        Returns:
            True if the enclosure utility is supported, False otherwise.
        Raises:
            CmdError: If there is an unexpected error running the command.
        """
        slot_info = self.host.oob.get_slot_info()
        cmd = f"enclosure-util {slot_info} --drive-status all"
        try:
            self.host.oob.bmc_host.run(cmd)
        except CmdError as e:
            if "Please check the board config" in str(e) or "command not found" in str(
                e
            ):
                return False
            raise
        return True

    def start_periodic_drive_monitor(self, end_of_test: Event) -> None:
        """
        Start periodic drive monitoring
        """
        MAX_PERIODIC_DRIVE_MONITOR_DURATION = 10 * 3600
        DEFAULT_INTERVAL_SECONDS = 15 * 60
        remaining_duration = MAX_PERIODIC_DRIVE_MONITOR_DURATION
        interval = self.test_control.get(
            "periodic_drive_monitor_interval", DEFAULT_INTERVAL_SECONDS
        )
        AutovalLog.log_info(
            f"Starting periodic drive monitoring with {interval}s interval"
        )
        opal2_0_drives, _ = SedUtils.opal_support_scan(self.host)
        AutovalLog.log_info(f"Opal2 supported drives: {opal2_0_drives}")
        is_enclosure_util_supported = self.is_enclosure_util_supported()
        try:
            self.host.oob.bmc_host.run("which enclosure-util")
            is_enclosure_util_supported = True
        except CmdError:
            AutovalLog.log_info("enclosure-util not installed on BMC")

        while remaining_duration > 0 and not end_of_test.is_set():
            if is_enclosure_util_supported:
                AutovalUtils.validate_no_exception(
                    self.host.oob.bmc_host.run,
                    [
                        f"enclosure-util {self.host.oob.get_slot_info()} --drive-status all"
                    ],
                    f"[Periodic Drive Monitoring][{self.host.oob.get_slot_info()}] Assert no enclosure-util cmd exception",
                    raise_on_fail=False,
                    log_on_pass=False,
                )
            AutovalUtils.validate_no_exception(
                self.host.oob.bmc_host.run,
                [f"sensor-util {self.host.oob.get_slot_info()}"],
                f"[Periodic Drive Monitoring][{self.host.oob.get_slot_info()}] Assert no sensor-util cmd exception",
                raise_on_fail=False,
                log_on_pass=False,
            )
            for drive in self.test_drives:
                if isinstance(drive, NVMeDrive):
                    AutovalUtils.validate_no_exception(
                        drive.get_smart_log,
                        [],
                        f"[Periodic Drive Monitoring][{drive.block_name}] Assert no nvme smart-log cmd exception",
                        raise_on_fail=False,
                        log_on_pass=False,
                    )

                    if drive.block_name in opal2_0_drives:
                        AutovalUtils.validate_no_exception(
                            self.host.run,
                            [
                                f"nvme security-recv -p 0x1 -s 0x1 -t 256 -x 256 /dev/{drive.block_name}"
                            ],
                            f"[Periodic Drive Monitoring][{drive.block_name}] Assert no nvme security-recv cmd exception",
                            raise_on_fail=False,
                            log_on_pass=False,
                        )

            for _ in range(interval):
                if end_of_test.is_set():
                    break
                sleep(1)
                remaining_duration -= 1
        AutovalLog.log_info("End of periodic drive monitoring")
