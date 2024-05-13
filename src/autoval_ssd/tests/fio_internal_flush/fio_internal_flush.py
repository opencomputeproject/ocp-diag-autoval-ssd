#!/usr/bin/env python3
# Copyright (c) 2016-present, Facebook, Inc.
# All rights reserved.
#
# Description     : The test will verify the NVMe drives IO performance with
#                   fio and following power cycle conditions
#                       1. Flush
#                       2. Shutdown (without Flush)
#                       3. Dirty power-off!
# TestCase IDs    :
# =============================================================================

# pyre-unsafe
from autoval.lib.host.component.component import COMPONENT
from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval_ssd.lib.utils.filesystem_utils import FilesystemUtils
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase

MOUNT_PATH = "/mnt/fio_test_%s/"


class FioInternalFlush(StorageTestBase):
    """The test will verify the NVMe drives IO performance with
    fio and following power cycle conditions:
        1. Flush
        2. Shutdown (without Flush)
        3. Dirty power-off!
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initializes the FIO Internal Flush Test.

        This method initializes the basic configuration for logging
        information, load and store the input details gathered from
        input/control file.
        """
        super().__init__(*args, **kwargs)
        self.cycle_type = self.test_control.get("cycle_type", "warm")
        self.iteration_count = self.test_control.get("iteration_count", 1)
        self.power_trigger = self.test_control.get("power_trigger", False)
        self.nvme_flush = self.test_control.get("nvme_flush", False)
        self.workloads = self.test_control["workloads"]
        self.parallel_mode = self.test_control.get("parallel_mode", True)
        self.fio_timeout = self.test_control.get("fio_timeout", 36000)
        self.filesystem = self.test_control.get("filesystem", False)

    # pyre-fixme[14]: `setup` overrides method defined in `StorageTestBase`
    #  inconsistently.
    def setup(self) -> None:
        super().setup()
        if self.test_drives:
            self.test_control["drives"] = self.test_drives
        if self.boot_drive:
            self.test_control["boot_drive"] = self.boot_drive
        fio = FioRunner(self.host, self.test_control)
        self.validate_no_exception(
            fio.test_setup,
            [],
            "Fio setup()",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

    def execute(self) -> None:
        """Execution of the FIO Internal Flush Test.

        This method constructs the command for fio internal flush test with
        number of loops, thread and executes the fio tool to check
        the drive IO performance and power cycles with following conditions.
           1. Power Cycle Server with NVME Flush
           2. Power Cycle Server without NVME Flush
           3. Dirty power cycle (Using FIO Trigger command)
        """
        self.host_dict = self.get_host_dict(self.host)
        for current_cycle in range(1, self.iteration_count + 1):
            # FIO write
            run_definition = self.workloads["nvme_flush_write"]
            self.log_info("write in progress")
            self.validate_no_exception(
                self.run_fio,
                [run_definition, self.power_trigger],
                "Cycle %d: Fio write job completed." % current_cycle,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )
            # Flush the all Nvme drive
            if self.nvme_flush:
                self.log_info("NVME flush in progress")
                threads = []
                for drive in self.test_drives:
                    if self.parallel_mode:
                        threads.append(
                            AutovalThread.start_autoval_thread(
                                self.flush_nvme_drive, self.host_dict, drive
                            )
                        )
                    else:
                        drive.nvme_flush()
                AutovalThread.wait_for_autoval_thread(threads)

            # powercycle for after fio ran
            if not self.power_trigger:
                self.log_info("Reboot in progress")
                self.host.cycle_host(self.host, self.cycle_type)

            # make sure to all drives are populated.
            self.check_block_devices_available()

            # FIO read
            run_definition = self.workloads["nvme_flush_read"]
            # Mounting the dirs after power cycle
            if self.filesystem:
                # pyre-fixme[19]: Expected 0 positional arguments.
                self._mount_dir(run_definition)
            self.log_info("read in progress")
            self.validate_no_exception(
                self.run_fio,
                [run_definition],
                "Cycle %d: Fio read job completed." % current_cycle,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )
            # FIO verify
            run_definition = self.workloads["nvme_flush_verify"]
            self.log_info("Verify in progress")
            self.validate_no_exception(
                self.run_fio,
                [run_definition],
                "Cycle %d: Fio verify job completed." % current_cycle,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )

    def run_fio(self, run_definition, power_trigger: bool = False) -> None:
        """FIO Job of the FIO internal Flush Test.

        This method executes the fio for internal flush test with number
        of loops and threads and checks the drive IO operations.

        Raises
        ------
        TestStepError when fails to run the FIO job
        """
        self.test_control["power_trigger"] = power_trigger
        self.test_control["run_definition"] = run_definition
        fio = FioRunner(self.host, self.test_control)
        fio.start_test()

    def flush_nvme_drive(self, host, drive) -> None:
        """Flush NVMe Drive.

        This method executes the NVMe flush command for internal flush test,
        to flush the data from the NVMe drives. ##TODO
        """
        if isinstance(host, dict):
            host = Host(host)
        AutovalUtils.run_on_host(host, drive.nvme_flush)

    def _mount_dir(self) -> None:
        """Mount Dir.

        This method enables the skip_fs flag to skip the filesystem creation
        and executes the mount command after the power cyle.

        """
        self.test_control["skip_fs"] = True
        FilesystemUtils.mount_all(
            self.host, self.test_drives, MOUNT_PATH, force_mount=False
        )

    def get_test_params(self) -> str:
        return (
            f"Cycle type: {self.cycle_type}\n"
            f"Number of iteration: {self.iteration_count}\n"
            f"Power_trigger: {self.power_trigger}\n"
            f"Nvme_flush: {self.nvme_flush}\n"
        )

    def cleanup(self):
        # unmount the drives
        if self.filesystem:
            AutovalUtils.validate_no_exception(
                FilesystemUtils.unmount_all,
                [self.host, self.drives_md5, MOUNT_PATH],
                "clean drive",
                raise_on_fail=False,
                log_on_pass=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.SYSTEM_ERR,
            )
        super().cleanup(cfg_filter=[{"filter_name": "bios_filter"}])
