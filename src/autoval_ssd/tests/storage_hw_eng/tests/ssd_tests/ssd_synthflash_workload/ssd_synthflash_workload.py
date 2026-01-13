# pyre-strict
import json
import os
import pathlib
import re
from collections.abc import Iterable
from time import sleep
from typing import Any, Optional, Union

from autoval.lib.host.component.component import COMPONENT

from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType

from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalUtils

from autoval.lib.utils.file_actions import FileActions
from autoval.lib.utils.generic_utils import GenericUtils
from autoval_ssd.lib.utils.fio.fio_synth_flash_utils import FioSynthFlashUtils
from autoval_ssd.lib.utils.storage.drive import Drive
from autoval_ssd.lib.utils.storage.nvme.fdp_utils import FDPUtils
from autoval_ssd.lib.utils.storage.nvme.latency_monitor_utils import LatencyMonitor
from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.storage.storage_device_factory import StorageDeviceFactory
from autoval_ssd.lib.utils.system_utils import SystemUtils
from autoval_ssd.tests.storage_hw_eng.libs.component_common_lib.component_test_base import (
    ComponentTestBase,
    SmartctlLogParser,
)
from autoval_ssd.tests.storage_hw_eng.libs.data_types.fb_synthflash_data import (
    FBSynthFlashInput,
)
from autoval_ssd.tests.storage_hw_eng.libs.data_types.fio_data.fio_data import FioOutput
from autoval_ssd.tests.storage_hw_eng.libs.ssd_lib.ssd_test_base import SSDTestBase
from autoval_ssd.tests.storage_hw_eng.libs.utils.exception_tb import get_traceback_str
from packaging.version import parse as parse_version

from .ssd_synthflash_data import (
    SSDSynthFlashDriveEntry,
    SSDSynthFlashEntry,
    SSDSynthFlashInput,
    SSDSynthFlashOutput,
)

REQUIRED_PKGS = [
    "fio",
    "fio-engine-libaio",
    "parted",
]


