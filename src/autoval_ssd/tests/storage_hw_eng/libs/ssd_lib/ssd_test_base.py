# pyre-strict
from __future__ import annotations

from typing import Any, Iterable

import pandas as pd
from autoval.lib.host.component.component import COMPONENT
from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import CmdError, TestError
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.decorators import retry
from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.storage.drive import Drive, DriveType
from autoval_ssd.lib.utils.storage.nvme import dix_utils
from autoval_ssd.lib.utils.storage.nvme.fdp_utils import FDPUtils
from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.storage.storage_device_factory import StorageDeviceFactory
from autoval_ssd.lib.utils.system_utils import SystemUtils
from autoval_ssd.tests.storage_hw_eng.libs.component_common_lib.component_test_base import (
    ComponentTestBase,
)
from autoval_ssd.tests.storage_hw_eng.libs.data_types.dmesg_record import Dmesg
from autoval_ssd.tests.storage_hw_eng.libs.data_types.drive_record import SSDDriveRecord
from autoval_ssd.tests.storage_hw_eng.libs.ext_test_base.tasks import TestTask

from .ssd_data_base import SSDTestInputBase, SSDTestOutputBase
from .ssd_dmesg_check import DmesgCheckSSD

# { TB Capacity : Power State } mapping for performance testing and these values are based on E1.S 25mm and U.2 form factors.
DRIVE_CAPACITY_POWER_STATES = {
    1: 8,
    2: 7,
    4: 6,
    8: 5,
    16: 2,
}


