#!/usr/bin/env python3

# pyre-strict

"""
DIX (Data Integrity Extension) utilities for NVMe drives.

This module provides utility functions for DIX test cases, including:
- Validating DIX support on NVMe drives
- Performing DIX namespace resize operations
- Formatting drives with T10 DIX format (4096+64 lbaf)
- Cleaning up DIX configuration after testing

"""

import re
from collections.abc import Iterable, Iterator
from itertools import product
from time import sleep

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.storage.drive import Drive
from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.storage.storage_device_factory import StorageDeviceFactory

ALL_LBAF_FORMATS: list[str] = ["4096+64", "512", "4096"]

T10_DIX_FORMAT: str = "4096+64"
DEFAULT_SWEEP_PARAM_VALUE: int = 75


def get_supported_lbaf_formats(host: Host, drive: Drive) -> set[str]:
    lbaf_to_flbas_map = NvmeResizeUtil.get_lbaf_to_flbas_map(host, drive.block_name)
    return set(lbaf_to_flbas_map.keys())


def get_max_namespaces(host: Host, drive: Drive) -> int:
    id_ctrl = NVMeUtils.get_id_ctrl(host, drive.block_name)
    return int(id_ctrl.get("nn", 1))


def generate_lbaf_combinations(
    host: Host,
    drive: Drive,
    dix_only: bool = True,
) -> Iterator[list[str]]:
    supported_formats = get_supported_lbaf_formats(host, drive)
    max_ns = get_max_namespaces(host, drive)

    known_formats = set(ALL_LBAF_FORMATS)
    available_formats = list(supported_formats & known_formats)

    format_priority = {T10_DIX_FORMAT: 0, "4096": 1, "512": 2}
    available_formats.sort(key=lambda x: format_priority.get(x, 99))

    AutovalLog.log_info(f"Drive support formats={available_formats}, max_ns={max_ns}")

    if max_ns > 1:
        if dix_only:
            if T10_DIX_FORMAT in available_formats:
                for fmt in available_formats:
                    yield [T10_DIX_FORMAT, fmt]
        else:
            for combo in product(available_formats, repeat=2):
                yield list(combo)
    else:
        for fmt in available_formats:
            yield [fmt]


def validate_dix_support(
    host: Host, drives: list[Drive], warning: bool = False
) -> dict[str, int] | None:
    AutovalLog.log_info("Validating DIX support on drives")
    return NvmeResizeUtil.validate_drives_support_dix_resize_lba_formats(
        host, drives, required_formats={T10_DIX_FORMAT}, warning=warning
    )


def dix_ns_resize_single(
    host: Host,
    drives: list[Drive],
    combination: list[str],
    lbaf_to_flbas_map: dict[str, int],
    sweep_param_value: int | float = DEFAULT_SWEEP_PARAM_VALUE,
    cycle: int = 1,
    nvme_id_ctrl_filter: str = "True",
    use_existing_ns: bool = False,
    sleep_after_resize: int = 5,
) -> None:
    sweep_param_key = NvmeResizeUtil.SweepParamKeyEnum["overprovisioning"]
    sweep_param_unit = NvmeResizeUtil.SweepParamUnitEnum["percent"]

    NvmeResizeUtil.perform_resize(
        host,
        drives,  # pyrefly: ignore [bad-argument-type]
        sweep_param_key=sweep_param_key,
        sweep_param_unit=sweep_param_unit,
        sweep_param_value=sweep_param_value,
        cycle=cycle,
        combination=combination,
        lbaf_to_flbas_map=lbaf_to_flbas_map,
        use_existing_ns=use_existing_ns,
        nvme_id_ctrl_filter=nvme_id_ctrl_filter,
    )

    sleep(sleep_after_resize)


def _wipe_drive_signatures(host: Host, block_name: str) -> None:
    host.run(
        cmd=f"wipefs --all --force /dev/{block_name}",
        ignore_status=True,
    )


