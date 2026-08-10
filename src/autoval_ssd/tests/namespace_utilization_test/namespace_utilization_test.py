#!/usr/bin/env python3
# Copyright (c) 2019-present, Facebook, Inc.
# All rights reserved.
#
# Description     : This test validates the namespace utilization size
#                   by running fio job and check the size using the
#                   'nvme id-ns /dev/nvmex' command.

# pyre-strict
import json
import os
import re
import time

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.file_actions import FileActions
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.storage.nvme.nvme_drive import NVMeDrive
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase


class NamespaceUtilizationTest(StorageTestBase):
    """
    This script is used to ensure that namespace utilization size
    by running the fio job and check the size using the
    'nvme id-ns /dev/nvmex' command.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.cycle_count: int = self.test_control.get("cycle", 3)
        self.expected_nuse_size: int = self.test_control.get(
            "expected_nuse_size", 2621440
        )
        self.nvme_format_timeout: int = self.test_control.get(
            "nvme_format_timeout", 1200
        )
        self.nvme_format_block_size: int | None = self.test_control.get(
            "nvme_format_block_size", None
        )
        self.validate_drive_cleared_with_sanitize_log: bool = self.test_control.get(
            "validate_drive_cleared_with_sanitize_log", False
        )

    def _verify_drive_health_post_format(self, drive: NVMeDrive) -> None:
        """Verify drive health via nvme id-ns after format (ref: S363460, S390936, S530447).

        Post-format, the drive should respond to id-ns with valid namespace data.
        A non-responsive or erroring drive indicates a format failure that
        the format command itself may not have reported.
        """
        try:
            # pyrefly: ignore [missing-attribute]
            output = self.host.run(f"nvme id-ns /dev/{drive}")
            self.validate_condition(
                output is not None and len(output.strip()) > 0,
                f"{drive}: Post-format drive health check via nvme id-ns",
                raise_on_fail=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
        except Exception as e:
            self.validate_condition(
                False,
                f"{drive}: Post-format drive health check failed - "
                f"nvme id-ns returned error: {e}",
                raise_on_fail=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

    def _check_dmesg_io_errors(self, drives: list[NVMeDrive]) -> None:
        """Check dmesg for I/O errors on NVMe devices after format (ref: S175040).

        Format operations that silently fail may leave I/O error traces in dmesg.
        """
        try:
            # pyrefly: ignore [missing-attribute]
            output = self.host.run("dmesg -T --level=err")
            for drive in drives:
                drive_name = str(drive)
                io_error_patterns = [
                    f"I/O error.*{drive_name}",
                    f"{drive_name}.*I/O error",
                    f"blk_update_request.*{drive_name}.*error",
                ]
                for pattern in io_error_patterns:
                    if re.search(pattern, output):
                        self.validate_condition(
                            False,
                            f"{drive}: dmesg I/O errors detected after format "
                            f"operation (pattern: {pattern})",
                            raise_on_fail=False,
                            component=COMPONENT.STORAGE_DRIVE,
                            error_type=ErrorType.DRIVE_ERR,
                        )
                        break
        except Exception as e:
            AutovalLog.log_info(f"dmesg I/O error check skipped: {e}")

    def _get_nuse_safe(self, drive: NVMeDrive) -> int:
        """Null-safe wrapper for drive.get_size('nuse') (ref: S573928).

        Returns 0 if get_size returns None, preventing TypeError
        in downstream comparisons.
        """
        nuse = drive.get_size("nuse")
        if nuse is None:
            self.validate_condition(
                False,
                f"{drive}: get_size('nuse') returned None - drive may not "
                "support NUSE reporting",
                raise_on_fail=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
            return 0
        return nuse

    def _wait_for_drive_ready(self, drive: NVMeDrive, timeout: int = 120) -> bool:
        """Poll `nvme id-ns` until the drive responds cleanly or timeout expires.

        After a Sanitize operation completes (SSTAT=001), the controller may
        still be re-attaching namespaces and briefly return
        "Device or resource busy" for subsequent admin commands. This helper
        waits for the drive to be ready before returning.
        """
        deadline = time.time() + timeout
        last_err: str | None = None
        while time.time() < deadline:
            try:
                # pyrefly: ignore [missing-attribute]
                output = self.host.run(f"nvme id-ns /dev/{drive}")
                if output and output.strip():
                    return True
            except Exception as e:
                last_err = str(e)
            time.sleep(5)
        AutovalLog.log_info(
            f"{drive}: Drive did not become ready within {timeout}s "
            f"after sanitize (last error: {last_err})"
        )
        return False

    def _log_fio_results(self) -> None:
        """Read FIO JSON output files from FioRunner's result directory and log key results."""
        try:
            resultsdir = self.fio.resultsdir
            if not resultsdir or not FileActions.exists(resultsdir, self.host):
                AutovalLog.log_info("FIO results directory not found")
                return
            # pyrefly: ignore [missing-attribute]
            files = self.host.run(f"ls {resultsdir}").strip().split("\n")
            for f in files:
                if not f.endswith(".json"):
                    continue
                fio_file = os.path.join(resultsdir, f)
                fio_output = FileActions.read_data(fio_file, host=self.host)
                AutovalLog.log_info(f"FIO output file: {fio_file}")
                data = json.loads(fio_output)
                for job in data.get("jobs", []):
                    filename = job.get("filename", "unknown")
                    write_info = job.get("write", {})
                    write_bytes = write_info.get("io_bytes", 0)
                    write_bw = write_info.get("bw", 0)
                    read_info = job.get("read", {})
                    read_bytes = read_info.get("io_bytes", 0)
                    error = job.get("error", 0)
                    AutovalLog.log_info(
                        f"FIO {filename}: wrote {write_bytes} bytes "
                        f"({write_bytes / (1024**3):.2f} GB), "
                        f"read {read_bytes} bytes, "
                        f"bw={write_bw} KB/s, error={error}"
                    )
        except (json.JSONDecodeError, OSError) as e:
            AutovalLog.log_info(f"Failed to read FIO results: {e}")

    def execute(self) -> None:
        """
        Test Flow:
        1. Filter the drives with crypto erase supported options
        2. Filter the drives with nuse supported drives
        3. Format the drive with secure erase option
        4. Verify drive health post-format via nvme id-ns
        5. Check dmesg for I/O errors after format
        6. Read nuse from id-ns and check that it == 0 (per-drive validation)
           (or validate via sanitize log if validate_drive_cleared_with_sanitize_log is True)
        7. Sequentially Write 10GB of data to the drive
        8. Read nuse from id-ns and check that it equals 2621440(0x280000)
           - indicating 10GB of namespace has been used
           (or verify via read/verify if validate_drive_cleared_with_sanitize_log is True)
        9. Format the drive with crypto-erase option
        10. Repeat the steps 3-8 for the given cycle_count
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
            AutovalLog.log_info(f"Cycle Count: {i + 1}")
            for drive in nuse_test_drives:
                self.validate_no_exception(
                    NVMeUtils.format_nvme,
                    [self.host, drive, 2, self.nvme_format_block_size],
                    f"{drive}: NVME formatting using Cryptographic erase option 2",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.NVME_ERR,
                )
                self._verify_drive_health_post_format(drive)
            self._check_dmesg_io_errors(nuse_test_drives)
            if self.validate_drive_cleared_with_sanitize_log:
                for drive in nuse_test_drives:
                    if self.validate_sanitize_status(drive):
                        AutovalLog.log_info(
                            f"{drive}: Sanitize operation completed successfully"
                        )
            else:
                timeout = time.time() + self.nvme_format_timeout
                all_drives_zeroed = False
                while time.time() < timeout:
                    all_drives_zeroed = True
                    for drive in nuse_test_drives:
                        nuse = self._get_nuse_safe(drive)
                        if nuse != 0:
                            all_drives_zeroed = False
                    if all_drives_zeroed:
                        break
                    time.sleep(30)
                for drive in nuse_test_drives:
                    nuse = self._get_nuse_safe(drive)
                    self.validate_equal(
                        nuse,
                        0,
                        f"{drive}: nuse size after drive erase operation",
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.DRIVE_ERR,
                    )
            self.run_fio_and_verify_or_validate_nuse(nuse_test_drives)

        self._final_crypto_erase(nuse_test_drives)

    def _final_crypto_erase(self, drives: list[NVMeDrive]) -> None:
        """Crypto erase all test drives after the final cycle to clean up written data."""
        AutovalLog.log_info("Final cleanup: crypto erasing test drives")
        for drive in drives:
            self.validate_no_exception(
                NVMeUtils.format_nvme,
                [self.host, drive, 2, self.nvme_format_block_size],
                f"{drive}: Final crypto erase cleanup",
                raise_on_fail=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )

    def run_fio_and_verify_or_validate_nuse(self, drives: list[NVMeDrive]) -> None:
        """Run FIO write test and validate nuse size."""
        self.validate_no_exception(
            self.fio.start_test,
            [],
            "Fio start_test()",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )
        self._log_fio_results()
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
            nuse_tolerance_pct = self.test_control.get("nuse_tolerance_pct", 1.0)
            for drive in drives:
                nuse_size = self._get_nuse_safe(drive)
                diff = abs(nuse_size - self.expected_nuse_size)
                diff_pct = (
                    (diff / self.expected_nuse_size * 100)
                    if self.expected_nuse_size
                    else 0
                )
                within_tolerance = diff_pct <= nuse_tolerance_pct and nuse_size > 0
                self.validate_condition(
                    within_tolerance,
                    f"{drive}: nuse size {nuse_size} is within {diff_pct:.2f}% "
                    f"of expected {self.expected_nuse_size} (diff={diff} blocks)",
                    raise_on_fail=False,
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )
                time.sleep(20)

    def validate_sanitize_status(self, drive: NVMeDrive) -> bool:
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

    def parse_sanitize_log(self, drive: NVMeDrive) -> tuple[int, int]:
        """
        Parse NVMe sanitize log to get status and estimated block erase time.

        Returns:
            tuple: (sanitize_status, estimated_time)
        """
        cmd = f"nvme get-log /dev/{drive} --log-id=0x81 --log-len=128"
        # pyrefly: ignore [missing-attribute]
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

    def get_nuse_test_drives(self) -> list[NVMeDrive]:
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
                if self.validate_drive_cleared_with_sanitize_log:
                    try:
                        NVMeUtils.sanitize_nvme(
                            self.host,  # pyrefly: ignore [bad-argument-type]
                            str(drive),
                            4,
                        )
                        AutovalLog.log_info(
                            f"{drive}: NVMe Sanitize (Crypto Erase) issued"
                        )
                    except Exception:
                        self.validate_condition(
                            False,
                            f"{drive}: NVMe Sanitize (Crypto Erase) not supported",
                            raise_on_fail=False,
                            component=COMPONENT.STORAGE_DRIVE,
                            error_type=ErrorType.NVME_ERR,
                        )
                        continue

                    if self.validate_sanitize_status(drive):
                        if not self._wait_for_drive_ready(drive):
                            self.validate_condition(
                                False,
                                f"{drive}: Drive not ready after sanitize; "
                                f"skipping from nuse test drives",
                                raise_on_fail=False,
                                component=COMPONENT.STORAGE_DRIVE,
                                error_type=ErrorType.DRIVE_ERR,
                            )
                            continue
                        nuse_test_drives.append(drive)
                        AutovalLog.log_info(
                            f"{drive}: Added to nuse test drives after successful sanitize operation"
                        )
                else:
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
                        continue

                    nuse = self._get_nuse_safe(drive)
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
