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

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval_ssd.lib.utils.drive_monitor_utils import DriveMonitorUtils
from autoval_ssd.lib.utils.filesystem_utils import FilesystemUtils
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase


class FioFb(StorageTestBase):
    """
    FioFb uses the Fio tool which is a public domain tool for testing drives and
    NVME's. This test validates performance by stressing the drives by creating
    and running the fio jobs.
    """

    def __init__(self, *args: tuple[object, ...], **kwargs: dict[str, object]) -> None:
        super().__init__(*args, **kwargs)

        self.enable_periodic_drive_monitor = self.test_control.get(
            "enable_periodic_drive_monitor", False
        )
        self.end_of_test = None
        self.skip_clean_filesystem = self.test_control.get(
            "skip_clean_filesystem", False
        )

    def setup(self, *args, **kwargs) -> None:
        super().setup(*args, **kwargs)
        if self.enable_periodic_drive_monitor:
            self.interval = self.test_control.get(
                "periodic_drive_monitor_interval", None
            )
            only_sideband_cmds = self.test_control.get("only_sideband_cmds", False)
            self.end_of_test = Event()
            self.monitor_thread = AutovalThread.start_autoval_thread(
                DriveMonitorUtils.start_periodic_drive_monitor,
                host=self.host,
                test_drives=self.test_drives,
                end_of_test=self.end_of_test,
                periodic_drive_monitor_interval=self.interval,
                only_sideband_cmds=only_sideband_cmds,
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
        if self.enable_periodic_drive_monitor and self.end_of_test:
            self.end_of_test.set()
            AutovalThread.wait_for_autoval_thread([self.monitor_thread])
        # Cleanup all drives except boot drive
        if not self.skip_clean_filesystem:
            drives = [d for d in self.test_drives if str(d) != str(self.boot_drive)]
            for device in drives:
                mnt = f"/mnt/fio_test_{device.block_name}"
                AutovalUtils.validate_no_exception(
                    FilesystemUtils.clean_filesystem,
                    [self.host, device.block_name, mnt],
                    "Clean drive %s" % device,
                    raise_on_fail=False,
                    log_on_pass=False,
                    component=COMPONENT.SYSTEM,
                    error_type=ErrorType.DRIVE_ERR,
                )
        super().cleanup()

    def get_test_params(self) -> str:
        params = ""
        run_definitions = self.test_control.get("run_definition", {})
        FioRunner.check_run_definition_format(run_definitions)
        for job, job_def in run_definitions.items():
            args = pformat(job_def.get("args"))
            template = job_def.get("template")
            params += (
                f"Fio job: {job}. Fio template: {template} \nTemplate arguments: {args}"
            )
        return params
