#!/usr/bin/env python3

# pyre-unsafe
"""
Test validates if the Self Encrypting Drive supports OPAL 2.0 spec and
ownership of the drive can be correctly set and verified.
"""
from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval_ssd.lib.utils.sed_util import SedUtils
from autoval_ssd.lib.utils.storage.nvme.nvme_drive import OwnershipStatus
from autoval_ssd.tests.sed_check.sed_check import SedCheck


class SedTakeOwnership(SedCheck):
    """
    The intent of the sed_take_ownership test is to validate if the SED is based
    on the OPAL 2.0 specification and to ensure that the ownership of the drive
    can be correctly set and verified. This test is crucial for maintaining
    the security and proper management of the drives in use.
    """
    
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.test_control["valdiate_drive_ownership"] = False
        self.ownership_taken_drives = []

    def execute(self) -> None:
        """
        Test Flow:
        1. Check information - issue "sedutil-cli --scan"
          command to check drive information.
        2. Check SED support.
        3. if SED is not supported, pass test.
        4. Check Locked = N with sedutil-cli --query $drive.
        5. Check ownership state
        6. If ownership is taken, attempt to revert with a tper revert
        """
        super().execute()
        if not self.opal_drive_objs:
            self.validate_condition(
                False,
                "Validate if SED drives are present",
                warning=True,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
            return
        self.log_info("Validating the take ownership for opal supported drives.")
        for drive in self.opal_drive_objs:
            msid = SedUtils.get_msid(self.host, drive.block_name)
            lock_status = SedUtils.check_locked_status(self.host, drive.block_name)
            ownership_status = drive.get_tcg_ownership_status()
            self.log_info(f"+++Performing Take ownership check on {drive.block_name}")
            self.log_info(
                f"Locked Status for drive {drive.block_name} is {lock_status}"
            )
            self.log_info(
                f"TCG Ownership for drive {drive.block_name} is {ownership_status}"
            )
            if not lock_status:
                if ownership_status == OwnershipStatus.NOT_SET:
                    SedUtils.take_ownership(self.host, drive, password=msid)
                    self.ownership_taken_drives.append(drive)
                elif ownership_status == OwnershipStatus.SET:
                    if (
                        drive.tooling_owned_models
                        and drive.model in drive.tooling_owned_models
                    ):
                        self.log_info(
                            "+++ Model owned by tooling. Cannot revert ownership"
                        )
                        return
                    self.log_info(
                        "+++Reverting the ownership and proceeding"
                        " with the take_ownership"
                    )
                    SedUtils.revert_take_ownership(
                        self.host, drive, password="facebook"
                    )
                    if ownership_status == OwnershipStatus.NOT_SET:
                        SedUtils.take_ownership(self.host, drive, password=msid)
                        self.ownership_taken_drives.append(drive)
                else:
                    self.validate_condition(
                        False,
                        "Validate if Ownership can be taken",
                        warning=True,
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.DRIVE_ERR,
                    )
                    self.log_info(
                        "Ownership can not be taken as the drive "
                        f"{drive.serial_number} is locked."
                    )

    def cleanup(self, *args, **kwargs) -> None:
        for drive in self.ownership_taken_drives:
            SedUtils.revert_take_ownership(self.host, drive, password="facebook")
        super().cleanup(*args, **kwargs)
