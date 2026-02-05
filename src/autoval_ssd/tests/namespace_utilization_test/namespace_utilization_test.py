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
        self.validate_drive_cleared_with_sanitize_log = self.test_control.get(
            "validate_drive_cleared_with_sanitize_log", False
        )

    def execute(self) -> None:
        """
        Test Flow:
        1. Filter the drives with crypto erase supported options
        2. Filter the drives with nuse supported drives
        3. Format the drive with secure erase option
        4. Read nuse from id-ns and check that it == 0
           (or validate via sanitize log if validate_drive_cleared_with_sanitize_log is True)
        5. Sequentially Write 10GB of data to the drive
        6. Read nuse from id-ns and check that it equals 2621440(0x280000)
           - indicating 10GB of namespace has been used
           (or verify via read/verify if validate_drive_cleared_with_sanitize_log is True)
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
            if self.validate_drive_cleared_with_sanitize_log:
                for drive in nuse_test_drives:
                    if self.validate_sanitize_status(drive):
                        AutovalLog.log_info(
                            f"{drive}: Sanitize operation completed successfully"
                        )
            else:
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
            self.run_fio_and_verify_or_validate_nuse(nuse_test_drives)

    def run_fio_and_verify_or_validate_nuse(self, drives) -> None:
        """Run FIO test and validate nuse size."""
        self.validate_no_exception(
            self.fio.start_test,
            [],
            "Fio start_test()",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )
        if self.validate_drive_cleared_with_sanitize_log:
            read_verify_definition = self.test_control.get(
                "read_verify_run_definition", {}
            )
            if read_verify_definition:
                original_run_definition = self.fio.run_definition
                self.fio.run_definition = read_verify_definition
                try:
                    self.validate_no_exception(
                        self.fio.start_test,
                        [],
                        "Fio read/verify start_test()",
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.TOOL_ERR,
                    )
                    AutovalLog.log_info("FIO read/verify completed successfully")
                finally:
                    self.fio.run_definition = original_run_definition
        else:
            for drive in drives:
                nuse_size = drive.get_size("nuse")
                self.validate_equal(
                    nuse_size,
                    self.expected_nuse_size,
                    f"nuse size of {drive} after 10GB write operation",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )
                time.sleep(20)

    def validate_sanitize_status(self, drive) -> bool:
        """
        Validate the sanitize status of a drive by parsing its sanitize log.
        Waits for the estimated sanitize time and then re-checks the status
        to confirm the operation completed successfully.
        Returns True if sanitize operation completed successfully, False otherwise.
        """
        try:
            status, estimated_time = self.parse_sanitize_log(drive)

            # Wait for sanitize operation to complete
            AutovalLog.log_info(f"{drive}: Sanitize operation in progress")
            if estimated_time == 0xFFFFFFFF:
                wait_time = 120
                AutovalLog.log_info(
                    f"{drive}: No time period reported (0xFFFFFFFF), using default wait time of {wait_time}s"
                )
            else:
                wait_time = int(estimated_time * 1.5)
                AutovalLog.log_info(f"{drive}: Waiting {wait_time}s for sanitization")

            time.sleep(wait_time)

            # Re-check sanitize status after waiting
            status, _ = self.parse_sanitize_log(drive)

            if status in {0b100, 0b001}:
                return True
            else:
                self.validate_condition(
                    False,
                    f"{drive}: Sanitize operation failed with status: {status:#05b}",
                    raise_on_fail=False,
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )
                return False
        except ValueError as e:
            self.validate_condition(
                False,
                f"{drive}: Failed to parse sanitize log: {e}",
                raise_on_fail=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )
            return False

    def parse_sanitize_log(self, drive) -> tuple:
        """
        Parse NVMe sanitize log to get status and estimated block erase time.

        Returns:
            tuple: (sanitize_status, estimated_time)
        """
        cmd = f"nvme get-log /dev/{drive} --log-id=0x81 --log-len=128"
        output = self.host.run(cmd)

        hex_byte = []
        for line in output.strip().split("\n"):
            line = line.strip()
            if line and "Device:" not in line and line[0:4].isdigit():
                parts = line.split()
                if len(parts) > 1:
                    hex_byte.extend(parts[1:17])

        if len(hex_byte) < 16:
            raise ValueError(f"Insufficient sanitize log data: {len(hex_byte)} bytes")

        sanitize_status = int("".join(hex_byte[3:1:-1]), 16) & 0b111
        estimated_time = int("".join(hex_byte[15:11:-1]), 16)

        return sanitize_status, estimated_time

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

                if self.validate_drive_cleared_with_sanitize_log:
                    if self.validate_sanitize_status(drive):
                        nuse_test_drives.append(drive)
                        AutovalLog.log_info(
                            f"{drive}: Added to nuse test drives after successful sanitize operation"
                        )
                else:
                    nuse = drive.get_size("nuse")
                    AutovalLog.log_info(
                        f"{drive}: Nuse size after User Data Erase: {nuse}"
                    )

                    if nsze != nuse:
                        nuse_test_drives.append(drive)
                    else:
                        self.validate_condition(
                            False,
                            f"{drive}: nuse equals nsze after User Data Erase operation, "
                            f"drive does not support nuse validation",
                            raise_on_fail=False,
                            component=COMPONENT.STORAGE_DRIVE,
                            error_type=ErrorType.DRIVE_ERR,
                        )
        self.validate_non_empty_list(
            nuse_test_drives,
            "Validating crypto erase supported drives",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        return nuse_test_drives