class SSDSynthFlashTest(SSDTestBase):
    """
    SSD Synthflash Test.
    """

    WL_SUITES = pathlib.Path("/usr/local/fb-FioSynthFlash/wkldsuites")
    performed_resize = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(
            *args, inputT=SSDSynthFlashInput, outputT=SSDSynthFlashOutput, **kwargs
        )
        self.synth_verify: bool = self.test_control.get("synth_verify", False)
        self.storage_test_tools: list[str] = REQUIRED_PKGS
        self.test_control["upqt_lm_validation"] = True
        self.fiosynth_lm: bool = self.test_control.get("fiosynth_lm", True)

    def setup(self, *args: Any, **kwargs: Any) -> None:
        super().setup(init_bg_polling=False)
        host = self.host

        self._install_required_packages()
        FioSynthFlashUtils.tool_setup(self.host)
        # Check for packages on system.
        runtime_chk = self.chk_host_runtime(host, self.storage_test_tools)
        self.validate_condition(runtime_chk, "Validate installed packages.")

        # Create Remote Temp Directory
        success, temp_dir = self.create_temp_directory(host)
        self.validate_condition(
            success, f"Create temp directory {temp_dir} on {host.hostname}."
        )
        self.work_dir = temp_dir

        # Copy workloads into the temp dir
        host.run(f"cp -rf {SSDSynthFlashTest.WL_SUITES} {self.work_dir}/workloads")

        # Transfer over additional workloads
        try:
            self._xfer_workloads()
        except Exception as e:
            raise TestError(f"Failed to Transfer Workloads! -- {type(e)}:{e}")

        try:
            os.makedirs(f"{self.resultsdir}/results")
        except FileExistsError:
            # directory already exists
            pass
        except Exception as e:
            raise TestError(
                f"Failed to create local results directory -- {type(e)}:{e}"
            )

    def _install_required_packages(self) -> None:
        SystemUtils.install_rpms(
            self.host,
            self.storage_test_tools,
            disable_tools_upgrade=self.disable_tools_upgrade,
            force_install=True,
        )

    def execute(self) -> None:
        """
        This function is the main execution loop for the SSDSynthFlashTest class.

        It first gets all the SSDs on the system and checks if there are any testable NVMe drives.
        If no testable drives are found, it logs a message and returns.

        If testable drives are found, it sets the write cache correctly for all drives, creates a
        list of test drives using the StorageDeviceFactory, and overrides kernel parameters for the test drives.

        It then loops through each workload configuration specified in the input parameters and
        performs the following steps:

            1. Deletes any existing RAID arrays
            2. Resizes the drives to the desired capacity.
               - If self.dix_ns_resize is True, it will perform a DIX namespace resize instead of the normal NVMe Resize.
            3. Creates RAID arrays on the devices if specified in the workload configuration.
            4. Sets the power state on the devices if specified in the workload configuration.
            5. Runs the specified workload suites using the FBSynthFlash tool.
            6. Monitors latency during the test using the LatencyMonitor class.
            7. Verifies the output of the test using the synth_output_validation function.
        """
        super().execute()
        self.log_info(" ")
        ComponentTestBase.override_kernel_parameters(
            self.host,
            self.test_drives,
            preferred_scheduler=self.test_control.get("preferred_scheduler", None),
            io_timeout=self.test_control.get("io_timeout", None),
            discard_max_bytes=self.test_control.get("discard_max_bytes", None),
            max_sectors_kb=self.test_control.get("max_sectors_kb", None),
        )
        index = 0
        loop_counter = 0

        for workload_config in self.input_params.workload_configs:
            # resize the drives
            loop_counter = loop_counter + 1
            self.test_specific_drives = ComponentTestBase.drives_executable(
                self.test_drives, workload_config
            )
            self.log_info(f"Testing on drives: {self.test_specific_drives}")

            self.log_info(
                f"================ Running fioSynth config {loop_counter} =======================\n"
            )

            # Displaying the FioSynth Version for the workload config
            self.log_info(
                f"Displaying the FioSynth version for the current config: {ComponentTestBase.display_fiosynth_version(self.host)}"
            )

            # Overriding the Kernal Parameters
            self.log_info(" ")
            ComponentTestBase.override_kernel_parameters(
                self.host,
                self.test_specific_drives,
                preferred_scheduler=workload_config.get("preferred_scheduler", None),
                io_timeout=workload_config.get("io_timeout", None),
                discard_max_bytes=workload_config.get("discard_max_bytes", None),
                max_sectors_kb=workload_config.get("max_sectors_kb", None),
            )
            self.log_info("Deleting the RAID array/s if exists")
            self.delete_raid_array()

            self.perform_resize = workload_config.get("perform_resize", False)
            self.nvme_id_ctrl_filter = workload_config.get(
                "nvme_id_ctrl_filter", "True"
            )
            self.nvme_id_ctrls = NvmeResizeUtil.get_nvme_ctrls(
                self.host, self.test_specific_drives, nvme_id_ctrl_filter="True"
            )
            self.cycle = workload_config.get("cycle_count", 1)

            if self.dix_ns_resize:
                lbaf_to_flbas_map = (
                    NvmeResizeUtil.validate_drives_support_dix_resize_lba_formats(
                        self.host, self.test_specific_drives
                    )
                )
                if self.lba_format:
                    self.lba_format_setup(lbaf_to_flbas_map)
                    self.set_power_state(workload_config)
                    self.run_workloads(workload_config, index)
                    index += 1

                else:
                    for dix_test_drives_list in self.dix_ns_resize_setup(
                        lbaf_to_flbas_map
                    ):
                        self.set_power_state(workload_config, dix_test_drives_list)
                        self.run_workloads(workload_config, index, dix_test_drives_list)
                        index += 1

            elif self.fdp_setup:
                self.fdp_single_namespace_setup()

            elif self.lba_format:
                self.lba_format_setup()

            elif self.perform_resize:
                self.over_provisioning_setup(workload_config)

            else:
                self.resize_full_capacity()

            if not self.dix_ns_resize:
                # Create RAID on devices
                if (
                    "perform_raid" in workload_config
                    and workload_config["perform_raid"]
                ):
                    self.log_info("++++++++++++ Creating RAID array ++++++++ ")
                    self.raid_to_drive_mapping = self.create_raid_array(workload_config)

                self.set_power_state(workload_config)
                self.run_workloads(workload_config, index)
                index += 1

    def resize_full_capacity(self) -> None:
        """
        Resize drives to full capacity, setting OP to default.
        """
        # actively set OP to default (TNVMCAP - 0) if perform_resize is False
        self.log_info("+++++++++++ Resizing the drives to Full Capacity  ++++++++++ ")
        self.performed_resize = False
        self.sweep_param_key: "NvmeResizeUtil.SweepParamKeyEnum" = (
            NvmeResizeUtil.SweepParamKeyEnum["overprovisioning"]
        )
        self.sweep_param_unit: "NvmeResizeUtil.SweepParamUnitEnum" = (
            NvmeResizeUtil.SweepParamUnitEnum["percent"]
        )
        self.sweep_param_value = NvmeResizeUtil.DEFAULT_OP_PERCENT
        NvmeResizeUtil.perform_resize(
            self.host,
            self.test_specific_drives,
            sweep_param_key=self.sweep_param_key,
            sweep_param_unit=self.sweep_param_unit,
            sweep_param_value=self.sweep_param_value,
            nvme_id_ctrl_filter=self.nvme_id_ctrl_filter,
            cycle=self.cycle,
        )

    def over_provisioning_setup(self, workload_config: dict[str, Any]) -> None:
        """
        Configures the drives for over-provisioning by setting the sweep
        parameters (key, unit, and value) from the workload configuration. Then
        performs the resize operation on the drives to apply the over-provisioning settings.

        Args:
            workload_config: A dictionary containing the configuration
                for the workload, including sweep parameters for over-provisioning.
        """

        try:
            self.sweep_param_key: "NvmeResizeUtil.SweepParamKeyEnum" = (
                NvmeResizeUtil.SweepParamKeyEnum[workload_config.get("sweep_param_key")]
            )
            self.sweep_param_unit: "NvmeResizeUtil.SweepParamUnitEnum" = (
                NvmeResizeUtil.SweepParamUnitEnum[
                    workload_config.get("sweep_param_unit")
                ]
            )
            self.sweep_param_value = workload_config.get("sweep_param_value")
        except KeyError as exc:
            raise TestError(
                f"Invalid/Missing sweep param in test_control: {str(exc)}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.INPUT_ERR,
            )
        self.log_info("+++++++++++ Over-provisioning the drives ++++++++++ ")
        self.performed_resize = True
        NvmeResizeUtil.perform_resize(
            self.host,
            self.test_specific_drives,
            sweep_param_key=self.sweep_param_key,
            sweep_param_unit=self.sweep_param_unit,
            sweep_param_value=self.sweep_param_value,
            nvme_id_ctrl_filter=self.nvme_id_ctrl_filter,
            cycle=self.cycle,
        )

    def dix_ns_resize_setup(
        self, lbaf_to_flbas_map: dict[str, int]
    ) -> Iterable[list[Drive]]:
        """
        Set up the DIX namespace resize process for the test drives.

        This function configures the drives for DIX namespace resizing by setting the
        sweep parameters (key, unit, and value) and iterates over the LBA format combinations
        to perform the resize operation on the drives.

        Args:
            lbaf_to_flbas_map: A dictionary mapping LBA formats to FLBAS values.

        Yields:
            It uses a generator to yield the test drives after each resize cycle,
            allowing for sequential processing of each configuration.
        """

        self.sweep_param_key: "NvmeResizeUtil.SweepParamKeyEnum" = (
            NvmeResizeUtil.SweepParamKeyEnum["overprovisioning"]
        )
        self.sweep_param_unit: "NvmeResizeUtil.SweepParamUnitEnum" = (
            NvmeResizeUtil.SweepParamUnitEnum["percent"]
        )
        self.sweep_param_value = 75
        self.performed_resize = True
        self.log_info(f"lbaf to flbas map {lbaf_to_flbas_map}")
        if self.lbaf_combinations == []:
            self.lbaf_combinations = [
                ["4096+64", "4096+64"],
                ["4096+64", "512"],
                ["4096+64", "4096"],
            ]
        resize_cycle = 1
        dix_test_drives = self.test_specific_drives

        for combo in self.lbaf_combinations:
            self.log_info(
                f"Starting resize cycle {resize_cycle} with combination {combo}"
            )

            NvmeResizeUtil.perform_resize(
                self.host,
                dix_test_drives,
                sweep_param_key=self.sweep_param_key,
                sweep_param_unit=self.sweep_param_unit,
                sweep_param_value=self.sweep_param_value,
                cycle=self.cycle,
                combination=combo,
                lbaf_to_flbas_map=lbaf_to_flbas_map,
                use_existing_ns=(resize_cycle != 1),
            )
            resize_cycle += 1
            sleep(5)

            self.data_ssds = self.get_all_ssds(self.collect_drive_data, no_boot=True)
            dix_drives_list = [
                drive_name[5:] for drive_name in self.data_ssds.devname.tolist()
            ]
            dix_test_drives = StorageDeviceFactory(
                self.host, dix_drives_list, None
            ).create()

            self.log_info(f"test drives {dix_test_drives}")
            yield dix_test_drives

    def lba_format_setup(
        self, lbaf_to_flbas_map: Optional[dict[str, int]] = None
    ) -> None:
        """
        This function formats the single NVMe namespace of the test drives using the specified
        LBA format.

        Args:
            lbaf_to_flbas_map: Optional dictionary mapping LBA formats to FLBAS values.
        """

        self.log_info(
            f"Formatting single NVMe namespace with {self.lba_format} LBA format"
        )

        for drive in self.test_specific_drives:
            if lbaf_to_flbas_map is None:
                drive_lbaf_map = NvmeResizeUtil.get_lbaf_to_flbas_map(
                    self.host, drive.block_name
                )
            else:
                drive_lbaf_map = lbaf_to_flbas_map

            AutovalUtils.validate_condition(
                self.lba_format in drive_lbaf_map,
                f"{drive.block_name} supports LBA format '{self.lba_format}'.",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.INPUT_ERR,
            )

            lbaf = drive_lbaf_map[self.lba_format]

            AutovalUtils.validate_no_exception(
                NVMeUtils.format_nvme,
                [self.host, drive.block_name, 0, None, f" -l {lbaf}"],
                f"{drive.block_name}: Format with lba {self.lba_format}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )
        self.log_info(f"NVME LIST:\n{self.host.run('nvme list')}")
        self.log_info(f"Test Drives: {self.test_specific_drives}")
        self.performed_resize = True

    def fdp_single_namespace_setup(self) -> None:
        """
        Set up a single namespace with 4k LBA format and FDP enabled on the test drives.

        Raises:
            TestError: If FDP support validation fails.
        """

        FDPUtils.validate_fdp_support(self.host, self.nvme_id_ctrls)
        FDPUtils.fdp_setup(self.host, self.nvme_id_ctrls)
        AutovalLog.log_info(
            "FDP setup completed\n NVME LIST\n" + self.host.run("nvme list")
        )
        self.fdp_enabled = True
        self.performed_resize = True

    def set_power_state(
        self, workload_config: dict[str, Any], drives: Optional[list[Drive]] = None
    ) -> None:
        """
        Set the power state of all drives in a test.
        This function uses the PowerState class to perform this action.
        Args:
            workload_config : A dictionary containing the configuration for the workload.
            drives: A list of drives to set the power state for. Defaults to None.
        """
        # Set Power State on devices
        if drives is None:
            drives = self.test_specific_drives
        if workload_config.get("set_power_state", False):
            power_state = workload_config.get("power_state", None)
            if power_state is None:
                power_state = self.drive_capacity_power_state

            ComponentTestBase.power_state(
                self.host,
                drives,
                power_state_set_key=power_state,
            )

    def run_workloads(
        self,
        workload_config: dict[str, Any],
        index: int,
        drives: Optional[list[Drive]] = None,
    ) -> None:
        """
        Perform the workload testing process for SSDSynthFlashTest.
        This function calls `run_synthflash()` to perform the actual tests.
        Args:
            workload_config: A dictionary containing the configuration for the workload.
            index: The index of the test.
            drives: A list of drives to test. Defaults to None.
        Raises:
            TestError: If there is an error in the input or if the synth verification result directory is missing.
        """
        if drives is None:
            drives = self.test_specific_drives

        for workload in workload_config.get("workload_suites"):
            self.latency_monitor = LatencyMonitor(
                host=self.host,
                test_drives=drives,
                test_control=self.test_control,
            )
            lm_enabled_drives = self.latency_monitor.enable(
                workload=workload, working_directory=self.work_dir
            )
            # Run Synthflash
            self.log_info("Starting Synthflash Tests ")
            self.log_info(f"Running the {workload} Workload.")

            # Generate the run folder locations
            run_folder = f"test{index}_{workload}"

            # Run synthflash
            queue_list = []
            for drive in drives:
                result_folder = f"{run_folder}_{str(drive.block_name)}_results"
                remote_run_folder = f"{self.work_dir}/{result_folder}"
                local_run_folder = f"{self.resultsdir}/{result_folder}"
                device = f"/dev/{str(drive.block_name)}"
                # Create the run parameters
                run_params = FBSynthFlashInput(
                    devices=device,
                    workload_suite=workload,
                    result_filename_prefix=result_folder,
                    capacity=self.input_params.capacity,
                    health_monitoring=self.input_params.health_monitoring,
                    skip_drive_prep=self.input_params.skip_drive_prep,
                    num_runs=self.input_params.num_runs,
                    flash_config_logging=self.input_params.flash_config_logging,
                )

                queue_list.append(
                    AutovalThread.start_autoval_thread(
                        self._run_synthflash,
                        self.host,
                        run_params,
                        device,
                        remote_run_folder,
                        local_run_folder,
                    )
                )
            if queue_list:
                AutovalThread.wait_for_autoval_thread(queue_list)

            for results in self.run_entry:
                self.output.entries.append(results)

            if self.synth_verify:
                result_dirs = [
                    i
                    for i in self.host.run(f"ls {self.work_dir}").split("\n")
                    if i.startswith(f"test{index}")
                ]
                for result_dir in result_dirs:
                    match = re.search(r"(nvme\d+n\d+)", result_dir)
                    if match:
                        test_specific_drive = match.group(0)
                    else:
                        raise TestError(
                            f"{result_dir} missing workload result",
                            component=COMPONENT.STORAGE_DRIVE,
                            error_type=ErrorType.INPUT_ERR,
                        )
                    result_dir = os.path.join(self.work_dir, result_dir)
                    AutovalLog.log_info(f" synth verification result dir {result_dir}")
                    SSDSynthFlashTest.synth_output_validation(
                        self.host,
                        result_dir,
                        workload,
                        test_specific_drive,
                        lm_enabled_drives,
                    )
                    if lm_enabled_drives:
                        self.latency_monitor.parse_and_validate_results(
                            synth_workload_result_dir=result_dir,
                            lm_enabled_drives=lm_enabled_drives,
                        )
            if lm_enabled_drives:
                self.latency_monitor.disable(working_directory=self.work_dir)

    def cleanup(self, **kwargs: Any) -> None:
        """
        This function performs the cleanup process for the SSDSynthFlashTest class.
        It restores any saved workloads and deletes any RAIDed volumes that were created during testing.
        If the 'performed_resize' attribute is set to True, it also resizes the drives to their full capacity.
        """

        self.log_info(" ")
        self.log_info("================ Clean Up Process=======================")
        host = self.host
        if hasattr(self, "saved_old_wl"):
            self.log_info(
                f"Restoring workloads from {self.saved_old_wl} on {host.hostname}"
            )
            # First remove current folder, then restore the original folder.
            host.run(f"rm -rf {self.SSDSynthFlashTest.WL_SUITES}")
            host.run(f"cp -rf {self.saved_old_wl} {self.SSDSynthFlashTest.WL_SUITES}")
            self.log_info(f"Removing {self.saved_old_wl} on {host.hostname}")
            host.run(f"rm -rf {self.saved_old_wl}")

        self.log_info(" ")
        self.log_info("++++++ Deleting the RAIDed Volumes +++++++")
        self.delete_raid_array()

        if self.performed_resize:
            self.log_info(" ")
            self.log_info(
                "+++++++++++ Resizing the drives to Full Capacity  ++++++++++ "
            )
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
        super().cleanup(**kwargs)

    @staticmethod
    def synth_output_validation(
        host: Host,
        results_dir: str,
        synth_workload: str,
        test_drive: str,
        lm_enabled_drives: Optional[list[str]] = None,
    ) -> None:
        """Synth Output Validation.

        Each fio workload in synth is compared with it's range in target
        workload file.

        Parameters
        -----------
        results_dir: String
             Master result directory of synth load.
        synth_workload: String
             FioSynth workload.
        test_drive: Str
             Drive name that is to be tested.
        """
        AutovalLog.log_info(
            f"synth verification running on {synth_workload} with drive {test_drive}..."
        )
        filename = "fiosynth_targets.json"
        cfg_dir = "cfg/storage/storage_hw_eng"
        relative_cfg_file_path = os.path.join(cfg_dir, filename)
        benchmark_dict = GenericUtils.read_resource_cfg(
            file_path=relative_cfg_file_path, module="autoval_ssd"
        )

        csv_files = ""
        fio_results_dir = FioSynthFlashUtils.find_file_paths(
            host, results_dir, file_extension=".csv"
        )
        global_target = ""
        if re.search(r".Workload_loop", synth_workload):
            global_target = re.sub(r".Workload_loop", "_Global", synth_workload)
        else:
            global_target = synth_workload + "_Global"
        # try to find the results dir with time-stamp
        for fio_load_dir in fio_results_dir:
            if FileActions.exists(fio_load_dir, host=host):
                if synth_workload not in fio_load_dir[::-1].split("/")[0][::-1]:
                    continue

                verify_workload = True
                # try to find the CSV verification file
                csv_files = FioSynthFlashUtils.find_file_paths(
                    host, fio_load_dir, file_extension=".csv"
                )
                if len(csv_files):
                    csv_file = csv_files[0]
                else:
                    raise TestError(
                        "Can't find CSV file in this dir: %s" % fio_load_dir
                    )
                output_json_files = FioSynthFlashUtils.find_file_paths(
                    host, results_dir, file_extension=".json"
                )

                csv_list = FileActions.read_data(csv_file, csv_file=True, host=host)
                if csv_list:
                    for index in range(len(output_json_files)):
                        # check for synthload in benchmark dict.
                        try:
                            if benchmark_dict[synth_workload]:
                                FioSynthFlashUtils.compare_csv_json(
                                    host,
                                    global_target,
                                    synth_workload,
                                    benchmark_dict,
                                    csv_list[index],
                                    test_drive,
                                    verify_workload,
                                    lm_enabled_drives,
                                )
                        except KeyError:
                            msg = "Synthload %s is not available in the benchmark dict"
                            raise TestError(msg % synth_workload)
            else:
                raise TestError(
                    "[synth_verify]: This synthload result dir is not avialble: %s"
                    % fio_load_dir,
                )

    def _xfer_workloads(self) -> None:
        """
        Attempts to transfer workloads if they exist.
        """
        if self.input_params.local_wl_suite_folder is not None:
            local_folder = pathlib.Path(self.input_params.local_wl_suite_folder)
            if local_folder.is_dir():
                host = self.host
                # Save old workloads
                self.saved_old_wl = f"/tmp/workloads_{self.create_timestamp()}"
                self.log_info(f"Saving old workloads at {self.saved_old_wl}")
                host.run(f"cp -rf {SSDSynthFlashTest.WL_SUITES} {self.saved_old_wl}")
                # Put in new workloads
                self.log_info(
                    f"Copying workloads from {local_folder} to "
                    + f"{SSDSynthFlashTest.WL_SUITES} on {self.host.hostname}"
                )
                host.put_folder(
                    f"{local_folder}",
                    f"{SSDSynthFlashTest.WL_SUITES}",
                    overwrite=True,
                    verbose=True,
                )
            else:
                raise TestError(f"Local folder {local_folder} does not exist!")

    def _run_synthflash(
        self,
        host: Host,
        run_params: FBSynthFlashInput,
        devnames: str,
        remote_run_folder: str,
        local_run_folder: str,
    ) -> None:
        """
        Collect Smartlog and run on drives.
        """

        synthflash_data = None
        success = True
        msgs = []
        drive_name = devnames

        synthflash_drive_entries = {drive_name: SSDSynthFlashDriveEntry()}

        pre_run_smartlog_data = self._pre_synthflash(
            host=host, devname=str(drive_name), entries=synthflash_drive_entries
        )

        # Run Synthflash on system
        try:
            fiosynth_version = re.findall(
                r"\d+(?:\.\d+)*", self.display_fiosynth_version()
            )[0]
            cmd = f"{run_params.to_cmd()} {' --lm' if self.fiosynth_lm and parse_version(fiosynth_version) >= parse_version('3.6.0') else ''}"

            self.log_info(f"Running {cmd} on host {host.hostname}")

            cmd = f"cd {self.work_dir} && {cmd}"  # trying to change dir

            result = host.run_get_result(cmd, timeout=self.input_params.timeout)

            # If run failed.
            if result.return_code != 0:
                success = False
                msg = (
                    f"Synthflash failed with rc={result.return_code} on host {host.hostname} "
                    + f"-- {result.stdout} {result.stderr}"
                )
                self.log_error(msg)
                msgs.append(msg)
            # Otherwise attempt to RX the results and process them.
            else:
                self.result_folder = self._rx_run_results(
                    host, remote_run_folder, local_run_folder, msgs=msgs
                )
                synthflash_data = self._process_results(
                    host, self.result_folder, msgs=msgs
                )
                self.test_results = synthflash_data
        except Exception:
            success = False
            msg = (
                f"Synthflash failed on host {host.hostname} "
                + f"-- {get_traceback_str()}"
            )
            self.log_error(msg)
            msgs.append(msg)
            self.validate_condition(success, "Synthflash execution")

        # Do all post-run operations
        post_run_smartlog_data = self._post_synthflash(
            host=host, devname=str(drive_name), entries=pre_run_smartlog_data
        )

        # Check if all drive entries completed successfully.
        if post_run_smartlog_data:
            for devname, entry in post_run_smartlog_data.items():
                if not entry.success:
                    success = False
                    msgs.append(
                        f"Drive entry failure for device {devname} "
                        + "-- Please check msgs in drive_entries!"
                    )

        fio_data = synthflash_data[0] if synthflash_data is not None else {}
        flash_config = synthflash_data[1] if synthflash_data is not None else {}
        summary_data = synthflash_data[2] if synthflash_data is not None else []

        for key in fio_data.keys():
            if "json" in key:
                fio_data[key].global_options = None

        self.run_entry.append(
            SSDSynthFlashEntry(
                success=success,
                msgs=msgs,
                workload_name=run_params.workload_suite,
                synthflash_params=run_params,
                fio_data=fio_data,
                flash_config=flash_config,
                summary_data=summary_data,
                drive_entries=post_run_smartlog_data,
            )
        )

    def _pre_synthflash(
        self,
        *,
        host: Host,
        devname: str,
        entries: dict[str, SSDSynthFlashDriveEntry],
    ) -> Optional[dict[str, SSDSynthFlashDriveEntry]]:
        entry = entries[devname]
        # Get the drive object
        entry.drive = self.entry_get_drive(
            host, devname, self.data_ssds, msgs=entry.msgs
        )
        if entry.drive is None:
            entry.success = False
            return

        self.smartctl_log = SmartctlLogParser()
        entry.init_nvme_smartlog = {"smart-log": ""}
        entry.init_smartctl_smartlog = ""
        if self.collect_smart_log:
            # Check Initial Smartlogs
            entry.init_smartctl_smartlog = self.smartctl_log.clean_data(
                self.entry_get_smartlog(
                    host, devname, smartlog_type="initial", msgs=entry.msgs
                )
            )

            entry.init_nvme_smartlog = self.entry_get_nvme_log(entry.drive, entry.msgs)

        return entries

    def _post_synthflash(
        self,
        *,
        host: Host,
        devname: str,
        entries: Optional[dict[str, SSDSynthFlashDriveEntry]],
    ) -> Optional[dict[str, SSDSynthFlashDriveEntry]]:
        if entries is None:
            return
        entry = entries[devname]

        # Get the drive object
        entry.drive = self.entry_get_drive(
            host, devname, self.data_ssds, msgs=entry.msgs
        )
        # Check there is a valid drive entry
        if entry.drive is None:
            return

        entry.final_nvme_smartlog = {"smart-log": ""}
        entry.final_smartctl_smartlog = ""
        if self.collect_smart_log:
            # Check Final Smartlogs
            entry.final_smartctl_smartlog = self.smartctl_log.clean_data(
                self.entry_get_smartlog(
                    host, devname, smartlog_type="final", msgs=entry.msgs
                )
            )
            entry.final_nvme_smartlog = self.entry_get_nvme_log(entry.drive, entry.msgs)
        return entries

    def _rx_run_results(
        self,
        host: Host,
        folder_prefix: str,
        dest: str,
        msgs: Optional[list[str]] = None,
    ) -> Union[bool, str]:
        """
        Retrieve the synthflash results.
        """
        self.log_info(
            f"Retrieving folder with prefix {folder_prefix} from {host.hostname}"
        )

        folder_prefix_path = pathlib.Path(folder_prefix)

        result = host.run_get_result(
            f'find {folder_prefix_path.parent} -maxdepth 1 -type d -name "{folder_prefix_path.name}*" -print',
            ignore_status=True,
        )

        if result.return_code != 0:
            if msgs is not None:
                msg = f"Error while searching! rc={result.return_code}: {result.stderr}"
                msgs.append(msg)
                self.log_error(msg)
                return False

        folders = result.stdout.strip().split("\n")

        if len(folders) == 0:
            if msgs is not None:
                msg = f"Cound not find folder with prefix {folder_prefix} on host {host.hostname}"
                msgs.append(msg)
                self.log_error(msg)
                return False

        if len(folders) > 1:
            if msgs is not None:
                msg = f"Multiple folders with prefix {folder_prefix} on host {host.hostname} -- Grabbing first."
                msgs.append(msg)
                self.log_warning(msg)

        result_folder = ", ".join(folders)

        self.log_info(f"Found folder: {result_folder}")

        return result_folder

    def _process_results(
        self, host: Host, folder: str, msgs: Optional[list[str]] = None
    ) -> tuple[dict[str, str], dict[str, str], list[dict[str, str]]]:
        """
        Extract the data.
        """

        self.log_info(f"Processing results in {folder}")

        results = pathlib.Path(folder)

        fio_results = {}
        config = {}
        summary = []
        results = str(host.run(f"cd {folder} && ls")).split("\n")
        file_name = ""
        for i in results:
            if i.endswith(".json"):
                file_name = i
                continue

        json_file_data = host.run(f"cd {folder} && cat {file_name}")
        json_str = str(json.loads(json_file_data)).replace("'", '"')
        try:
            fio_results[str(file_name)] = FioOutput.from_JSON_string(str(json_str))

        except Exception as e:
            if msgs is not None:
                msg = f"Failed to parse {file_name} as fio output! -- {type(e)}:{e}"
                self.log_warning(msg)
                msgs.append(msg)

        # Go through CSV files
        results = [i for i in results if ".csv" in str(i)]

        for csv_file_name in results:
            # If the flashconfig csv
            if "flashconfig" in str(csv_file_name):
                self.log_info(f"Flash Config File: {csv_file_name}")
                csv_data = str(host.run(f"cd {folder} && cat {csv_file_name}")).split(
                    "\n"
                )
                heading = csv_data[0].split(",")
                for index in range(1, len(csv_data)):
                    temp_dict = {}
                    for key, val in zip(heading, csv_data[index].split(",")):
                        if key != "{":
                            temp_dict[key.strip("\r")] = val.strip("\r")
                    config.update(temp_dict)

            # If the summary csv
            else:
                self.log_info(f"Summary File: {csv_file_name}")
                csv_data = str(host.run(f"cd {folder} && cat {csv_file_name}")).split(
                    "\n"
                )
                heading = csv_data[0].split(",")
                for index in range(1, len(csv_data)):
                    temp_dict = {}
                    for key, val in zip(heading, csv_data[index].split(",")):
                        if key != "{":
                            temp_dict[key.strip("\r")] = val.strip("\r")
                    summary.append(temp_dict)

        return (fio_results, config, summary)