def format_t10_dix_drives(
    host: Host,
    drives: list[Drive],
) -> None:
    AutovalLog.log_info("Formatting drives with T10 DIX format (4096+64)")
    t10_dix_format = T10_DIX_FORMAT

    for drive in drives:
        if is_drive_dix_formatted(host, drive):
            AutovalLog.log_info(
                f"{drive.block_name} already formatted to {t10_dix_format}"
            )
            continue

        lbaf_to_flbas_map = NvmeResizeUtil.get_lbaf_to_flbas_map(host, drive.block_name)
        lbaf = lbaf_to_flbas_map.get(t10_dix_format)

        AutovalUtils.validate_condition(
            lbaf is not None,
            f"{drive.block_name} supports {t10_dix_format} format",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
            log_on_pass=False,
        )

        _wipe_drive_signatures(host, drive.block_name)

        AutovalUtils.validate_no_exception(
            NVMeUtils.format_nvme,
            [host, drive.block_name, 0, None, f" -l {lbaf}"],
            f"{drive.block_name}: Format with LBA {t10_dix_format}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )


def dix_cleanup(
    host: Host,
    drives: list[Drive],
    original_lbaf: str = "4096",
) -> None:
    AutovalLog.log_info(f"Restoring drives to original LBA format: {original_lbaf}")

    for drive in drives:
        lbaf_to_flbas_map = NvmeResizeUtil.get_lbaf_to_flbas_map(host, drive.block_name)
        lbaf = lbaf_to_flbas_map.get(original_lbaf)

        if lbaf is None:
            AutovalLog.log_info(
                f"{drive.block_name} does not support {original_lbaf} format, skipping cleanup"
            )
            continue

        _wipe_drive_signatures(host, drive.block_name)

        AutovalUtils.validate_no_exception(
            NVMeUtils.format_nvme,
            [host, drive.block_name, 0, None, f" -l {lbaf}"],
            f"{drive.block_name}: Restore to LBA {original_lbaf}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        AutovalLog.log_info(
            f"{drive.block_name} restored to {original_lbaf} successfully"
        )


def is_drive_dix_formatted(host: Host, drive: Drive) -> bool:
    current_lbaf_details = NvmeResizeUtil.get_lbaf_details(host, drive.block_name)
    return (
        current_lbaf_details.get("ms") == 64 and current_lbaf_details.get("lbads") == 12
    )


def filter_drives_by_controllers(
    drives: list[Drive], controllers: set[str]
) -> Iterator[Drive]:
    for drive in drives:
        for controller in controllers:
            if re.match(rf"^{re.escape(controller)}n\d+$", drive.block_name):
                yield drive
                break


def rescan_nvme_drives(
    host: Host,
    original_drives: list[Drive] | None = None,
    exclude_boot: bool = True,
) -> list[Drive]:
    nvme_list = NVMeUtils.get_nvme_list(host)
    drive_names = [entry["DevicePath"].replace("/dev/", "") for entry in nvme_list]

    if exclude_boot:
        boot_drive = DiskUtils.get_boot_drive(host)
        if boot_drive:
            drive_names = [d for d in drive_names if d != boot_drive]

    drives = StorageDeviceFactory(host, drive_names, None).create()

    if original_drives:
        original_controllers = set()
        for orig in original_drives:
            match = re.match(r"(nvme\d+)n\d+", orig.block_name)
            if match:
                original_controllers.add(match.group(1))

        drives = list(filter_drives_by_controllers(drives, original_controllers))

    AutovalLog.log_info(f"Rescanned NVMe drives: {[d.block_name for d in drives]}")
    return drives


def dix_ns_resize_loop(
    host: Host,
    drives: list[Drive],
    lbaf_combinations: list[list[str]] | None = None,
    sweep_param_value: int | float = DEFAULT_SWEEP_PARAM_VALUE,
    cycle: int = 1,
    dix_only: bool = True,
    nvme_id_ctrl_filter: str = "True",
    sleep_after_resize: int = 5,
    warning: bool = False,
) -> Iterable[list[Drive]]:
    lbaf_to_flbas_map = validate_dix_support(host, drives, warning=warning)
    if lbaf_to_flbas_map is None:
        AutovalLog.log_info(
            "DIX support validation skipped (warning=True). "
            "Skipping DIX namespace resize loop."
        )
        return

    if not lbaf_combinations:
        lbaf_combinations = list(
            generate_lbaf_combinations(host, drives[0], dix_only=dix_only)
        )

    original_drives = drives
    current_drives = drives

    for resize_cycle, combo in enumerate(lbaf_combinations):
        AutovalLog.log_info(
            f"Starting DIX resize cycle {resize_cycle + 1}/{len(lbaf_combinations)} "
            f"with combination {combo}"
        )

        dix_ns_resize_single(
            host,
            current_drives,
            combination=combo,
            lbaf_to_flbas_map=lbaf_to_flbas_map,
            sweep_param_value=sweep_param_value,
            cycle=cycle,
            nvme_id_ctrl_filter=nvme_id_ctrl_filter,
            use_existing_ns=(resize_cycle != 0),
            sleep_after_resize=sleep_after_resize,
        )

        current_drives = rescan_nvme_drives(host, original_drives)
        AutovalLog.log_info(f"DIX resize cycle {resize_cycle + 1} completed")

        yield current_drives