class SSDTestBase(ComponentTestBase):
    """
    The SSD Test base.
    """

    def __init__(
        self,
        inputT: type[SSDTestInputBase] = SSDTestInputBase,
        outputT: type[SSDTestOutputBase] = SSDTestOutputBase,
        **kwargs: Any,
    ) -> None:
        if not issubclass(inputT, SSDTestInputBase):
            TestError(
                f"Type {inputT} is not a subclass of {SSDTestInputBase}!"
                " The SSD Test base requires that the input type be a subclass."
            )
        if not issubclass(outputT, SSDTestOutputBase):
            TestError(
                f"Type {outputT} is not a subclass of {SSDTestOutputBase}!"
                " The SSD Test base requires that the output type be a subclass."
            )
        super().__init__(inputT=inputT, outputT=outputT, **kwargs)
        self.test_results: object = []
        self.pre_run_smartlog_data: object = None
        self.cleanup_test_drives: list[Drive] = []
        self.test_specific_drives: list[Drive] = []
        self.test_drives: list[Drive] = []
        self.run_entry: list[object] = []
        self.nvme_id_ctrl_filter: str = self.test_control.get(
            "nvme_id_ctrl_filter", "True"
        )

        self.collect_smart_log: bool = self.test_control.get("collect_smart_log", True)
        self.collect_drive_data: bool = self.test_control.get(
            "collect_drive_data", True
        )
        self.drive_interface: str | None = self.test_control.get(
            "drive_interface", None
        )
        self.drive_type: str | None = self.test_control.get("drive_type", None)
        self.disable_tools_upgrade: object = self.test_control.get(
            "disable_tools_upgrade", None
        )
        self.lbaf_combinations: list[list[str]] = self.test_control.get(
            "lbaf_combinations", []
        )
        self.dix_ns_resize: bool = self.test_control.get("dix_ns_resize", False)
        self.dix_warning: bool = self.test_control.get("dix_warning", True)
        self.dix_enabled = False
        self.lba_format: str | None = self.test_control.get("lba_format", None)
        self.hypernode: bool = self.test_control.get("hypernode", False)
        self.fdp_setup: str | None = self.test_control.get("fdp_setup", None)
        self.fdp_cleanup: bool = self.test_control.get("fdp_cleanup", False)
        self.fdp_enabled = False
        self.nvme_version: str | None = self.test_control.get("nvme_version", None)
        self.drives_filter: list[str] = self.test_control.get("drives", [])
        self.fio_synth_flash_version: str | None = self.test_control.get(
            "fio_synth_flash_version", None
        )
        self.only_boot_drive: bool = self.test_control.get("only_boot_drive", False)
        self.drive_models: list[str] = self.test_control.get("drive_models", [])

    def setup(self, **kwargs: Any) -> None:
        """
        Setup for the HDD Tests.
        """
        super().setup(**kwargs)

        if self.nvme_version:
            SystemUtils.install_rpms(
                self.host,  # pyrefly: ignore [bad-argument-type]
                [self.nvme_version],
                force_install=True,
            )
        self.log_info(
            f"Running test with Nvme Version: {NVMeUtils.get_nvme_version(self.host)}"
        )

        if self.only_boot_drive:
            boot_drive_str = DiskUtils.get_boot_drive(self.host)
            self.log_info(f"Only testing boot drive: {boot_drive_str}")
            drive_list = [boot_drive_str]
            self.data_ssds = self.get_all_ssds(self.collect_drive_data, no_boot=False)
            self.test_drives = StorageDeviceFactory(
                self.host,  # pyrefly: ignore [bad-argument-type]
                drive_list,
                None,
            ).create()

        else:
            # Get all SSDs
            self.data_ssds = self.get_all_ssds(self.collect_drive_data, no_boot=True)
            if len(self.data_ssds) == 0:
                self.log_info("Found No Testable NVMe Drives.")
                return

            # Create Drive objects from all SSDs
            drive_list = [
                drive_name[5:] for drive_name in self.data_ssds.devname.tolist()
            ]
            drive_objects = StorageDeviceFactory(
                self.host,  # pyrefly: ignore [bad-argument-type]
                drive_list,
                None,
            ).create()

            if self.drive_models:
                filtered_drives = [
                    drive for drive in drive_objects if drive.model in self.drive_models
                ]

                if not filtered_drives:
                    available_models = [drive.model for drive in drive_objects]
                    self.log_info(
                        f"No drives found matching models: {self.drive_models}. "
                        f"Available models: {available_models}"
                    )
                    return

                filtered_devnames = [
                    f"/dev/{drive.block_name}" for drive in filtered_drives
                ]
                self.data_ssds = self.data_ssds[
                    self.data_ssds.devname.isin(filtered_devnames)
                ]
                self.test_drives = filtered_drives
            else:
                self.test_drives = drive_objects

            self.log_info(
                f"Found {len(self.data_ssds.devname.unique())} unique devices to test on."
            )

            drive_str = ", ".join(list(self.data_ssds.devname))
            self.log_info(f"Excutable drives: {drive_str}")

            # Set all wr cache correctly
            self.set_multi_ssd_wr_cache(
                devnames=list(self.data_ssds.devname), enable=self.input_params.wr_cache
            )
        self.nvme_id_ctrls = NvmeResizeUtil.get_nvme_ctrls(
            self.host,
            self.test_drives,
            self.nvme_id_ctrl_filter,
        )
        tnvmcap = self.nvme_id_ctrls[str(self.test_drives[0])[:-2]]["tnvmcap"]
        _, TB_capacity = NvmeResizeUtil.get_reported_capacity(tnvmcap)
        self.drive_capacity_power_state = DRIVE_CAPACITY_POWER_STATES.get(
            TB_capacity, None
        )
        if self.drive_capacity_power_state is None:
            # None is a valid sentinel meaning "no known power-state mapping".
            # Callers must handle it; set_power_state already does.
            self.log_warning(
                f"No power-state mapping for drive capacity {TB_capacity}TB; "
                "drive_capacity_power_state set to None"
            )
        self.boot_drive = self.test_drives[0] if self.only_boot_drive else None

    def execute(self) -> None:
        """
        Execute function for the SSD Test Base.
        """

    def cleanup(self, **kwargs: Any) -> None:
        """
        This is the cleanup function. This will be called after the execute function.
        Note that this will be called regardless of pass condition on execute.
        """

        # Call super with if are any kwargs
        if self._debug:
            super().cleanup(config_check=False)
        else:
            super().cleanup(**kwargs)

    def check_dmesg_errors(self, dmesg: Dmesg) -> list[tuple[Any, ...]]:
        """
        Checks the dmesg for a particular set of errors.
        """
        checker = DmesgCheckSSD()
        return checker.check(dmesg, ts_only=False)

    @retry(3, 5)
    def get_nvme_smartlog(
        self,
        *,
        drive: SSDDriveRecord,
        check_input_param: bool = False,
    ) -> dict[str, Any] | None:
        """
        Gets smartlog for a drive from a host.

        Params:
        drive (SSDDriveRecord):
            The drive to get the NVME smartlogs from.

        Return:
        The Smartlog output.
        """
        if drive.drive_obj is None or drive.drive_type is not DriveType.SSD:
            return {}
        # pyre-fixme[16]: `Drive` has no attribute `get_smart_log` - NVMeDrive subclass has this method
        return drive.drive_obj.get_smart_log()

    def get_all_ssds(
        self,
        collect_drive_data: bool,
        host: Host | None = None,
        no_boot: bool = True,
    ) -> pd.DataFrame:
        """
        Gets all of the SSDs on a hosts.
        """

        host = self._default_host_if_none(host)

        devnames = None
        if self.drives_filter:
            self.log_info(f"Using drives from test control: {self.drives_filter}")
            devnames = [
                d if d.startswith("/dev/") else f"/dev/{d}" for d in self.drives_filter
            ]

        self.log_info("Getting SSDs.")
        drives = SSDDriveRecord.get_mounted_SSD_drives(
            # pyrefly: ignore [bad-argument-type]
            host,
            collect_drive_data,
            devnames=devnames,
            logger=self.log_info,
        )
        bootDrive = DiskUtils.get_boot_drive(host)
        if bootDrive == "":
            bootDrive = "No boot drives detected"
            self.log_info("No boot drives detected")
        self.log_info("Boot Drives are:")
        self.log_info(bootDrive)
        if no_boot:
            drives = [drive for drive in drives if bootDrive not in drive.devname]

        records = [drive.to_dataframe_record(add_self="drive_obj") for drive in drives]
        df = pd.DataFrame(records)

        return df

    def check_if_bootdrive(self, devname: str, host: Host | None = None) -> bool:
        """
        Checks if a drive is the bootdrive via looking for /boot
        """
        host = self._default_host_if_none(host)
        # pyrefly: ignore [missing-attribute]
        num = host.run(f"lsblk {devname} | grep /boot | wc -l")
        return int(num) > 0

    def set_multi_ssd_wr_cache(
        self,
        *,
        devnames: list[str],
        host: Host | None = None,
        enable: bool = True,
    ) -> object:
        """
        Sets the write cache of multiple ssds. Multi-threaded.
        """
        self.log_info(f"Setting multiple write caches on SSDs to {enable}.")
        return self.operate_on_devnames(
            task=TestTask(func=self.set_ssd_wr_cache, kwargs={"enable": enable}),
            host=host,
            devnames=devnames,
        )

    def set_ssd_wr_cache(
        self, *, devname: str, host: Host | None = None, enable: bool = True
    ) -> bool:
        """
        Sets the write cache on a ssd by devicename and host.
        """
        host = self._default_host_if_none(host)
        devname = self.format_devname(devname, to_full_path=False)

        if enable:
            self.log_info(
                # pyrefly: ignore [missing-attribute]
                f"Attempting to enable write cache on {devname} on host {host.hostname}"
            )
            NVMeUtils.enable_write_cache(host, devname)
            return NVMeUtils.get_write_cache(host, devname) == 1
        else:
            self.log_info(
                # pyrefly: ignore [missing-attribute]
                f"Attempting to disable write cache on {devname} on host {host.hostname}"
            )
            NVMeUtils.disable_write_cache(host, devname)
            return NVMeUtils.get_write_cache(host, devname) == 0

    def entry_get_nvme_log(
        self, drive: SSDDriveRecord, msgs: list[str]
    ) -> dict[str, Any] | None:
        if drive.drive_obj is not None:
            try:
                # pyre-fixme[16]: `Drive` has no attribute `get_smart_log` - NVMeDrive subclass has this method
                return drive.drive_obj.get_smart_log()
            except CmdError as e:
                msg = f"Failed to get final nvme smartlogs for {drive.devname} on {drive.hostname} - {type(e)}:{e}."

        else:
            msg = f"Failed to get final nvme smartlogs for {drive.devname} on {drive.hostname} - drive obj is None."

        self.log_info(msg)
        msgs.append(msg)
        return None

    def fdp_single_namespace_setup(self) -> None:
        """
        Set up a single namespace with 4k LBA format and FDP enabled on the test drives.

        Raises:
            TestError: If FDP support validation fails.
        """
        wait_for_ns_ready = self.test_control.get("wait_for_ns_ready", False)
        fdp_warning = self.test_control.get("fdp_warning", True)

        # Check if FDP is already enabled on all drives
        all_fdp_enabled = True
        for device in self.nvme_id_ctrls:
            if not NVMeUtils.get_fdp_status(self.host, device):
                all_fdp_enabled = False
                break

        if all_fdp_enabled:
            self.log_info("FDP is already enabled on all drives, skipping FDP setup")
            # pyrefly: ignore [missing-attribute]
            self.log_info("NVME LIST\n" + self.host.run("nvme list"))
            self.fdp_enabled = True
            return

        if not FDPUtils.validate_fdp_support(
            # pyrefly: ignore [bad-argument-type]
            self.host,
            self.nvme_id_ctrls,
            warning=fdp_warning,
        ):
            return

        # FDP supported, perform setup
        # pyrefly: ignore [bad-argument-type]
        FDPUtils.fdp_setup(self.host, self.nvme_id_ctrls, wait_for_ns_ready)
        # pyrefly: ignore [missing-attribute]
        self.log_info("FDP setup completed\n NVME LIST\n" + self.host.run("nvme list"))
        self.fdp_enabled = True
        self.performed_resize = True

    def dix_ns_resize_setup(
        self,
        drives: list[Drive] | None = None,
        dix_only: bool = True,
        sweep_param_value: int | float | None = None,
    ) -> Iterable[list[Drive]]:
        target_drives = drives if drives is not None else self.test_specific_drives
        lbaf_combinations = self.lbaf_combinations if self.lbaf_combinations else None
        sweep_value = (
            sweep_param_value
            if sweep_param_value is not None
            else dix_utils.DEFAULT_SWEEP_PARAM_VALUE
        )

        yielded = False
        for dix_test_drives in dix_utils.dix_ns_resize_loop(
            # pyrefly: ignore [bad-argument-type]
            self.host,
            target_drives,
            lbaf_combinations=lbaf_combinations,
            sweep_param_value=sweep_value,
            cycle=self.cycle,
            dix_only=dix_only,
            nvme_id_ctrl_filter=self.nvme_id_ctrl_filter,
            warning=self.dix_warning,
        ):
            if not yielded:
                self.dix_enabled = True
                self.performed_resize = True
                yielded = True
            self.log_info(f"test drives {dix_test_drives}")
            yield dix_test_drives

        if not yielded:
            self.log_info(
                "DIX namespace resize was skipped (drives do not support DIX). "
                "No workloads will be executed."
            )

    def lba_format_setup(self, drives: list[Drive] | None = None) -> None:
        target_drives = drives if drives is not None else self.test_specific_drives

        if self.lba_format is None:
            raise TestError(
                "lba_format must be set in test_control to run lba_format_setup.",
                component=COMPONENT.TEST,
                error_type=ErrorType.INPUT_ERR,
            )
        lba_format = self.lba_format

        lbaf_to_flbas_map = (
            NvmeResizeUtil.validate_drives_support_dix_resize_lba_formats(
                # pyrefly: ignore [bad-argument-type]
                self.host,
                target_drives,
                required_formats={dix_utils.T10_DIX_FORMAT},
                warning=self.dix_warning,
            )
        )
        if lbaf_to_flbas_map is None:
            self.dix_enabled = False
            return

        self.log_info(f"Formatting single NVMe namespace with {lba_format} LBA format")

        for drive in target_drives:
            AutovalUtils.validate_condition(
                lba_format in lbaf_to_flbas_map,
                f"{drive.block_name} supports LBA format '{lba_format}'.",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.INPUT_ERR,
            )

            lbaf = lbaf_to_flbas_map[lba_format]
            AutovalUtils.validate_no_exception(
                NVMeUtils.format_nvme,
                [self.host, drive.block_name, 0, None, f" -l {lbaf}"],
                f"{drive.block_name}: Format with lba {lba_format}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )
        # pyrefly: ignore [missing-attribute]
        self.log_info(f"NVME LIST:\n{self.host.run('nvme list')}")
        self.log_info(f"Test Drives: {target_drives}")
        self.dix_enabled = True
        self.performed_resize = True

    def set_power_state(
        self,
        workload_config: dict[str, Any] | None = None,
        drives: list[Drive] | None = None,
    ) -> None:
        """
        Set the power state of all drives in a test.
        If drive_capacity_power_state is None (meaning the TB capacity is not in
        DRIVE_CAPACITY_POWER_STATES), this method will log a message and skip
        setting the power state.

        Args:
            drives: A list of drives to set the power state. Defaults to None.
            workload_config: A dictionary containing workload configuration. Defaults to None.
        """
        if drives is None:
            drives = self.test_specific_drives

        # Convention: "set_power_state" is the boolean enable flag,
        # "power_state" is the actual numeric power state value.
        # workload_config takes priority; self.test_control is the fallback for both keys.
        enable_power_state = False
        power_state_value = None
        if workload_config is not None:
            # For workload-based configurations (SSDSynthFlashTest, SSDCachebenchTest).
            # Fall back to test_control so that passing --args '{"power_state": N}'
            # works even when a workload_config is present.
            enable_power_state = workload_config.get(
                "set_power_state", self.test_control.get("set_power_state", False)
            )
            if enable_power_state:
                power_state_value = workload_config.get(
                    "power_state", self.test_control.get("power_state", "")
                )
        else:
            # For test_control-based configurations (SSDFileAppendTest)
            enable_power_state = self.test_control.get("set_power_state", False)
            if enable_power_state:
                power_state_value = self.test_control.get("power_state", "")

        if not enable_power_state:
            return

        if power_state_value is None or power_state_value == "":
            if self.drive_capacity_power_state is None:
                self.log_info(
                    "Skipping power state setting - drive capacity not in DRIVE_CAPACITY_POWER_STATES and no explicit power state provided"
                )
                return
            power_state_value = self.drive_capacity_power_state

        self.log_info(f"Setting power state {power_state_value} for drives: {drives}")
        ComponentTestBase.power_state(
            self.host,
            drives,
            power_state_set_key=power_state_value,
        )
