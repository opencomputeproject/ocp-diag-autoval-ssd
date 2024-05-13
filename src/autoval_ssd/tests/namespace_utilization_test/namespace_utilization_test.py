#!/usr/bin/env python3
# Copyright (c) 2019-present, Facebook, Inc.
# All rights reserved.
#
# Description     : This test validates the namespace utilization size
#                   by running fio job and check the size using the
#                   'nvme id-ns /dev/nvmex' command.

# pyre-unsafe
import time

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_log import AutovalLog

from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase


class NamespaceUtilizationTest(StorageTestBase):
    """
    This script is used to ensure that namespace utilization size
    by running the fio job and check the size using the
    'nvme id-ns /dev/nvmex' command.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.cycle_count = self.test_control.get("cycle", 3)
        self.expected_nuse_size = self.test_control.get("expected_nuse_size", 2621440)
        self.nvme_format_timeout = self.test_control.get("nvme_format_timeout", 1200)
        self.nvme_format_block_size = self.test_control.get(
            "nvme_format_block_size", None
        )

    def execute(self) -> None:
        """
        Test Flow:
        1. Filter the drives with crypto erase supported options
        2. Filter the drives with nuse supported drives
        3. Format the drive with secure erase option
        4. Read nuse from id-ns and check that it == 0
        5. Sequentially Write 10GB of data to the drive
        6. Read nuse from id-ns and check that it equals 2621440(0x280000)
           - indicating 10GB of namespace has been used
        7. Format the drive with crypto-erase option
        8. Repeat the steps 3-5 for the given cycle_count
        """
        nuse_test_drives = self.get_nuse_test_drives()
        if nuse_test_drives:
            self.test_control["drives"] = nuse_test_drives
        self.fio = FioRunner(self.host, self.test_control)
        self.validate_no_exception(
            self.fio.test_setup,
            [],
            "Fio setup()",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )
        AutovalLog.log_info(f"Drives for namespace utilization test {nuse_test_drives}")
        for i in range(self.cycle_count):
            AutovalLog.log_info("Cycle Count: %d" % (i + 1))
            for drive in nuse_test_drives:
                self.validate_no_exception(
                    NVMeUtils.format_nvme,
                    [self.host, drive, 2, self.nvme_format_block_size],
                    f"{drive}: NVME formatting using Cryptographic erase option 2",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.NVME_ERR,
                )
            timeout = time.time() + self.nvme_format_timeout
            nuse_all_zero = 0
            while time.time() < timeout:
                # reset nuse_all_zero to 0 for every checking cycle
                nuse_all_zero = 0
                for drive in nuse_test_drives:
                    # check if any drive's nuse equal 0
                    nuse_all_zero = nuse_all_zero or drive.get_size("nuse")
                # if nuse_all_zero quit while loop, no need to wait for timeout
                if nuse_all_zero == 0:
                    break
                time.sleep(30)
            self.validate_equal(
                nuse_all_zero,
                0,
                "nuse size of all drive after drive erase operation",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
            self.validate_no_exception(
                self.fio.start_test,
                [],
                "Fio start_test()",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )
            for drive in nuse_test_drives:
                nuse_size = drive.get_size("nuse")
                self.validate_equal(
                    nuse_size,
                    self.expected_nuse_size,
                    f"nuse size of {drive} after 10GB write operation",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )
                time.sleep(20)

    def get_nuse_test_drives(self):
        """
        Get nuse Test Drives.

        This method is used to filter the drives with crypto erase and
        nuse supported drives.
        """
        nuse_test_drives = []
        for drive in self.test_drives:
            out = drive.get_crypto_erase_support_status()
            if out:
                nsze = drive.get_size("nsze")
                try:
                    NVMeUtils.format_nvme(self.host, drive, 1)
                    AutovalLog.log_info(
                        f"{drive}: NVME Formatting using User Data Erase option 1"
                    )
                except Exception:
                    self.validate_condition(
                        False,
                        f"{drive}: NVME formatting with User Data Erase option 1 not supported",
                        raise_on_fail=False,
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.NVME_ERR,
                    )
                nuse = drive.get_size("nuse")
                AutovalLog.log_info(f"{drive}: Nuse size after User Data Erase: {nuse}")
                if nsze != nuse:
                    nuse_test_drives.append(drive)
                else:
                    AutovalLog.log_info(
                        f"Skipping {drive} for nuse test, since nuse and nsze"
                        f"values are same even after User Data Erase operation"
                    )
        self.validate_non_empty_list(
            nuse_test_drives,
            "Validating crypto erase supported drives",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        return nuse_test_drives
