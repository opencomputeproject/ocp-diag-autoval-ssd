# pyre-unsafe
import json
import os
import pathlib
import typing as t
from typing import Any, Dict

from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.file_actions import FileActions
from autoval.lib.utils.generic_utils import GenericUtils
from autoval_ssd.lib.utils.fio.fio_synth_flash_utils import FioSynthFlashUtils
from autoval_ssd.lib.utils.storage.nvme.fdp_utils import FDPUtils
from autoval_ssd.lib.utils.storage.nvme.latency_monitor_utils import LatencyMonitor
from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil
from autoval_ssd.tests.storage_hw_eng.libs.component_common_lib.component_test_base import (
    ComponentTestBase,
)
from autoval_ssd.tests.storage_hw_eng.libs.ssd_lib.ssd_test_base import SSDTestBase
from autoval_ssd.tests.storage_hw_eng.libs.utils.exception_tb import get_traceback_str

from .ssd_cachebench_data import (  # noqa
    SSDSynthFlashDriveEntry,
    SSDSynthFlashEntry,
    SSDSynthFlashInput,
    SSDSynthFlashOutput,
)


class SSDCachebenchTest(SSDTestBase):
    """
    SSD Cachebench Test.
    """

    performed_resize = False
    raid_to_drive_mapping = {}

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args, inputT=SSDSynthFlashInput, outputT=SSDSynthFlashOutput, **kwargs
        )
        self.workload_folder_path = self.test_control.get("workload_folder_path", None)
        self.workload_file_name = self.test_control.get("workload_file_name", None)
        self.update_JSON_config = self.test_control.get("update_JSON_config", False)
        self.pass_fail_verify = self.test_control.get("pass_fail_verify", False)
        self.cachelib_path = self.test_control.get("cachelib_path", "/root/CacheLib/")

    def setup(self, *args, **kwargs):
        super().setup(init_bg_polling=False)
        host = self.host
        self.cachebench_path = self.cachelib_path + "opt/cachelib/bin/"
        self.WL_SUITES = pathlib.Path(
            self.cachelib_path + "cachelib/cachebench/test_configs"
        )
        cachebench_check = host.run_get_result(
            self.cachebench_path + "cachebench --version", ignore_status=True
        )
        if cachebench_check.return_code != 0:
            raise TestError(
                f"Cachebench Installation is not found at {self.cachebench_path} -- {cachebench_check.stderr}.\nPlease refer to https://cachelib.org/docs/installation/"
            )

        # Create Remote Temp Directory
        success, temp_dir = self.create_temp_directory(host)
        self.validate_condition(
            success, f"Create temp directory {temp_dir} on {host.hostname}."
        )
        self.work_dir = temp_dir

        # Copy workloads into the temp dir
        host.run(f"cp -rf {self.WL_SUITES} {self.work_dir}/test_configs")

        # Transfer over additional workloads
        try:
            self._xfer_workloads()
        except Exception as e:
            raise TestError(f"Failed to Transfer Test Configs! -- {type(e)}:{e}")

        try:
            os.makedirs(f"{self.resultsdir}/results")
        except FileExistsError:
            # directory already exists
            pass
        except Exception as e:
            raise TestError(
                f"Failed to create local results directory -- {type(e)}:{e}"
            )

    def execute(self):
        """
        This function executes the main test logic for the SSD Fio Synthetic Workload test.

        It first gets all the NVMe drives on the system and checks if there are any testable drives.
        If no testable drives are found, it logs a message and returns.

        If testable drives are found, it sets the write cache correctly for all devices and initializes the test drives using the StorageDeviceFactory class.

        It then loops through each workload configuration specified in the input parameters and performs the following steps:

            1. Overrides the kernel parameters for the specified workload configuration.
            2. Deletes any existing RAID arrays.
            3. (Optional) Resizes the drives to the desired capacity.
            4. (Optional) Creates a RAID array on the devices.
            5. Runs the cachebench tests for the specified workload configuration.
                (Enables latency monitor if applicable)
            6. Processes the results of the cachebench tests and adds them to the output.
            7. Validates the results of the cachebench tests against the expected values.
            8. Disables the latency monitor.
        """
        host = self.host

        ComponentTestBase.override_kernel_parameters(
            host,
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

            self.cleanup_test_drives = list(
                set(self.cleanup_test_drives + self.test_specific_drives)
            )
            self.log_info(
                f"================ Running Cachebench config {loop_counter} ======================="
            )

            # Overriding the Kernal Parameters
            ComponentTestBase.override_kernel_parameters(
                host,
                self.test_specific_drives,
                preferred_scheduler=workload_config.get("preferred_scheduler", None),
                io_timeout=workload_config.get("io_timeout", None),
                discard_max_bytes=workload_config.get("discard_max_bytes", None),
                max_sectors_kb=workload_config.get("max_sectors_kb", None),
            )

            self.log_info("Deleting the RAID array/s if exists")
            self.delete_raid_array()

            self.perform_resize = workload_config.get("perform_resize", False)
            self.nvme_id_ctrl_filter: str = workload_config.get(
                "nvme_id_ctrl_filter", "True"
            )
            self.cycle = workload_config.get("cycle_count", 1)

            if self.fdp_setup:
                self.fdp_single_namespace_setup()

            elif self.perform_resize:
                self.over_provisioning_setup(workload_config)

            elif self.performed_resize:
                self.resize_full_capacity(workload_config)

            # Create RAID on devices
            if "perform_raid" in workload_config and workload_config["perform_raid"]:
                self.log_info("++++++++++++ Creating RAID array ++++++++ ")
                self.raid_to_drive_mapping = self.create_raid_array(workload_config)

            self.set_power_state(workload_config)
            self.run_workload(workload_config, index)
            index += 1

    def resize_full_capacity(self, workload_config: Dict[str, Any]) -> None:
        """
        Resize the drives to full capacity.

        Args:
            workload_config: A dictionary containing the configuration for the workload.
        """
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

    def over_provisioning_setup(self, workload_config: Dict[str, Any]) -> None:
        """
        Overprovisioning the drives to the desired capacity.

        Args:
            workload_config: A dictionary containing the configuration for the workload.
        """
        self.log_info("+++++++++++ Over-provisioning the drives ++++++++++ ")
        self.performed_resize = True

        # Parse test_control json inputs
        try:
            self.sweep_param_key: "NvmeResizeUtil.SweepParamKeyEnum" = (
                NvmeResizeUtil.SweepParamKeyEnum[
                    workload_config.get("sweep_param_key", None)
                ]
            )
            self.sweep_param_unit: "NvmeResizeUtil.SweepParamUnitEnum" = (
                NvmeResizeUtil.SweepParamUnitEnum[
                    workload_config.get("sweep_param_unit", None)
                ]
            )
        except KeyError as e:
            raise TestError(f"Invalid/Missing sweep param in test_control: {str(e)}")
        self.sweep_param_value = workload_config.get("sweep_param_value", "")

        NvmeResizeUtil.perform_resize(
            self.host,
            self.test_specific_drives,
            sweep_param_key=self.sweep_param_key,
            sweep_param_unit=self.sweep_param_unit,
            sweep_param_value=self.sweep_param_value,
            nvme_id_ctrl_filter=self.nvme_id_ctrl_filter,
            cycle=self.cycle,
        )

    def set_power_state(self, workload_config: Dict[str, Any]) -> None:
        """
        Set the power state of all drives in a test.

        Args:
            workload_config : A dictionary containing the configuration for the workload
        """
        self.power_state = workload_config.get("power_state", False)
        if self.power_state:
            ComponentTestBase.power_state(
                self.host,
                self.test_specific_drives,
                power_state_set_key=workload_config.get("set_power_state", ""),
            )

    def run_workload(self, workload_config: Dict[str, Any], index: int) -> None:
        """
        Run the specified workload using Cachebench.

        This function sets up the necessary directories and files for running the workload,
        updates JSON configurations if required, and executes the Cachebench command.
        It also handles latency monitoring and collects results.

        Args:
            workload_config: A dictionary containing the configuration for the workload.
            index: The index of the test.
        """

        for workload in workload_config.get("workload_suites"):
            # Run Cachebench
            self.log_info("Starting Cachebench Tests ")
            self.log_info(f"Running the {workload.get('name')} Workload.")

            # Generate the run folder locations
            run_folder = (
                f"test{index}_{workload.get('name')}" + "-" + self.create_timestamp()
            )
            remote_run_folder = f"{self.work_dir}/{run_folder}"
            self.host.run("mkdir " + remote_run_folder)
            local_run_folder = f"{self.resultsdir}/{run_folder}"

            workload_folder_name = workload.get("workload_folder_path").rsplit("/", 1)[
                1
            ]
            workload_folder_path = remote_run_folder + "/" + workload_folder_name
            self.host.run("mkdir " + workload_folder_path)

            # Copying the Workload Directory to temp folder
            self.host.run(
                "cp -a "
                + self.work_dir
                + "/test_configs/"
                + workload.get("workload_folder_path")
                + "/. "
                + workload_folder_path
                + "/"
            )

            self.file_path = str(
                workload_folder_path + "/" + workload.get("workload_file_name")
            )

            if self.update_JSON_config:
                self.log_info(
                    f"Updating the JSON parameters of {workload.get('name')} Workload"
                )
                JsonUpdate.update_JSON_file_dict(
                    self.host, self.file_path, workload.get("parameters_override")
                )

            # Cachebench Run command
            cachebench_path = self.cachebench_path + "cachebench "
            json_test_config_path = (
                "--json_test_config "
                + workload_folder_path
                + "/"
                + workload.get("workload_file_name")
            )
            output_log_path = (
                " --progress_stats_file="
                + remote_run_folder
                + "/"
                + workload.get("name")
                + "_"
                + self.create_timestamp()
                + "_output.log"
            )
            cmd = cachebench_path + json_test_config_path + output_log_path
            self.latency_monitor = LatencyMonitor(
                host=self.host,
                test_drives=self.test_drives,
                test_control=self.test_control,
            )
            lm_enabled_drives = self.latency_monitor.enable(
                workload=workload["name"], working_directory=self.work_dir
            )
            # Run Cachebench on system
            try:
                msgs = []
                self.log_info(f"Running {cmd} on host {self.host.hostname}")
                result = self.host.run_get_result(
                    cmd,
                    timeout=self.input_params.timeout,
                    ignore_status=True,
                )

                # If run failed.
                if result.return_code != 0:
                    success = False
                    msg = (
                        f"Cachebench failed with rc={result.return_code} on host {self.host.hostname} "
                        + f"-- {result.stdout} {result.stderr}"
                    )
                    self.log_error(msg)
                    msgs.append(msg)
                # Otherwise attempt to RX the results and process them.
                else:
                    result_folder = self._rx_run_results(
                        self.host, remote_run_folder, local_run_folder, msgs=msgs
                    )
                    cachebench_data = self._process_results(
                        self.host, result_folder, msgs=msgs
                    )
                    if lm_enabled_drives:
                        self.latency_monitor.collect_logs(
                            workload=workload["name"],
                            synth_workload_result_dir=remote_run_folder,
                        )
                    self.output.entries.append(cachebench_data)
            except Exception:
                success = False  # noqa
                msg = (
                    f"Cachebench failed on host {self.host.hostname} "
                    + f"-- {get_traceback_str()}"
                )
                self.log_error(msg)
                msgs.append(msg)

            if self.pass_fail_verify:
                SSDCachebenchTest.cachebench_output_validation(self.host, self.work_dir)
                if lm_enabled_drives:
                    self.latency_monitor.parse_and_validate_results(
                        synth_workload_result_dir=remote_run_folder,
                        lm_enabled_drives=lm_enabled_drives,
                    )
        if hasattr(self.latency_monitor, "latency_monitor_config"):
            self.latency_monitor.disable(working_directory=self.work_dir)

    @staticmethod
    def cachebench_output_validation(host, results_dir: str) -> None:
        pass

        filename = "cachebench_targets.json"
        cfg_dir = "cfg/storage/storage_hw_eng"
        relative_cfg_file_path = os.path.join(cfg_dir, filename)
        benchmark_dict = GenericUtils.read_resource_cfg(
            file_path=relative_cfg_file_path, module="autoval_ssd"
        )
        cb_results_dir = FioSynthFlashUtils.find_file_paths(
            host, results_dir, file_extension=""
        )

        for cb_load_dir in cb_results_dir:
            if FileActions.exists(cb_load_dir, host=host):
                for cb_wl_load_dir in FioSynthFlashUtils.find_file_paths(
                    host, cb_load_dir, file_extension=""
                ):
                    log_files = []
                    if FileActions.exists(cb_load_dir, host=host):
                        # try to find the CSV verification file
                        log_files = FioSynthFlashUtils.find_file_paths(
                            host, cb_wl_load_dir, file_extension=".log"
                        )
                    for log_file in log_files:
                        verification_fields = None  # noqa
                        SSDCachebenchTest.compare_cachebench_logs(
                            host, benchmark_dict, log_file
                        )

    @staticmethod
    def compare_cachebench_logs(
        host, benchmark_dict: t.Union[dict, Dict[str, Dict]], log_file: str
    ) -> None:
        pass
        if "TaoLeader" in log_file:
            verification_fields = benchmark_dict.get("CacheBench_loop").get("TaoLeader")

        elif "MemCache" in log_file:
            verification_fields = benchmark_dict.get("CacheBench_loop").get("MemCache")

        ext_data = host.run("cat " + log_file)
        log_dict = SSDCachebenchTest.parse_cachebench_output_log(ext_data)

        for k in verification_fields.keys():
            if "MIN" in k:
                cb_op_val = float(log_dict[k.split("_MIN")[0]])
                AutovalUtils.validate_greater(
                    cb_op_val,
                    # pyre-fixme[61]: `verification_fields` is undefined, or not
                    #  always defined.
                    float(verification_fields[k].split(">")[1]),
                    msg="[%s]: %s" % (cb_op_val, k),
                    raise_on_fail=False,
                )
            elif "MAX" in k:
                cb_op_val = float(log_dict[k.split("_MAX")[0]])
                AutovalUtils.validate_less(
                    cb_op_val,
                    # pyre-fixme[61]: `verification_fields` is undefined, or not
                    #  always defined.
                    float(verification_fields[k].split("<")[1]),
                    msg="[%s]: %s" % (cb_op_val, k),
                    raise_on_fail=False,
                )
            else:
                raise TestError(
                    "[synth_verify]: Substring 'MIN' or 'MAX' is not provided"
                )

    @staticmethod
    def parse_cachebench_output_log(log_text):
        output_dict = {}
        log_text = log_text.split("== Allocator Stats ==")[-1]

        output_dict["NVM_Read_Latency_p50"] = float(
            log_text.split("NVM Read  Latency    p50      :")[1]
            .split(" us")[0]
            .replace(",", "")
        )
        output_dict["NVM_Read_Latency_p90"] = float(
            log_text.split("NVM Read  Latency    p90      :")[1]
            .split(" us")[0]
            .replace(",", "")
        )
        output_dict["NVM_Read_Latency_p99"] = float(
            log_text.split("NVM Read  Latency    p99      :")[1]
            .split(" us")[0]
            .replace(",", "")
        )
        output_dict["NVM_Read_Latency_p99.99"] = float(
            log_text.split("NVM Read  Latency    p9999    :")[1]
            .split(" us")[0]
            .replace(",", "")
        )
        output_dict["NVM_Read_Latency_Max"] = float(
            log_text.split("NVM Read  Latency    p100     :")[1]
            .split(" us")[0]
            .replace(",", "")
        )

        output_dict["NVM_Write_Latency_p50"] = float(
            log_text.split("NVM Write Latency    p50      :")[1]
            .split(" us")[0]
            .replace(",", "")
        )
        output_dict["NVM_Write_Latency_p90"] = float(
            log_text.split("NVM Write Latency    p90      :")[1]
            .split(" us")[0]
            .replace(",", "")
        )
        output_dict["NVM_Write_Latency_p99"] = float(
            log_text.split("NVM Write Latency    p99      :")[1]
            .split(" us")[0]
            .replace(",", "")
        )
        output_dict["NVM_Write_Latency_p99.99"] = float(
            log_text.split("NVM Write Latency    p9999    :")[1]
            .split(" us")[0]
            .replace(",", "")
        )
        output_dict["NVM_Write_Latency_p100"] = float(
            log_text.split("NVM Write Latency    p100     :")[1]
            .split(" us")[0]
            .replace(",", "")
        )

        log_text = log_text.split("== Throughput Stats ==")[-1]
        log_text = log_text.split("Total sets:")[1]

        output_dict["Get_Rate"] = float(
            log_text.split("get       :")[1].split("/s,")[0].replace(",", "")
        )
        output_dict["Set_Rate"] = float(
            log_text.split("set       :")[1].split("/s,")[0].replace(",", "")
        )

        return output_dict

    def cleanup(self, **kwargs) -> None:
        """
        This function performs the cleanup process for the SSD Fio Synthetic Workload test.

        It first restores any saved workloads that were modified during the test.

        It then deletes any RAIDed volumes that were created during the test.

        If the 'performed_resize' attribute is set to True, it also resizes the drives to their full capacity.

        Finally, it calls the parent class's cleanup method to perform any additional cleanup tasks.
        """
        self.log_info("================ Clean Up Process=======================")
        if hasattr(self, "saved_old_wl"):
            host = self.host
            self.log_info(
                f"Restoring workloads from {self.saved_old_wl} on {host.hostname}"
            )
            # First remove current folder, then restore the original folder.
            host.run(f"rm -rf {self.SSDCachebenchTest.WL_SUITES}")
            host.run(f"cp -rf {self.saved_old_wl} {self.SSDCachebenchTest.WL_SUITES}")
            self.log_info(f"Removing {self.saved_old_wl} on {host.hostname}")
            host.run(f"rm -rf {self.saved_old_wl}")

        self.log_info("++++++ Deleting the RAIDed Volumes +++++++")
        self.delete_raid_array()

        if self.performed_resize:
            self.log_info(
                "+++++++++++ Resizing the drives to Full Capacity  ++++++++++ "
            )
            self.sweep_param_key: "NvmeResizeUtil.SweepParamKeyEnum" = (
                NvmeResizeUtil.SweepParamKeyEnum["overprovisioning"]
            )
            self.sweep_param_unit: "NvmeResizeUtil.SweepParamUnitEnum" = (
                NvmeResizeUtil.SweepParamUnitEnum["percent"]
            )
            self.sweep_param_value = NvmeResizeUtil.DEFAULT_OP_PERCENT
            if self.fdp_enabled:
                FDPUtils.fdp_cleanup(self.host, self.nvme_id_ctrls)
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
                        self.sweep_param_value,
                    )
                )
                if ns_validate_queue:
                    AutovalThread.wait_for_autoval_thread(ns_validate_queue)
            self.log_info("NVME LIST AFTER CLEANUP\n" + self.host.run("nvme list"))
        super().cleanup(**kwargs)

    def _xfer_workloads(self):
        """
        Attempts to transfer workloads if they exist.
        """
        if self.input_params.local_wl_suite_folder is not None:
            local_folder = pathlib.Path(self.input_params.local_wl_suite_folder)
            if local_folder.is_dir():
                host = self.host
                # Save old workloads
                self.saved_old_wl = f"/tmp/test_configs_{self.create_timestamp()}"
                self.log_info(f"Saving old test configs at {self.saved_old_wl}")
                host.run(f"cp -rf {SSDCachebenchTest.WL_SUITES} {self.saved_old_wl}")
                # Put in new workloads
                self.log_info(
                    f"Copying test configs from {local_folder} to "
                    + f"{SSDCachebenchTest.WL_SUITES} on {host.hostname}"
                )
                host.put_folder(
                    f"{local_folder}",
                    f"{SSDCachebenchTest.WL_SUITES}",
                    overwrite=True,
                    verbose=True,
                )
            else:
                raise TestError(f"Local folder {local_folder} does not exist!")

    def _rx_run_results(self, host: Host, folder_prefix, dest: str, msgs=None):
        """
        Retrieve the cachebench results.
        """
        self.log_info(
            f"Retrieving folder with prefix {folder_prefix} from {host.hostname}"
        )
        folder_prefix = pathlib.Path(folder_prefix)

        result = host.run_get_result(
            f'find {folder_prefix.parent} -maxdepth 1 -type d -name "{folder_prefix.name}*" -print',
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

    def _process_results(self, host: Host, folder: str, msgs=None):
        """
        Extract the data.
        """
        self.log_info(f"Processing results in {folder}")
        results = pathlib.Path(folder)

        config_path = os.path.join(
            folder,
            host.run(f'cd {folder} && find . -type f -name "config.json"').strip("./"),
        )
        config_results = json.loads(host.run(f"cat {config_path}"))

        results = str(host.run(f"cd {folder} && ls")).split("\n")
        file_name = ""
        for i in results:
            if i.endswith(".log"):
                file_name = i
                break

        log_data = str(host.run(f"cd {folder} && cat {file_name}"))

        log_text = log_data.split("== Allocator Stats ==")[-1]
        allocator_stats = log_text.split("== Hit Ratio Stats Since Last ==")[0]

        remaining_stats = log_text.split("== Hit Ratio Stats Since Last ==")[1].split(
            "== Throughput Stats =="
        )
        hit_ratio_stats_since_last = remaining_stats[0]
        throughput_stats = remaining_stats[1]

        allocator_stats = allocator_stats.split("\n")
        hit_ratio_stats_since_last = hit_ratio_stats_since_last.split("\n")
        throughput_stats = throughput_stats.split("\n")

        cachebench_results = {}
        allocator_stats_data = {}
        hit_ratio_stats_since_last_data = {}
        throughput_stats_data = {}

        for lines in allocator_stats:
            if ":" in lines:
                allocator_stats_data.update(self.clean_log_data(line=lines))
        cachebench_results["Allocator Stats"] = allocator_stats_data

        for lines in hit_ratio_stats_since_last:
            if ":" in lines:
                # hit_ratio_stats_since_last_data.append(
                #     self.clean_log_data(line_data=lines)
                # )
                hit_ratio_stats_since_last_data.update(self.clean_log_data(lines))
        cachebench_results["Hit Ratio Stats Since Last"] = (
            hit_ratio_stats_since_last_data
        )

        for lines in throughput_stats:
            if ":" in lines:
                throughput_stats_data.update(self.clean_log_data(line=lines))
        cachebench_results["Throughput Stats"] = throughput_stats_data

        return (config_results, cachebench_results)

    def clean_log_data(self, line: str) -> t.Union[dict, set]:
        cleaned_data = {}
        count_colon = line.count(":")
        log_data = line.split(":")
        if count_colon == 1:
            cleaned_data[f"{log_data[0].strip()}"] = log_data[1].strip()
        elif (
            (count_colon == 3)
            and (log_data[0].count(",") == 0)
            and (log_data[1].count(",") == 0)
            and (log_data[3].count(",") == 0)
        ):
            head1 = log_data[0].strip()
            sub_head1 = log_data[1].strip()
            val1 = log_data[2].strip().split(" ")[0].strip(",")
            sub_head2 = log_data[2].strip().split(" ")[1]
            val2 = log_data[3].strip()
            cleaned_data[head1 + " " + sub_head1] = val1
            cleaned_data[head1 + " " + sub_head2] = val2

        else:
            log_data = [data.strip() for data in log_data]
            temp_data = [log_data[0]]
            for count in range(1, count_colon):
                elem = log_data[count].split(" ", 1)
                elem = [element.strip(" ,") for element in elem]
                temp_data += elem
            temp_data.append(log_data[-1])
            cleaned_data[temp_data[0]] = temp_data[1]
            for i in temp_data[2::2]:
                cleaned_data[f"{temp_data[0]} {i}"] = temp_data[temp_data.index(i) + 1]
        return cleaned_data


class JsonUpdate:
    @staticmethod
    def update_JSON_file_dict(host, file_path, json_dict):
        for key, value in json_dict.items():
            JsonUpdate.update_JSON_file_key(host, file_path, key, value)

    @staticmethod
    def update_JSON_file_key(host, file_path, JSON_key_path, new_value):
        """
        Method to update the JSON parameters of Cachebench Config

        """
        new_value = str(new_value).replace("'", '"').replace(" ", "")
        cmd = "cat %s | echo \"$(jq '.%s = %s')\" > %s" % (
            file_path,
            JSON_key_path,
            new_value,
            file_path,
        )
        host.run(cmd)
        updated_JSON_value = (
            JsonUpdate.get_JSON_file_key(host, file_path, JSON_key_path)
            .replace("\n", "")
            .replace(" ", "")
        )

        AutovalUtils.validate_equal(
            new_value,
            updated_JSON_value,
            "Successfully JSON %s key %s value set to %s"
            % (file_path, JSON_key_path, new_value),
        )

    @staticmethod
    def get_JSON_file_key(host, file_path, JSON_key_path):
        """
        Method to update the JSON parameters of Cachebench Config

        """

        cmd = "jq '.%s' %s" % (JSON_key_path, file_path)
        return host.run(cmd)
