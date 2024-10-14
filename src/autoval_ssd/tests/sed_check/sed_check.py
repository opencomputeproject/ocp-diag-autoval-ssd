#!/usr/bin/env python3

# pyre-unsafe
"""
Test validates if the Self Encrypting Drive supports OPAL 2.0 spec
"""
from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval_ssd.lib.utils.sed_util import SedUtils
from autoval_ssd.lib.utils.storage.drive import DriveType
from autoval_ssd.lib.utils.storage.nvme.nvme_drive import OwnershipStatus
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase


class SedCheck(StorageTestBase):
    """
    This script is used to validate if the Self Encrypting drive is based
    on OPAL 2.0 specification.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.opal_drive_objs = []
        self.test_control["drive_type"] = DriveType.SSD.value
        self.test_control["include_boot_drive"] = True
        self.include_boot_drive = True

    def setup(self, *args, **kwargs) -> None:
        self.storage_test_tools.extend(["sedutil"])
        self.test_control["drive_type"] = DriveType.SSD.value
        self.test_control["include_boot_drive"] = True
        self.include_boot_drive = True
        super().setup(*args, **kwargs)

    def execute(self) -> None:
        """
        Test Flow:
        1. Check information - issue "sedutil-cli --scan"
          command to check drive information.
        2. Check SED support.
        3. if SED is not supported, pass test.
        4. check if ownership is taken for all the SED supported
        if not fail the test if validate_take_ownership is true.
        """
        opal_list, non_opal_list = SedUtils.opal_support_scan(self.host)
        self.validate_non_empty_list(
            opal_list,
            "Validate if SED drives are present",
            warning=True,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        if opal_list:
            self.log_info(f"SED Supported Drive list is {opal_list}")
            self.opal_drive_objs = [
                drive
                for drive in self.test_drives
                if drive.get_drive_name() in opal_list
            ]
            self.log_info(
                "SED Supported Drive list is "
                f"{[f'Serial no:{drive.serial_number} block name:{drive.block_name})' for drive in self.opal_drive_objs]}"
            )
            if self.test_control.get("valdiate_drive_ownership", True):
                self.log_info(
                    "Validating, if ownership is taken for the opal supported drives."
                )
                for drive in self.opal_drive_objs:
                    self.validate_in(
                        str(drive.get_tcg_ownership_status()),
                        [
                            str(OwnershipStatus.SET),
                            str(OwnershipStatus.BLOCKED_AND_SET),
                        ],
                        "validating the drive ownership status"
                        f" {drive.block_name} {drive.serial_number}",
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.DRIVE_ERR,
                    )
        if non_opal_list:
            self.log_info(f"SED Un-Supported Drive list is {non_opal_list}")
