#!/usr/bin/env python3

# pyre-unsafe
"""Nvme namespace resize test"""

from time import sleep
from typing import Any, Dict, List, Optional, Union

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.storage.drive import Drive
from autoval_ssd.lib.utils.storage.drive_fw_update_util import DriveFwUpdateUtil
from autoval_ssd.lib.utils.storage.nvme.fdp_utils import FDPUtils
from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase


class NvmeNSResize(StorageTestBase):
    """
    Verify NVMe create-ns command with namespaces with a variety of sizes.
    Run NVME id-ns to double check the set nsze.
    Run FIO to ensure IOs can be issued to the new namespace.

    Assumptions: one NS per controller,  no thin provisioning, ie nsze = ncap,
                4K block size

    Required test control json inputs:
        sweep_param_key: enum member name from SweepParamKeyEnum
        sweep_param_unit: enum member name from SweepParamUnitEnum
        sweep_param_values: list of integers representing sweep values

    Optional test control json inputs:
        nvme_id_ctrl_filter: evaluatable string that can be used to add an inclusion
            criterion on nvme_drives for that particular control file, based
            on nvme id-ctrl attribute checks. The condition should be expressed
            assuming id-ctrl json is present in var nvme_id_ctrl.
            e.g. to only include drives > 500G (536870912000 bytes) in tnvmcap,
            we would have the following in test control json
            {
            "nvme_id_ctrl_filter": "nvme_id_ctrl[\"tnvmcap\"] >= 536870912000",
            ...}
        cycle_count: number of times to repeat each test
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        try:
            self.sweep_param_key: "NvmeResizeUtil.SweepParamKeyEnum" = (
                NvmeResizeUtil.SweepParamKeyEnum[
                    self.test_control.get("sweep_param_key")
                ]
            )
            self.sweep_param_unit: "NvmeResizeUtil.SweepParamUnitEnum" = (
                NvmeResizeUtil.SweepParamUnitEnum[
                    self.test_control.get("sweep_param_unit")
                ]
            )

        except KeyError as exc:
            raise TestError(
                f"Invalid/Missing sweep param in test_control: {str(exc)}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.INPUT_ERR,
            )
        self.sweep_param_values = self.test_control.get("sweep_param_values", [])
        self.nvme_id_ctrl_filter: str = self.test_control.get(
            "nvme_id_ctrl_filter", "True"
        )
        self.cycle = self.test_control.get("cycle_count", 1)
        # Placehold dictionary to store nvme device to id-ctrl mapping
        self.nvme_id_ctrls = {}
        self.dix_ns_resize: bool = self.test_control.get("dix_ns_resize", False)
        self.workloads: Dict[str, Dict[str, Dict[str, Any]]] = self.test_control.get(
            "workloads", {}
        )
        self.validate_tooling: bool = self.test_control.get("validate_tooling", False)
        self.lbaf_combinations: List[List[str]] = self.test_control.get(
            "lbaf_combinations", []
        )
        self.validate_drive_fw_update: bool = self.test_control.get(
            "validate_drive_fw_update", False
        )
        self.fdp_setup: bool = self.test_control.get("fdp_setup", False)
        self.fdp_enabled: bool = False

    def execute(self) -> None:
        """
        This function performs the following steps:
        1. Gets the nvmcap for the test drives using NvmeResizeUtil.get_nvmcap()
        2. Gets the nvme_id_ctrls for the test drives using NvmeResizeUtil.get_nvme_ctrls()
        3. For each cycle (1 to self.cycle), it does the following:
            3.1. Performs a resize operation on the test drives using NvmeResizeUtil.perform_resize()
            3.2. Sets up FIO after NS recreate using self._fio_setup_after_ns_recreate()
            3.3. Validates that the FIO run completes without any exceptions using self.validate_no_exception()
        4. Logs information about the completion of each cycle.
        """
        self.before_resize_nvmecap = NvmeResizeUtil.get_nvmcap(
            self.host, self.test_drives
        )
        self.nvme_id_ctrls = NvmeResizeUtil.get_nvme_ctrls(
            self.host, self.test_drives, nvme_id_ctrl_filter="True"
        )
        for _cycle in range(1, self.cycle + 1):
            self.log_info(f"Starting cycle {_cycle}")

            if self.fdp_setup:
                self.run_fdp_workflow()

            else:
                for resize_cycle, sweep_param_value in enumerate(
                    self.sweep_param_values
                ):
                    if self.dix_ns_resize:
                        self.run_dix_ns_resize(sweep_param_value)
                    else:
                        self.run_standard_resize(resize_cycle, sweep_param_value)
            self.log_info(f"Cycle {_cycle} completed")

    def run_standard_resize(
        self, resize_cycle: int, sweep_param_value: Union[int, float]
    ) -> None:
        """
        This function performs the following steps:
            1. Performs a resize operation on the test drives
            2. Sets up FIO after NS recreate
            3. Validates that the FIO run completes without any exceptions

        Args:
            resize_cycle: The current resize cycle number.
            sweep_param_value: The value of the sweep parameter used in the current resize cycle.
        """

        self.log_info(f"Starting resize cycle {resize_cycle+1}")
        NvmeResizeUtil.perform_resize(
            self.host,
            self.test_drives,
            sweep_param_key=self.sweep_param_key,
            sweep_param_unit=self.sweep_param_unit,
            sweep_param_value=sweep_param_value,
            nvme_id_ctrl_filter=self.nvme_id_ctrl_filter,
            cycle=self.cycle,
        )
        self._fio_setup_after_ns_recreate()
        self.validate_no_exception(
            self.fio_runner.start_test,
            [],
            "Fio run",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

    def run_dix_ns_resize(self, sweep_param_value: Union[int, float]) -> None:
        """
        This function performs the following steps:
            1. Validates that the test drives support the required LBAF for Dix resize.
            2. Performs a resize operation on the test drives using labaf combinations.
            3. When validate_tooling is set to True, it performs filesystem validation on the test drives.
            4. Otherwise, it verifies data integrity on the test drives.
            5. If validate_drive_fw_update is set to True, it performs firmware update on the test drives.

        Args:
            sweep_param_value: The value of the sweep parameter used in the current resize cycle.
        """

        lbaf_to_flbas_map = (
            NvmeResizeUtil.validate_drives_support_dix_resize_lba_formats(
                self.host, self.test_drives
            )
        )
        self.log_info(f"lbaf to flbas map {lbaf_to_flbas_map}")
        if not self.lbaf_combinations:
            self.lbaf_combinations = [
                ["4096", "4096"],
                ["4096", "512"],
                ["4096", "4096+64"],
                ["512", "512"],
                ["512", "4096"],
                ["512", "4096+64"],
                ["4096+64", "4096+64"],
                ["4096+64", "512"],
                ["4096+64", "4096"],
            ]

        dix_test_drives = self.test_drives
        for combo_resize_cycle, combo in enumerate(self.lbaf_combinations):
            self.log_info(
                f"Starting lbaf combo resize cycle {combo_resize_cycle+1} with combination {combo}"
            )

            NvmeResizeUtil.perform_resize(
                self.host,
                dix_test_drives,
                sweep_param_key=self.sweep_param_key,
                sweep_param_unit=self.sweep_param_unit,
                sweep_param_value=sweep_param_value,
                nvme_id_ctrl_filter=self.nvme_id_ctrl_filter,
                combination=combo,
                lbaf_to_flbas_map=lbaf_to_flbas_map,
                use_existing_ns=(combo_resize_cycle != 0),
            )
            sleep(5)

            dix_drive_list = self.get_drive_list(self.boot_drive)
            dix_drives = self.scan_drives()
            dix_test_drives = self.allocate_test_drives(dix_drives)

            if self.validate_tooling:
                self.tooling_filesystem_validation(dix_test_drives, dix_drive_list)
            else:
                self.verify_data_integrity(dix_test_drives, dix_drive_list)

            if self.validate_drive_fw_update:
                drive_fw_updater = DriveFwUpdateUtil(self.host, self.test_control)
                for drive in self.test_drives:
                    drive_fw_updater.test_firmware_update(drive, "latest")

    def run_fdp_workflow(self) -> None:
        """
        This function performs the following steps:
            1. Validates FDP support on the test drives and set up FDP.
            2. When validate_tooling is set to True, it performs filesystem validation
            3. Otherwise, it sets up FIO after NS recreate and validates that the FIO run completes without any exceptions
        """
        FDPUtils.validate_fdp_support(self.host, self.nvme_id_ctrls)
        FDPUtils.fdp_setup(self.host, self.nvme_id_ctrls)
        AutovalLog.log_info(
            "FDP setup completed\n NVME LIST\n" + self.host.run("nvme list")
        )
        self.fdp_enabled = True

        if self.validate_tooling:
            self.tooling_filesystem_validation(
                self.test_drives, self.get_drive_list(self.boot_drive)
            )
        else:
            self.verify_data_integrity(
                self.test_drives, self.get_drive_list(self.boot_drive)
            )

        if self.validate_drive_fw_update:
            drive_fw_updater = DriveFwUpdateUtil(self.host, self.test_control)
            for drive in self.test_drives:
                drive_fw_updater.test_firmware_update(drive, "latest")

    def verify_data_integrity(
        self, test_drives: List[Drive], drive_list: List[str]
    ) -> None:
        """
        This method peforms the following steps:
            1. Iterates through defined workloads.
            2. Sets up Fio after namespace recreation.
            3. Starts Fio tests.
            4. Validates that the block devices list has not changed after fio run.
            5. Logs namespace usage.
        Args:
            test_drives: A list of drives to perform data integrity verification on.
            drive_list: A list of drive identifiers to check for block device availability.
        Raises:
            TestError: If any operation within the verification process fails, including Fio setup, run, or block device checks.
        """
        for wkld_name, wkld in self.workloads.items():
            AutovalLog.log_info(f"Starting fio {wkld_name}")
            self.test_control["power_trigger"] = wkld_name == "write"
            self._fio_setup_after_ns_recreate(test_drives, wkld)
            self.validate_no_exception(
                self.fio_runner.start_test,
                [],
                "Fio run",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )

            self.check_block_devices_available(drive_list)
            self.log_namespace_usage(test_drives)

    def tooling_filesystem_validation(
        self, test_drives: List[Drive], drive_list: List[str]
    ) -> None:
        """
        This function peforms the following steps:
            1. Runs fio setup after namespace recreation to create the filesystem specified on each namespace.
            2. Starts a Fio test on the filesystem.
            3. Validates the block devices list has not changed.
            4. Performs fio clean up after running the Fio test, which removes and unmounts the filesystems that were created.
            5. Logs namespace usage before and after formatting the drives.
        Args:
            test_drives: A list of drives on which to perform the filesystem validation.
            drive_list: A list of drive identifiers to check for block device availability.

        Raises:
            TestError: If any operation within the validation process fails, including Fio setup, Fio start, Fio cleanup,
                       block device availability check, or NVMe formatting.
        """
        filesystem_types = ["xfs", "ext4", "btrfs"]
        for filesystem_type in filesystem_types:
            self.test_control["run_definition"]["filesystem_io"].update(
                {
                    "filesystem": True,
                    "filesystem_type": filesystem_type,
                }
            )
            self._fio_setup_after_ns_recreate(test_drives)
            self.validate_no_exception(
                self.fio_runner.start_test,
                [],
                "Fio run",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )

            self.check_block_devices_available(drive_list)
            self.validate_no_exception(
                self.fio_runner.test_cleanup,
                [],
                "Fio cleanup",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )

            self.log_namespace_usage(test_drives)
            for drive in test_drives:
                self.validate_no_exception(
                    NVMeUtils.format_nvme,
                    [self.host, drive, 2],
                    "NVME Formatting on device %s" % (drive),
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.NVME_ERR,
                )
            self.log_namespace_usage(test_drives)

    def log_namespace_usage(self, drives: List[Drive]) -> None:
        """
        Logs the namespace usage for each drive in the drives list.

        Args:
            drives: A list of drives to log the namespace usage for.
        """

        for drive in drives:
            self.log_info(f"{drive}: nuse: {drive.get_size('nuse')}")  # pyre-ignore

    def _fio_setup_after_ns_recreate(
        self,
        drives: Optional[List[Drive]] = None,
        workload: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        """
        Get the drive list and setup the Fio after ns_resize.

        Args:
            drives: A list of drives to run FIO during DIX resize test
            workload: A dictionary of workload to run FIO

        """
        self.test_control["drives"] = self.test_drives
        if self.dix_ns_resize and drives:
            self.test_control["drives"] = drives
        if workload:
            self.test_control["run_definition"] = workload
        if self.boot_drive:
            self.test_control["boot_drive"] = self.boot_drive
        self.fio_runner = FioRunner(self.host, self.test_control)
        self.validate_no_exception(
            self.fio_runner.test_setup,
            [],
            "Fio setup()",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

    def cleanup(self, *args, **kwargs) -> None:
        """
        This function performs the following steps:
        1. If test_drives is not empty, it does the following:
            1.1. Sets self.sweep_param_key to usercapacity and self.sweep_param_unit to num_bytes
            1.1. Sets the sweep_param_value to 0 (to reset the namespace to the original capacity)
            1.2. Creates a queue of threads to perform ns_resize operation on each device using NvmeResizeUtil.ns_resize()
            1.3. Waits for all the threads in the queue to complete
            1.4. Logs the nvme list after cleanup
        2. Calls the parent class's cleanup method with the given arguments.
        """
        if self.test_drives:
            self.sweep_param_key: "NvmeResizeUtil.SweepParamKeyEnum" = (
                NvmeResizeUtil.SweepParamKeyEnum["overprovisioning"]
            )
            self.sweep_param_unit: "NvmeResizeUtil.SweepParamUnitEnum" = (
                NvmeResizeUtil.SweepParamUnitEnum["percent"]
            )

            sweep_param_value = NvmeResizeUtil.DEFAULT_OP_PERCENT
            ns_validate_queue = []

            if self.fdp_enabled:
                FDPUtils.fdp_cleanup(self.host, self.nvme_id_ctrls)

            else:
                for device in self.nvme_id_ctrls:
                    ns_validate_queue.append(
                        AutovalThread.start_autoval_thread(
                            NvmeResizeUtil.ns_resize,
                            self.host,
                            self.nvme_id_ctrls,
                            self.sweep_param_unit,
                            self.sweep_param_key,
                            device,
                            sweep_param_value,
                        )
                    )
                    if ns_validate_queue:
                        AutovalThread.wait_for_autoval_thread(ns_validate_queue)
            AutovalLog.log_info(
                "NVME LIST AFTER CLEANUP\n" + self.host.run("nvme list")
            )

        super().cleanup(*args, **kwargs)
