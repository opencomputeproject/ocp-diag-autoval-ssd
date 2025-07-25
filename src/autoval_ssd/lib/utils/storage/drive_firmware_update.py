#!/usr/bin/env python3

# pyre-unsafe

from abc import ABC
from typing import List

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.storage.drive import Drive
from autoval_ssd.lib.utils.storage.drive_fw_update_util import DriveFwUpdateUtil
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase


class DriveFirmwareUpdate(StorageTestBase, ABC):
    """Drive Firmware Update.

    This util installs/updates and validates drive firmware. Optionally
    performs IO after firmware update.

    Parameters
    ----------
    versions:  :obj:`List` of 'String'
        Firmware version to find and install on test drives.
    cycle: Integer
        How many times to perform the upgrade/downgrade cycle.
    verify_io: Boolean
        If set to True will perform IO on test drives post firmware update.
    fio_template: String
        Path to fio_template file to be used.
    fio_options: Dictionary
        Mapping of entries to fill in the given template file.

    Example
    -------
    Sample control file:
        {
          "cycle": 2,
          "versions": ["stable", "latest"],
          "verify_io": true,
          "fio_template": "basic_verify.job",
          "fio_options": {
            "RW":"randrw",
            "BLKSIZE":"128k",
            "SIZE":"10G",
            "RUNTIME":"30m",
            "DEPTH":"128",
            "VERIFY": "crc32c"
          }
        }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.revert_to_stable: bool = self.test_control.get("revert_to_stable", False)
        self.fw_versions: List[str] = self.test_control.get(
            "versions", ["latest", "stable"]
        )
        self.nvme_update_actions: List[int] = self.test_control.get(
            "nvme_update_actions", [1, 3]
        )
        self.iteration: int = self.test_control.get("cycle", 1)
        self.verify_io: bool = self.test_control.get("verify_io", False)
        self.fio_runner = None

    # @override
    def storage_test_setup(self) -> None:
        """Initializes Drive Firmware Update Tests.

        This method install the packages required for the test. Initializes
        the basic configuration for logging information, read and store the
        input details gathered from input file and assigns the variables
        "fio_run_definition" with the value from "test_control" dictionary.
        Also install the rpm's required for the fio job.

        Raises
        ------
        TestStepError
            When fails to install the fio on the DUT.
        """
        super().storage_test_setup()
        self.drive_fw_updater = DriveFwUpdateUtil(self.host, self.test_control)
        if self.verify_io:
            if self.test_drives:
                self.test_control["drives"] = self.test_drives
            if self.boot_drive:
                self.test_control["boot_drive"] = self.boot_drive
            self.test_control["skip_iops_validation"] = True
            self.fio_runner = FioRunner(self.host, self.test_control)
            self.validate_no_exception(
                self.fio_runner.test_setup,
                [],
                "Fio setup()",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )

    # @override
    def execute(self) -> None:
        """Execution of Drive Firmware Update.

        This method gets the test drive details using firmware information
        from fw_version_map.json, constructs the binary file path, updates the
        firmware based on the binary file path and verifies IO using FIO job.

        Raises
        ------
        TestError
            When fails to update the firmware for the drive.
        """
        for i in range(1, self.iteration + 1):
            # Get initial version
            for drive in self.test_drives:
                version = drive.get_firmware_version()
                self.log_info(
                    "Drive %s has initial FW version %s" % (drive.block_name, version)
                )
            AutovalLog.log_info("Cycle %d:" % i)
            for ver in self.fw_versions:
                self.firmware_update(ver)

    def firmware_update(self, ver: str) -> None:
        """
        Firmware update

        This method will update the firmware and run fio
        post update based on the input.

        Parameters
        ----------
        ver: String
            firmware to install on DUT.
        """

        for drive in self.test_drives:
            self.drive_fw_updater.test_firmware_update(drive, ver)
        if self.verify_io:
            self.log_info("Starting fio to the DUT now")
            self.fio_runner.start_test()

    def fw_name_to_version_name(self, version: str, drive: Drive) -> str:
        """Some firmware names in `fw_version_map.json` file are
        referred to as "stable" or "latest". This is for convenience of
        replacing binary each time a new version comes out.
        However, the string "latest" doesn't indicate the exact firmware.
        This method returns the exact version that those string refers
        to in file `fw_version_map.json`
        """
        try:
            fw_info = self.drive_fw_updater._get_firmware_info(version, drive)
        except Exception:
            self.log_info(f"{drive}: FW upgrade not supported")
            return ""
        self.validate_in(
            "name",
            fw_info,
            "Firmware version {version} does not have a 'name' attribute",
            log_on_pass=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.FIRMWARE_ERR,
        )
        return fw_info.get("name", "")

    def get_test_params(self) -> str:
        """
        get_test_params:
        returns a string of test_params for the Test Summary
        """
        verify_report = (
            "Run IO after each firmware update cycle." if self.verify_io else ""
        )
        if self.test_drives:
            drive = self.test_drives[0]
        else:
            raise TestError(
                "Empty test drives list.",
                error_type=ErrorType.INPUT_ERR,
            )
        firmware = []
        for version in self.fw_versions:
            firmware.append(self.fw_name_to_version_name(version, drive))
        params = (
            f"\nFirmware being installed each cycle: {firmware}\n"
            f"Number of update cycle: {self.iteration}\n"
            f"{verify_report}"
        )
        return params

    def cleanup(self, *args, **kwargs) -> None:
        flash_fw_version = "latest"
        try:
            if self.revert_to_stable:
                flash_fw_version = "stable"
            self.log_info(f"Reverting back {flash_fw_version} version")
            for drive in self.test_drives:
                self.drive_fw_updater.test_firmware_update(drive, flash_fw_version)
        except AttributeError as e:
            self.log_info(f"self.drive_fw_updater has not been initized: {e}")
        except Exception as e:
            self.log_info(
                f"Failed while Reverting back to {flash_fw_version} version with error - {str(e)}."
            )
            raise
        finally:
            super().cleanup(*args, **kwargs)
