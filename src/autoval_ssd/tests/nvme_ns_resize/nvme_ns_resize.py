#!/usr/bin/env python3

# pyre-unsafe
"""Nvme namespace resize test"""
from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil
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
            for sweep_param_value in self.sweep_param_values:
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
            self.log_info(f"Cycle {_cycle} completed")

    def _fio_setup_after_ns_recreate(self) -> None:
        """
        Get the drive list and setup the Fio after ns_resize.
        """
        self.test_control["drives"] = self.test_drives
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
