#!/usr/bin/env python3

# pyre-strict

import re
import time
from typing import List

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval_ssd.lib.utils.system_utils import SystemUtils


class BootDrivePartitionUtils:
    """Utility class for managing boot drive partitions for FIO testing.

    This class provides static methods for creating and cleaning up boot drive
    partitions used during FIO testing. It handles:
    - Stale partition cleanup from previous test runs
    - Btrfs filesystem resizing with retry logic
    - Partition creation and deletion using sgdisk
    - Error handling and recovery
    """

    DEFAULT_FIO_PARTITION_SIZE_GB: int = 60
    DEFAULT_MAX_RETRIES: int = 3
    DEFAULT_RETRY_DELAY_SECONDS: int = 20

    @staticmethod
    def create_fio_partition(
        host,
        boot_drive: str,
        partition_size_gb: int = DEFAULT_FIO_PARTITION_SIZE_GB,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: int = DEFAULT_RETRY_DELAY_SECONDS,
    ) -> bool:
        SystemUtils.install_rpms(
            host,
            ["gdisk"],
        )

        AutovalLog.log_info("Checking for stale FIO partitions")
        stale_partitions = BootDrivePartitionUtils._get_stale_fio_partitions(
            host, boot_drive, partition_size_gb
        )
        if stale_partitions:
            AutovalLog.log_info(f"Found {len(stale_partitions)} stale FIO partition(s)")
            BootDrivePartitionUtils._cleanup_stale_fio_partitions(
                host, boot_drive, stale_partitions
            )
        else:
            AutovalLog.log_info("No stale FIO partitions found")

        root_partition_number = BootDrivePartitionUtils._get_root_partition_number(host)
        original_partition_size = BootDrivePartitionUtils._get_partition_size_bytes(
            host, boot_drive, root_partition_number
        )
        partition_size_bytes = partition_size_gb * 1024 * 1024 * 1024
        new_partition_size = int(original_partition_size - partition_size_bytes)
        sector_size = int(
            host.run(f"cat /sys/block/{boot_drive}/queue/logical_block_size")
        )

        if not BootDrivePartitionUtils._resize_btrfs_filesystem(
            host, new_partition_size, max_retries, retry_delay
        ):
            AutovalLog.log_info(
                "Skipping boot drive partition creation due to filesystem resize failure"
            )
            return False

        host.run(f"sgdisk -d {root_partition_number} /dev/{boot_drive}")

        new_size_sectors = int(new_partition_size / sector_size)
        host.run(
            f"sgdisk -n {root_partition_number}:0:+{new_size_sectors}s /dev/{boot_drive}"
        )
        host.run(f"sgdisk -n 0:0:0 /dev/{boot_drive}")
        host.run(f"partprobe /dev/{boot_drive}")

        AutovalUtils.validate_no_exception(
            BootDrivePartitionUtils.get_fio_partition,
            [host, boot_drive, partition_size_gb],
            "Boot drive partition for fio created",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

        AutovalLog.log_info(
            f"Successfully created {partition_size_gb}GB FIO partition on {boot_drive}"
        )
        return True

    @staticmethod
    def cleanup_fio_partition(
        host,
        boot_drive: str,
        partition_size_gb: int = DEFAULT_FIO_PARTITION_SIZE_GB,
    ) -> None:
        root_partition_number = BootDrivePartitionUtils._get_root_partition_number(host)
        fio_partition = BootDrivePartitionUtils.get_fio_partition(
            host, boot_drive, partition_size_gb
        )
        fio_partition_number = int(fio_partition.split("p")[1])

        host.run(f"sgdisk -d {fio_partition_number} /dev/{boot_drive}")
        host.run(f"sgdisk -d {root_partition_number} /dev/{boot_drive}")

        host.run(f"sgdisk -n {root_partition_number}:0:0 /dev/{boot_drive}")
        host.run(f"partprobe /dev/{boot_drive}")

        host.run("btrfs filesystem resize max /")

        AutovalLog.log_info("Boot drive partition for fio deleted")

    @staticmethod
    def get_fio_partition(
        host,
        boot_drive: str,
        partition_size_gb: int = DEFAULT_FIO_PARTITION_SIZE_GB,
    ) -> str:
        fio_partitions = host.run(
            f"sgdisk -p /dev/{boot_drive} 2>/dev/null | "
            f"grep '{partition_size_gb}.0 GiB' | awk '{{print $1}}'",
            ignore_status=True,
        )

        if not fio_partitions.strip():
            raise TestError(
                f"No {partition_size_gb}GB FIO partition found on {boot_drive}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

        partition_numbers = [int(p) for p in fio_partitions.strip().split()]
        latest_partition_num = max(partition_numbers)
        return f"/dev/{boot_drive}p{latest_partition_num}"

    @staticmethod
    def _resize_btrfs_filesystem(
        host,
        new_size: int,
        max_retries: int,
        retry_delay: int,
    ) -> bool:
        for attempt in range(max_retries + 1):
            try:
                host.run(f"btrfs filesystem resize {new_size} /")
                if attempt > 0:
                    AutovalLog.log_info(
                        f"Successfully resized filesystem on attempt {attempt + 1}"
                    )
                return True
            except Exception as e:
                if attempt < max_retries:
                    AutovalLog.log_info(
                        f"btrfs resize attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                        f"Retrying in {retry_delay} seconds..."
                    )
                    time.sleep(retry_delay)
                else:
                    AutovalLog.log_info(
                        f"Unable to resize filesystem after {max_retries + 1} attempts: {e}"
                    )
                    return False

        return False

    @staticmethod
    def _get_root_partition_number(host) -> int:
        root_partition = host.run("df / | grep -E '/dev/' | awk '{print $1}'").strip()

        match = re.match(r"(/dev/.*?)p?(\d+)$", root_partition)
        if not match:
            raise TestError(
                "Could not determine root partition",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

        root_partition_number = int(match.group(2))
        return root_partition_number

    @staticmethod
    def _get_partition_size_bytes(
        host,
        boot_drive: str,
        partition_number: int,
    ) -> int:
        sector_size = int(
            host.run(f"cat /sys/block/{boot_drive}/queue/logical_block_size")
        )

        partition_output = host.run(f"sgdisk -p /dev/{boot_drive} 2>/dev/null")

        for line in partition_output.strip().split("\n"):
            match = re.match(r"\s*(\d+)\s+(\d+)\s+(\d+)\s+", line)
            if match:
                part_num = int(match.group(1))
                if part_num == partition_number:
                    start_sector = int(match.group(2))
                    end_sector = int(match.group(3))
                    size_bytes = (end_sector - start_sector + 1) * sector_size
                    return size_bytes

        raise TestError(
            f"Could not determine size of partition {partition_number} on {boot_drive}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    @staticmethod
    def _get_stale_fio_partitions(
        host,
        boot_drive: str,
        partition_size_gb: int,
    ) -> List[int]:
        root_partition_number = BootDrivePartitionUtils._get_root_partition_number(host)

        partition_info = host.run(
            f"sgdisk -p /dev/{boot_drive} 2>/dev/null | "
            f"grep '{partition_size_gb}.0 GiB' | awk '{{print $1}}'",
            ignore_status=True,
        )

        stale_partitions = []
        if partition_info.strip():
            for partition_num_str in partition_info.strip().split():
                partition_num = int(partition_num_str)
                if partition_num != root_partition_number:
                    stale_partitions.append(partition_num)

        return sorted(stale_partitions, reverse=True)

    @staticmethod
    def _cleanup_stale_fio_partitions(
        host,
        boot_drive: str,
        stale_partitions: List[int],
    ) -> None:
        root_partition_number = BootDrivePartitionUtils._get_root_partition_number(host)

        AutovalLog.log_info(
            f"Cleaning up {len(stale_partitions)} stale FIO partition(s)"
        )

        for partition_num in stale_partitions:
            AutovalLog.log_info(
                f"Deleting stale FIO partition: /dev/{boot_drive}p{partition_num}"
            )
            host.run(
                f"sgdisk -d {partition_num} /dev/{boot_drive}",
                ignore_status=True,
            )

        host.run(f"sgdisk -d {root_partition_number} /dev/{boot_drive}")
        host.run(f"sgdisk -n {root_partition_number}:0:0 /dev/{boot_drive}")

        host.run(f"partprobe /dev/{boot_drive}")
        host.run("btrfs filesystem resize max /")

        AutovalLog.log_info(
            "Successfully cleaned up stale FIO partitions and restored root partition"
        )
