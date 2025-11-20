#!/usr/bin/env python3

# pyre-unsafe
"""QLC Drive Data Integrity test - specialized test for QLC drives with T10 DIX format support."""

import os
import random
import time
from typing import List

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.file_actions import FileActions
from autoval_ssd.lib.utils.storage.drive import Drive
from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.tests.drive_data_integrity.drive_data_integrity import (
    DriveDataIntegrityTest,
)


class QLCDriveDataIntegrityTest(DriveDataIntegrityTest):
    """Test validates data integrity for QLC drives with T10 DIX format support.

    This test extends DriveDataIntegrityTest with QLC-specific functionality including:
    - T10 DIX formatting (4k+64 lbaf)
    - QLC-specific FIO job sequences (write -> verify -> random LBA read)
    - QLC back to back power cycle test mode
    - Generic drive support
    """

    def __init__(self, *args, **kwargs) -> None:
        """
        Initializes the QLC Drive data integrity test.
        Additional test control params beyond parent class:
            test_generic_drives: Use generic device names instead of block names
            t10_dix_format: Format drives with T10 DIX format (4k+64 lbaf)
            qlc_power_cycle_test: Enable QLC power cycle test mode
            num_power_cycles: Number of power cycle iterations (default: 1)
            qlc_fio_runtime: Runtime for QLC FIO jobs in seconds
        """
        super().__init__(*args, **kwargs)
        self.test_generic_drives: bool = self.test_control.get(
            "test_generic_drives", False
        )
        self.t10_dix_format: bool = self.test_control.get("t10_dix_format", False)
        self.qlc_power_cycle_test: bool = self.test_control.get(
            "qlc_power_cycle_test", False
        )
        self.num_power_cycles: int = self.test_control.get("num_power_cycles", 1)
        self.qlc_fio_runtime: int = self.test_control.get("qlc_fio_runtime", 120)

    def setup(self, *args, **kwargs) -> None:
        """Prerequisite for QLC drive data integrity test.

        Extends parent setup with T10 DIX formatting if enabled.
        """
        super().setup(*args, **kwargs)

        if self.t10_dix_format:
            self.format_t10_dix_drives()

    def execute(self) -> None:
        """
        Main test execution for QLC drive data integrity.

        Runs QLC-specific FIO job sequence (write -> verify -> random LBA read)
        for the specified number of cycles or power cycle test based on configuration.
        """
        for i in range(1, self.cycle_count + 1):
            self.log_info(f"=== Starting cycle {i} of {self.cycle_count} ===")

            test_drives = self.test_drives.copy()

            self.save_drive_logs_async(test_drives)

            if self.qlc_power_cycle_test:
                self.run_qlc_power_cycle_test(test_drives, i)
            else:
                self.qlc_fio_test(test_drives, i)

            self.validate_condition(
                True,
                "Verify Flash Integrity for Cycle - %s" % i,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
            self.cleanup_test_file(force_delete=True)
        self.check_drives_presence()

    def qlc_fio_test(self, test_drives, cycle) -> None:
        """Runs QLC FIO tests on the given hosts.

        This method runs fio for the following jobs in sequential order:
        a. write with verification
        b. verify the above write
        c. verify random LBA

        Args:
           test_drives: All drives for the given drive type.
           cycle: No. of test cycle value.

        Raises
        ------
        TestStepError
            When fails to run the FIO job.
        """
        self.validate_no_exception(
            self.qlc_write_io,
            [test_drives, cycle],
            f"Cycle {cycle}: QLC Fio write job completed.",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

        self.check_block_devices_available()

        self.start_fio_monitor()
        self.validate_no_exception(
            self.qlc_verify_io,
            [test_drives, cycle],
            f"Cycle {cycle}: QLC Fio verify job completed.",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )
        self.stop_fio_monitor()

        self.start_fio_monitor()
        self.validate_no_exception(
            self.qlc_random_lba_read_io,
            [test_drives, cycle],
            f"Cycle {cycle}: QLC Random LBA read job completed.",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )
        self.stop_fio_monitor()

    def qlc_write_io(self, test_drives, cycle) -> None:
        """Run QLC write FIO jobs on the host.

        Args:
           test_drives: All drives for the given drive type.
           cycle: No. of test cycle value.
        """
        self.log_info(f"Cycle {cycle}")
        self.log_info("QLC Write in progress")
        qlc_write_job = self._get_qlc_common_fio_params()
        qlc_write_job.extend(
            [
                "verify=crc32",
                "time_based",
                "runtime=120",
                "do_verify=1",
                "verify_backlog=1000",
                "verify_state_save=1",
                "verify_async=4",
                "verify_fatal=1",
                "verify_dump=1",
            ]
        )
        self.run_fio(qlc_write_job, test_drives, "qlc_write", cycle, power_trigger=True)

    def qlc_verify_io(self, test_drives, cycle) -> None:
        """Run QLC verify FIO jobs on the host

        Args:
           test_drives: All drives for the given drive type.
           cycle: No. of test cycle value.
        """
        self.log_info(f"Cycle {cycle}")
        self.log_info("QLC Verify in progress")
        qlc_read_job = self._get_qlc_common_fio_params()
        qlc_read_job.extend(
            [
                "verify=crc32",
                "verify_only",
                "verify_state_load=1",
            ]
        )
        self.run_fio(
            qlc_read_job, test_drives, "qlc_verify", cycle, power_trigger=False
        )

    def qlc_random_lba_read_io(self, test_drives, cycle) -> None:
        """Run QLC random LBA read FIO jobs on the host.

        This job reads from random LBA locations with fixed 1G size
        using only common FIO parameters.

        Args:
           test_drives: All drives for the given drive type.
           cycle: No. of test cycle value.
        """
        self.log_info(f"Cycle {cycle}")
        self.log_info("QLC Random LBA Read in progress")
        qlc_random_read_job = self._get_qlc_common_fio_params(rw="read")
        self.run_fio(
            qlc_random_read_job, test_drives, "random_lba", cycle, power_trigger=False
        )

    def _get_qlc_common_fio_params(self, rw: str = "write") -> list:
        """Get common FIO parameters for QLC jobs.

        Args:
            rw: The read/write mode. Defaults to 'write'.

        Returns:
            List of common FIO parameters used by QLC jobs.
        """
        return [
            f"rw={rw}",
            "blocksize=128k",
            "md_per_io_size=2k",
            "iodepth=64",
            "ioengine=io_uring_cmd",
            "numjobs=1",
            "group_reporting=1",
            "cmd_type=nvme",
            "pi_act=1",
            "pi_chk=GUARD",
        ]

    def create_fio_job(
        self, job_str: List[str], drives: List[Drive], name: str, cycle: int = 1
    ) -> str:
        """Override parent method to support QLC-specific job creation.

        Args:
            job_str: FIO job arguments
            drives: List of drives
            name: Job name
            cycle: Test cycle number

        Returns:
            Complete FIO job content
        """
        dev_str = "[global]\n" + "\n".join(job_str) + "\n"
        filename = f"seq_io_{name}_cycle_{cycle}.fio"

        if name == "random_lba":
            dev_str = self.create_random_lba_job_content(dev_str, drives, name)
        else:
            dev_str = self.create_qlc_job_content(dev_str, drives, name, cycle)

        job_file = os.path.join(self.fiolog_dir, filename)
        if self.remote_fio:
            FileActions.write_data(job_file, dev_str)
        else:
            FileActions.write_data(job_file, dev_str, host=self.host, sync=True)
        return job_file

    def _get_global_fio_section(self, job_args: List[str]) -> str:
        """Create the global section of FIO job.

        Args:
            job_args: FIO job arguments

        Returns:
            FIO global section content
        """
        dev_str = "[global]\n"
        for line in job_args:
            dev_str += line + "\n"
        return dev_str

    def create_qlc_job_content(
        self, dev_str: str, drives: List[Drive], name: str, cycle: int = 1
    ) -> str:
        """Creates content for QLC fio job.

        Distributes the LBA range (0-100%) across all drives with cycle-based offset variation.

        Args:
            dev_str: FIO file content for global section; other jobs will be appended.
            drives: List of drives on the host.
            name: Name of the FIO job.
            cycle: Test cycle number used to vary offset

        Returns:
            FIO content for each job.

        """
        num_drives = len(drives)
        if num_drives == 0:
            return dev_str

        size_per_drive = 100 // num_drives
        remainder = 100 % num_drives

        # Shift offset by 5% per cycle (wraps around at 100%)
        cycle_offset_shift = ((cycle - 1) * 5) % 100

        current_offset = cycle_offset_shift
        for index, device in enumerate(drives):
            fio_device = self._get_fio_device_path(device)

            drive_size = size_per_drive + (1 if index < remainder else 0)

            job_name = f"job{index}"
            job_str = f"\n[{job_name}]\n"
            job_str += f"filename={fio_device}\n"
            job_str += f"size={drive_size}%\n"
            job_str += f"offset={current_offset}%\n"
            job_str += "new_group=1\n"

            dev_str += job_str
            current_offset = (current_offset + drive_size) % 100

        return dev_str

    def create_random_lba_job_content(
        self, dev_str: str, drives: List[Drive], name: str
    ) -> str:
        """Creates content for random LBA read job.

        Uses fixed 1G size with randomized offset % for each drive.

        Args:
            dev_str: FIO file content for global section; other jobs will be appended.
            drives: List of drives on the host.
            name: Name of the FIO job.

        Returns:
            FIO content for each job.

        """
        if len(drives) == 0:
            return dev_str

        for index, device in enumerate(drives):
            fio_device = self._get_fio_device_path(device)

            # Random offset between 0% and 99% (to ensure 1G can fit)
            random_offset = random.randint(0, 99)

            job_name = f"job{index}"
            job_str = f"\n[{job_name}]\n"
            job_str += f"filename={fio_device}\n"
            job_str += "size=1G\n"
            job_str += f"offset={random_offset}%\n"
            job_str += "new_group=1\n"

            dev_str += job_str

        return dev_str

    def _get_fio_device_path(self, device: Drive) -> str:
        """Get the appropriate device path for FIO based on test configuration.

        Args:
            device: Drive object

        Returns:
            Device path to use in FIO job
        """
        if self.test_generic_drives:
            return f"/dev/{getattr(device, 'generic_name', None) or device.block_name}"
        return f"/dev/{device.block_name}"

    def run_qlc_power_cycle_test(self, test_drives, cycle) -> None:
        """Runs QLC power cycle test on the given hosts.

        This method runs fio for the following jobs in sequential order:
        a. write without power trigger
        b. manual power cycle in a loop
        c. verify the above write

        Args:
            test_drives: All drives for the given drive type.
            cycle: No. of test cycle value.

        Raises
        ------
        TestStepError
            When fails to run the FIO job.
        """
        self.validate_no_exception(
            self.qlc_write_io_no_trigger,
            [test_drives, cycle],
            f"Cycle {cycle}: QLC Fio write job completed.",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

        self.validate_no_exception(
            self.qlc_power_cycle_loop,
            [cycle],
            f"Cycle {cycle}: Manual power cycle loop completed.",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

        self.check_block_devices_available()

        self.start_fio_monitor()
        self.validate_no_exception(
            self.qlc_verify_io,
            [test_drives, cycle],
            f"Cycle {cycle}: QLC Fio verify job completed.",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )
        self.stop_fio_monitor()

    def qlc_write_io_no_trigger(self, test_drives, cycle) -> None:
        """Run QLC write FIO jobs without power trigger on the host.

        Args:
           test_drives: All drives for the given drive type.
           cycle: No. of test cycle value.
        """
        self.log_info(f"Cycle {cycle}")
        self.log_info("QLC Write in progress")
        qlc_write_job = self._get_qlc_common_fio_params()
        qlc_write_job.extend(
            [
                "time_based",
                f"runtime={self.qlc_fio_runtime}",
                "verify=crc32",
                "do_verify=1",
                "verify_backlog=1000",
                "verify_state_save=1",
                "verify_async=4",
                "verify_fatal=1",
                "verify_dump=1",
            ]
        )
        self.run_fio(
            qlc_write_job,
            test_drives,
            "qlc_write_no_trigger",
            cycle,
            power_trigger=False,
        )

    def qlc_power_cycle_loop(self, cycle) -> None:
        """Perform qlc power cycle in a loop.

        Args:
           cycle: No. of test cycle value.
        """
        self.log_info(f"Cycle {cycle}")
        self.log_info(
            f"Qlc power cycle loop in progress for {self.num_power_cycles} iterations"
        )

        for i in range(self.num_power_cycles):
            self.log_info(f"Power cycle iteration {i + 1} of {self.num_power_cycles}")
            cmd = f"hwc power_reset {self.host.hostname}"
            AutovalLog.log_info(f"Running command: {cmd}")
            self.host.localhost.run(cmd=cmd)

            if i < self.num_power_cycles - 1:
                self.log_info("Waiting 30 seconds before next power cycle")
                time.sleep(30)

        self.log_info("Performing system health check after final power cycle")
        self.host.reconnect(timeout=2400)
        self.host.check_system_health()
        self.log_info("Qlc power cycle loop completed")

    def format_t10_dix_drives(self) -> None:
        """
        Format the Test drives with T10 dix format 4k+64 lbaf
        """
        t10_dix_format = "4096+64"
        for drive in self.test_drives:
            current_lbaf_details = NvmeResizeUtil.get_lbaf_details(
                self.host, drive.block_name
            )
            if (
                current_lbaf_details.get("ms") == 64
                and current_lbaf_details.get("lbads") == 12
            ):
                AutovalLog.log_info(
                    f"{drive.block_name} already formated to {t10_dix_format}"
                )
                continue

            lbaf_to_flbas_map = NvmeResizeUtil.get_lbaf_to_flbas_map(
                self.host, drive.block_name
            )
            lbaf = lbaf_to_flbas_map.get(t10_dix_format, None)

            AutovalUtils.validate_condition(
                lbaf is not None,
                f"{drive.block_name} supports {t10_dix_format} format",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
                log_on_pass=False,
            )

            AutovalUtils.validate_no_exception(
                NVMeUtils.format_nvme,
                [self.host, drive.block_name, 0, None, f" -l {lbaf}"],
                f"{drive.block_name }: Format with lba {t10_dix_format}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )
