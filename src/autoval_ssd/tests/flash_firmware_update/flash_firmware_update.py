#!/usr/bin/env python3

# pyre-unsafe

from threading import Event
from typing import Any, Dict, Optional

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalLog, AutovalUtils
from autoval_ssd.lib.utils.drive_monitor_utils import DriveMonitorUtils
from autoval_ssd.lib.utils.storage.drive import DriveType
from autoval_ssd.lib.utils.storage.drive_firmware_update import DriveFirmwareUpdate
from autoval_ssd.lib.utils.storage.drive_fw_update_util import DriveFwUpdateUtil


class FlashFirmwareUpdate(DriveFirmwareUpdate):
    """Flash Drive's firmware Update.

    This test gets the firmware details from the Flash drive and updates
    the firmware (bin file) for the flash drive.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # only pick SSD for testing
        self.test_control["drive_type"] = DriveType.SSD.value
        self.test_results = {}
        # always config check needs to validate for flash fw update test.
        self.test_control["disable_config_collection"] = False
        self.nvme_admin_io: bool = self.test_control.get("nvme_admin_io", False)
        self.enable_periodic_drive_monitor = self.test_control.get(
            "enable_periodic_drive_monitor", False
        )
        self.end_of_test = None

    def storage_test_setup(self) -> None:
        super().storage_test_setup()
        # setup number of successful flash firmware updates and update data in the test results
        self.test_results["number_of_successful_flash_firmware_updates"] = 0
        self.test_results["flash_firmware_update_data"] = []
        self.test_results["failed_firmware_update_data"] = []
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

    def get_test_params(self) -> str:
        """
        Returns a string of test_params for the Test Summary
        """
        params = super().get_test_params()
        params += f", NVME_update_actions: {self.nvme_update_actions}"
        return params

    # @override
    def firmware_update(
        self,
        ver: str,
        iteration: Optional[int] = None,
        drive_version_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Firmware update

        This method will update the firmware in parallel or in sequence
        and run fio post update based on the input.

        Args:
            ver: firmware to install on DUT.
            iteration: iteration number of the test.
            drive_version_info: version info of the drives on DUT.

        Returns:
            None

        Raises:
            ToolError: When fails to start fio test through fio runner.
            AutovalThreadError: When fails to wait for the threads.
        """
        drive_fw_updater = DriveFwUpdateUtil(self.host, self.test_control)
        # Key which determines to run the firmware update in parallel or not.
        parallel_update = self.test_control.get("parallel_update", None)
        parallel_firmware_fio_jobs = []
        flash_firmware_update_data = self.test_results["flash_firmware_update_data"]
        failed_firmware_update_data = self.test_results["failed_firmware_update_data"]
        if parallel_update:
            if self.verify_io:
                self.log_info(
                    "Starting fio to the DUT with firmware update in parallel"
                )
                parallel_firmware_fio_jobs.append(
                    AutovalThread.start_autoval_thread(self.fio_runner.start_test)
                )
            for drive in self.test_drives:
                self.log_info(
                    f"Running firmware update for {drive.block_name} in background"
                )
                parallel_firmware_fio_jobs.append(
                    AutovalThread.start_autoval_thread(
                        drive_fw_updater.test_firmware_update,
                        drive,
                        ver,
                        failed_firmware_update_data=failed_firmware_update_data,
                        iteration=iteration,
                        drive_version_info=drive_version_info,
                    )
                )
            self.log_info("Waiting for all the background jobs to complete")
            results = AutovalThread.wait_for_autoval_thread(
                parallel_firmware_fio_jobs,
                flash_firmware_update_data=flash_firmware_update_data,
            )
            filtered_results = [result for result in results if result is not None]
            self.test_results["number_of_successful_flash_firmware_updates"] += len(
                filtered_results
            )
            self.log_info(f"+++Firmware update on all drives with {ver} is completed")
        else:
            for drive in self.test_drives:
                update_data = drive_fw_updater.test_firmware_update(
                    drive,
                    ver,
                    failed_firmware_update_data=failed_firmware_update_data,
                    iteration=iteration,
                    drive_version_info=drive_version_info,
                )
                flash_firmware_update_data.append(update_data)
                self.test_results["number_of_successful_flash_firmware_updates"] += 1
            if self.verify_io:
                self.log_info("Starting fio to the DUT now")
                self.validate_no_exception(
                    self.fio_runner.start_test,
                    [],
                    "Fio start_test()",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.TOOL_ERR,
                )

    # @override
    def execute(self) -> None:
        for i in range(1, self.iteration + 1):
            # Get initial version
            drive_version_info = {}
            for drive in self.test_drives:
                version = drive.get_firmware_version()
                self.log_info(
                    "Drive %s has initial FW version %s" % (drive.block_name, version)
                )
                drive_version_info[drive.block_name] = version
            AutovalLog.log_info("Cycle %d:" % i)
            for ver in self.fw_versions:
                self.firmware_update(
                    ver=ver, iteration=i, drive_version_info=drive_version_info
                )
        if self.nvme_admin_io:
            for drive in self.test_drives:
                drive.validate_fw_commit_timer(
                    drive.fw_commit_timer_after, drive.fw_commit_timer_before
                )
                drive.validate_admin_command_timer(
                    drive.admin_command_timer_after, drive.command_timer_before
                )
                drive.validate_io_command_timer(
                    drive.io_command_timer_after, drive.command_timer_before
                )
                drive.check_admin_command_success(drive.admin_command)
                drive.check_io_command_success(drive.io_command)
                drive.check_new_firmware_current_firmware(drive.current_fw_ver)

    def cleanup(self, *args, **kwargs) -> None:
        if self.enable_periodic_drive_monitor and self.end_of_test:
            self.end_of_test.set()
            AutovalThread.wait_for_autoval_thread([self.monitor_thread])
        try:
            AutovalUtils.result_handler.add_test_results(self.test_results)
        except Exception as err:
            self.log_info(
                f"drive fw active history clean failed with error : {str(err)}"
            )
            raise
        finally:
            cfg_filter = [{"filter_name": "bios_filter"}]
            super().cleanup(*args, **kwargs, cfg_filter=cfg_filter)
