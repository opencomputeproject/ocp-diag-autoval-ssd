#!/usr/bin/env python3

# pyre-unsafe
import copy
import os
import queue
import re
from time import sleep
from typing import Dict, Iterable, List, Optional

from autoval.lib.host.component.component import COMPONENT

from autoval.lib.host.host import Host
from autoval.lib.transport.ssh import SSHConn
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.file_actions import FileActions
from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.filesystem_utils import FilesystemUtils
from autoval_ssd.lib.utils.fio.fio_synth_flash_utils import FioSynthFlashUtils
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.storage.drive import Drive
from autoval_ssd.lib.utils.storage.nvme.fdp_utils import FDPUtils
from autoval_ssd.lib.utils.storage.nvme.latency_monitor_utils import LatencyMonitor
from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase
from autoval_ssd.lib.utils.system_utils import SystemUtils
from autoval_ssd.tests.storage_hw_eng.libs.component_common_lib.component_test_base import (
    ComponentTestBase,
)
from autoval_ssd.tests.storage_hw_eng.libs.ssd_lib.ssd_test_base import (
    DRIVE_CAPACITY_POWER_STATES,
)

p_errors = []


class IoGO(StorageTestBase):
    """
    Run fio on preconditioned drives.
    For each block size, run IOGO on write files of size 16GB
    and delete the test file while IOGO is in progress
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.host_dict = {}
        self.fstype = self.test_control.get("fstype", "xfs")
        self.drive_type = self.test_control.get("drive_type", None)
        self.drive_interface = self.test_control.get("drive_interface", None)
        self.max_latency = self.test_control.get("max_latency", 0)
        self.precondition_loops = self.test_control.get("precondition_loops", 2)
        self.go_bin: str = "/bin/go"
        self.go_script: str = ""
        self.precondition_template = self.test_control.get(
            "precondition_template", "precondition.fio"
        )
        self.iogo_runtime = self.test_control.get("iogo_runtime", 120)
        self.trimrate = self.test_control.get("trimrate", False)
        self.workload = self.test_control.get("workload", "TrimRate")
        self.mnt = "/mnt/test"
        self.secure_erase_option = self.test_control.get("secure_erase_option", 0)
        self.fio_synth_options = self.test_control.get("fio_synth_options", None)
        self.collect_drive_data = self.test_control.get("collect_drive_data", True)
        self.cleanup_test_drives = []
        self.test_specific_drives = []
        self.performed_resize = False
        self.lm_enabled_drives = []
        self.cycle = self.test_control.get("cycle_count", 1)
        self.perform_resize = self.test_control.get("perform_resize", False)
        self.dix_ns_resize = self.test_control.get("dix_ns_resize", False)
        self.fdp_setup = self.test_control.get("fdp_setup", False)
        self.fdp_enabled = False

    # @override
    def setup(self):
        FioSynthFlashUtils.tool_setup(self.host)
        super().setup()
        # Setup fio
        if self.test_drives:
            self.test_control["drives"] = self.test_drives
        if self.boot_drive:
            self.test_control["boot_drive"] = self.boot_drive

    def execute(self) -> None:
        """
        This function executes the main test logic for the ioT6.go tool.

        It first checks if the file system type is btrfs and installs the required rpm package if necessary.
        It then deploys the ioT6.go script to the DUT and checks if golang is installed on the DUT.

        It then identifies the drives that will be used for testing and performs any necessary resizing operations.
        If the 'perform_resize' parameter is set to True in the test control, it over-provisions the drives.
        Otherwise, if the 'performed_resize' attribute is set to True, it also resizes the drives to their full capacity.
        If self.dix_ns_resize is True, it will perform a DIX namespace resize instead of the normal NVMe Resize.

        It also sets the power state on the devices if specified in the test control and performs a secure erase operation if the 'trimrate' parameter is set to True.

        Finally, it creates and runs the ioT6.go script on each device in a separate thread and cleans up any files created during the test.
        """
        if self.fstype == "btrfs":
            self.storage_test_tools.extend(["btrfs-progs"])
        self.go_script = self.deploy_tool()

        # Check if golang is installed on DUT
        self.install_go_lang()

        self.test_specific_drives = ComponentTestBase.drives_executable(
            self.test_drives, self.test_control
        )
        self.log_info(f"Testing on drives: {self.test_specific_drives}")

        self.cleanup_test_drives = list(
            set(self.cleanup_test_drives + self.test_specific_drives)
        )
        self.nvme_id_ctrl_filter: str = self.test_control.get(
            "nvme_id_ctrl_filter", "True"
        )
        self.nvme_id_ctrls = NvmeResizeUtil.get_nvme_ctrls(
            self.host, self.test_drives, self.nvme_id_ctrl_filter
        )
        tnvmcap = self.nvme_id_ctrls[self.test_drives[0].block_name[:-2]]["tnvmcap"]
        _, TB_capacity = NvmeResizeUtil.get_reported_capacity(tnvmcap)
        self.drive_capacity_power_state = DRIVE_CAPACITY_POWER_STATES[TB_capacity]

        if self.dix_ns_resize:
            for dix_test_drives_list in self.dix_ns_resize_setup():
                self.set_power_state(dix_test_drives_list)
                self.trimrate_secure_erase(dix_test_drives_list)
                self.run_workload(dix_test_drives_list)
                self.cleanup_test_files(dix_test_drives_list)
                self.validate_results()

        elif self.fdp_setup:
            self.fdp_single_namespace_setup()

        elif self.perform_resize:
            self.over_provisioning_setup()

        elif self.performed_resize:
            self.resize_full_capacity()

        if not self.dix_ns_resize:
            self.set_power_state()
            self.trimrate_secure_erase()
            self.run_workload()
            self.cleanup_test_files()
            self.validate_results()

    def resize_full_capacity(self) -> None:
        """
        Resize drives to full capacity, setting OP to default.
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

    def over_provisioning_setup(self) -> None:
        """
        Configures the drives for over-provisioning by setting the sweep
        parameters (key, unit, and value) from the test control. Then
        performs resize operation on the drives to apply the over-provisioning settings.
        """
        self.log_info("+++++++++++ Over-provisioning the drives ++++++++++ ")
        self.performed_resize = True
        # Parse test_control json inputs
        try:
            self.sweep_param_key: "NvmeResizeUtil.SweepParamKeyEnum" = (
                NvmeResizeUtil.SweepParamKeyEnum[
                    self.test_control.get("sweep_param_key", None)
                ]
            )
            self.sweep_param_unit: "NvmeResizeUtil.SweepParamUnitEnum" = (
                NvmeResizeUtil.SweepParamUnitEnum[
                    self.test_control.get("sweep_param_unit", None)
                ]
            )
        except KeyError as e:
            raise TestError(f"Invalid/Missing sweep param in test_control: {str(e)}")
        self.sweep_param_value = self.test_control.get("sweep_param_value", "")

        NvmeResizeUtil.perform_resize(
            self.host,
            self.test_specific_drives,
            sweep_param_key=self.sweep_param_key,
            sweep_param_unit=self.sweep_param_unit,
            sweep_param_value=self.sweep_param_value,
            nvme_id_ctrl_filter=self.nvme_id_ctrl_filter,
            cycle=self.cycle,
        )

    def dix_ns_resize_setup(self) -> Iterable[List[Drive]]:
        """
        Set up the DIX namespace resize process for the test drives.

        This function configures the drives for DIX namespace resizing by setting the
        sweep parameters (key, unit, and value) and iterates over the LBA format combinations
        to perform the resize operation on the drives.

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
        lbaf_to_flbas_map = (
            NvmeResizeUtil.validate_drives_support_dix_resize_lba_formats(
                self.host, self.test_specific_drives
            )
        )
        self.log_info(f"lbaf to flbas map: {lbaf_to_flbas_map}")
        self.lbaf_combinations = self.test_control.get("lbaf_combinations", [])
        if self.lbaf_combinations == []:
            self.lbaf_combinations = [
                ["4096+64", "4096+64"],
                ["4096+64", "512"],
                ["4096+64", "4096"],
            ]
        dix_test_drives = self.test_specific_drives

        for resize_cycle, combo in enumerate(self.lbaf_combinations):
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
                use_existing_ns=(resize_cycle != 0),
            )
            sleep(5)

            all_drives = self.scan_drives()
            dix_test_drives = self.allocate_test_drives(all_drives)

            dix_test_drives = [
                drive
                for drive in dix_test_drives
                if any(
                    drive.block_name.startswith(test_drive.block_name[:-1])
                    for test_drive in self.test_specific_drives
                )
            ]

            self.log_info(f"test drives {dix_test_drives}")
            yield dix_test_drives

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

    def set_power_state(self, drives: Optional[List[Drive]] = None) -> None:
        """
        Set the power state of all drives in a test.
        This function uses the PowerState class to perform this action.
        Args:
            drives: A list of drives to set the power state for.
        """
        if drives is None:
            drives = self.test_specific_drives
        # Set Power State on devices
        if self.test_control.get("set_power_state", False):
            power_state = self.test_control.get("power_state", "")
            if not power_state:
                power_state = self.drive_capacity_power_state
            ComponentTestBase.power_state(
                self.host,
                drives,
                power_state_set_key=power_state,
            )

    def run_workload(self, drives: Optional[List[Drive]] = None) -> None:
        """
        Run the workload on the specified drives.
        Args:
            drives: A list of drives to run the workload on.
        """
        if drives is None:
            drives = self.test_specific_drives
        self.host_dict = AutovalUtils.get_host_dict(self.host)
        fio_runner = FioRunner(self.host, self.test_control)
        fio_runner.test_setup()
        precondition_drives = fio_runner.get_precondition_drives()
        if precondition_drives:
            fio_runner.precondition_drives(
                drives=precondition_drives,
                precondition_loops=self.precondition_loops,
                precondition_template=self.precondition_template,
                remote=False,
                mnt=self.mnt,
            )

        if self.trimrate:
            FioSynthFlashUtils.start_fio_synth_flash(
                host=self.host,
                workload=self.workload,
                resultsdir=self.dut_logdir[self.host.hostname],
                options=self.fio_synth_options,
                test_drives=drives,
                test_drive_filter=self.test_drive_filter,
            )

        go_queue = queue.Queue()
        go_threads = []

        # Create a thread per device to do the following
        # 1. Create the 'write and delete' test files
        # 2. Run ioT6.go on the write test file
        # 3. Delete the delete files

        for drive in drives:
            go_thread = AutovalThread(go_queue, self.create_and_go, drive)
            go_thread.start()
            go_threads.append(go_thread)
        d_errors = []
        for thread in list(go_threads):
            thread.join()
            go_threads.remove(thread)
            try:
                ex = go_queue.get(block=False)
                d_errors.append("Error during Iogo steps: %s" % (str(ex)))
            except queue.Empty:
                pass
            if d_errors:
                raise Exception("\n".join(d_errors))

    def trimrate_secure_erase(self, drives: Optional[List[Drive]] = None) -> None:
        """
        Perform a secure erase on the specified drives if the 'trimrate' parameter is set to True.
        Args:
            drives: A list of drives to perform the secure erase on.
        """
        if drives is None:
            drives = self.test_specific_drives
        if self.trimrate:
            for device in drives:
                self.secure_erase(device.block_name)

    def cleanup_test_files(self, drives: Optional[List[Drive]] = None) -> None:
        """
        Clean up the write test files created during the test.
        Args:
            drives: A list of drives to clean up.
        """
        if drives is None:
            drives = self.test_specific_drives
        # Clean up write test files
        for device in drives:
            mnt = self.mnt + "_%s" % (device.block_name)
            self.validate_no_exception(
                DiskUtils.umount,
                [self.host, mnt],
                "Unmount %s" % (mnt),
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.SYSTEM_ERR,
            )
            cmd = "rm -rf %s" % (mnt)
            self.validate_no_exception(
                self.host.run,
                [cmd],
                "Remove file_16GB",
                component=COMPONENT.SYSTEM,
                error_type=ErrorType.SYSTEM_ERR,
            )

    def validate_results(self) -> None:
        """
        Validate the results of the iogo test.
        """
        self.validate_condition(
            self._parse_results(),
            "ioT6.go completed successfully",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

    def cleanup(self):
        """
        This function performs the cleanup process for the test.
        It first identifies all drives that need to be cleaned up, excluding the boot drive.
        It then removes any files or directories on these drives and cleans up the file system.

        If the 'performed_resize' attribute is set to True, it also resizes the drives to their full capacity.
        """
        # Cleanup all drives except boot drive
        drives = [d for d in self.cleanup_test_drives if str(d) != str(self.boot_drive)]
        cmd = "killall go ioT6"
        self.host.run(cmd, ignore_status=True)
        for device in drives:
            mnt = self.mnt + "_%s" % device.block_name
            cmd = "rm -rf %s/*" % mnt
            self.host.run(cmd)
            AutovalUtils.validate_no_exception(
                FilesystemUtils.clean_filesystem,
                [self.host, device.block_name, mnt],
                "Clean drive %s" % device,
                raise_on_fail=False,
                log_on_pass=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
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
            self.sweep_param_value = NvmeResizeUtil.DEFAULT_OP_PERCENT
            if self.fdp_enabled:
                FDPUtils.fdp_cleanup(self.host, self.nvme_id_ctrls)
            else:
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
            AutovalLog.log_info(
                "NVME LIST AFTER CLEANUP\n" + self.host.run("nvme list")
            )
        super().cleanup()

    def create_and_go(self, drive: Drive) -> None:
        """
        Creates a write test file of size 16GB and runs ioT6.go on it.

        Args:
            drive: The drive object on which the test will be performed.
        """
        latency_monitor = LatencyMonitor(
            host=self.host,
            test_drives=[drive],
            test_control=self.test_control,
            log_lm_commands=False,
        )
        device = drive.block_name
        host = Host(self.host_dict)
        DiskUtils.remove_all_partitions(host, device)
        mnt = self.mnt + "_%s" % (device)
        iogo_log = "%s/iogo_%s.log" % (self.dut_logdir[self.host.hostname], device)
        fs_opts = ""
        if self.fstype == "btrfs":
            fs_opts = " -K "
        else:
            fs_opts = " -K -i size=2048"
        FilesystemUtils.mount(
            host,
            device,
            mnt,
            filesystem_type=self.fstype,
            filesystem_options=fs_opts,
        )
        df = FilesystemUtils.get_df_info(host, device)
        self.validate_condition(
            df["type"] == self.fstype,
            "Mount %s at %s" % (device, mnt),
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.SYSTEM_ERR,
        )
        count = 16000
        write_file = "%s/file_16GB" % (mnt)
        cmd = "dd if=/dev/zero of=%s oflag=direct bs=1M count=%s" % (write_file, count)
        host.run(cmd)
        # Next create the delete test files size upto 16GB
        # For each block size, run ioT6.go on the write file
        # and delete the test file while ioT6.go was run in the background
        block_sizes = [1, 32, 64, 128, 256, 512, 1024]
        if str(device) != self.boot_drive:
            block_sizes.extend([2048, 4096, 8192, 16384])
        AutovalLog.log_info("Create delete_files and run iogo")
        for i in block_sizes:
            lm_drive = latency_monitor.enable(
                workload="ioT6",
                working_directory=self.dut_logdir[self.host.hostname],
            )
            if lm_drive and ("".join(lm_drive) not in self.lm_enabled_drives):
                self.lm_enabled_drives.extend(lm_drive)
            for j in range(10):
                cmd = (
                    "dd if=/dev/zero of=%s/test_file_%s_%s "
                    + "oflag=direct bs=1M count=%s"
                ) % (mnt, i, j, i)
                host.run(cmd)
            FileActions.write_data(
                iogo_log, "Deleting 10x %sMB files \n" % i, append=True, host=host
            )
            self._run_iogo(host, write_file, iogo_log)
            # Remove the delete test files
            AutovalLog.log_info("%s: Deleting 10x %sMB files" % (device, i))
            cmd = "rm -rf %s/test_file_*" % (mnt)
            host.run(cmd)
            # Stop ioT6.go processes
            cmd = "killall go ioT6"
            host.run(cmd, ignore_status=True)
            if lm_drive:
                latency_monitor.collect_logs(
                    workload="ioT6",
                    synth_workload_result_dir=self.dut_logdir[self.host.hostname],
                    block_size=f"{i}MB",
                )
                latency_monitor.disable(
                    working_directory=self.dut_logdir[self.host.hostname],
                )

    def _run_iogo(self, host, write_file, iogo_log: str) -> None:
        AutovalLog.log_info("Running ioT6.go on %s" % (write_file))
        cmd = "export GOCACHE=/root/go/cache"
        host.run(cmd)
        # runs ioT6.go in the background using nohup. Output and stderr is redirected to the log file
        cmd = f"nohup {self.go_bin} run {self.go_script} {write_file} >> {iogo_log} 2>&1 </dev/null &"
        host.run(cmd, timeout=6000)
        # sleep till go process triggers and perform IO for 120 seconds
        sleep(self.iogo_runtime)

    # Parse the log files, report if the latency exceeds 10ms
    def _parse_results(self) -> bool:
        """
        Parses the log files generated by the ioT6.go tool, checks if the latency exceeds the max_latency.

        Sample content from the log file.
                Deleting 10x 1MB files
                2018-09-05 10:50:28.662143016 -0700 PDT m=+1.026250398 19.73869ms 5.20271ms 8
                Deleting 10x 32MB files
                Deleting 10x 64MB files
                Deleting 10x 128MB files
                Deleting 10x 256MB files
                Deleting 10x 512MB files
                Deleting 10x 1024MB files
                Deleting 10x 2048MB files
                Deleting 10x 4096MB files
                Deleting 10x 8192MB files
                Deleting 10x 16384MB files
                2018-09-05 11:47:24.899261699 -0700 PDT m=+3417.263369108 10.391522ms

        Returns:
            bool: True if the validation is successful from validate_dict(), False otherwise.
        """
        device_dict: Dict[str, Dict[str, int]] = {}
        total_dict: Dict[str, int] = {}
        size_dict: Dict[str, int] = {}
        sizes = [
            "1MB",
            "32MB",
            "64MB",
            "128MB",
            "256MB",
            "512MB",
            "1024MB",
            "2048MB",
            "4096MB",
            "8192MB",
            "16384MB",
        ]
        for size in sizes:
            total_dict[size] = 0

        for device in self.test_specific_drives:
            iogo_log = "%s/iogo_%s.log" % (
                self.dut_logdir[self.host.hostname],
                device.block_name,
            )
            try:
                file = FileActions.read_data(iogo_log, host=self.host)
            except BaseException as e:
                raise TestError(str(e))
                self.log_info("Unable to open the log file %s" % iogo_log)

            line_list = []
            for line in file.splitlines():
                line_list.append(line)

            for size in sizes:
                size_dict[size] = 0
            device_dict[device.block_name] = copy.deepcopy(size_dict)

            size_: str = ""
            for i in line_list:
                if re.match(r"^Deleting", i):
                    size_ = i.split()[2]
                    continue
                elif re.match(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})", i):
                    if len(i.split()) >= 6:
                        latency = re.sub(r"[^0-9\.]", "", i.split()[5])
                        str_ = re.sub(r"[^\x00-\x7f]", r" ", i.split()[5])
                        if "ms" in str_ and float(latency) >= self.max_latency:
                            p_errors.append(
                                f"[IOGO] Latency exceeding {self.max_latency}ms in device {device.block_name}, latency: {latency}ms"
                            )
                            device_dict[device.block_name][size_] += 1
                            total_dict[size_] += 1
                else:
                    # line from stderr
                    p_errors.append(f"iogo_{device.block_name}.log: {i}")
        return self.validate_dict(total_dict, device_dict, sizes)

    def validate_dict(
        self,
        total_dict: Dict[str, int],
        device_dict: Dict[str, Dict[str, int]],
        sizes: List[str],
    ) -> bool:
        """
        Validates the dictionary of file sizes and their corresponding latency outliers.
        Args:
            total_dict: A dictionary with file sizes as keys and the number of latency outliers as values.
                        For eg: {'1MB': 0, '32MB': 0, '64MB': 0}
            device_dict: A dictionary with device names as keys and dictionaries of file sizes and latency outliers as values.
                        For eg {'nvme2n1': {'1MB': 0, '32MB': 0, '64MB': 0},
                                'nvme3n1': {'1MB': 0, '32MB': 0, '64MB': 0}}
            sizes: A list of file sizes.

        Returns:
            True if the validation passed, Raise an error otherwise.
        """
        # Number of file sizes per device with latency outliers > 10ms
        for device in self.test_specific_drives:
            outliers = sum(
                1 for size in sizes if device_dict[device.block_name][size] != 0
            )
            if outliers >= 4:
                p_errors.append(
                    "[IOGO] Four or more file sizes total with latency outliers in device %s"
                    % device.block_name
                )

        # No more than 2 latency outliers per file size
        outlier_per_size = {k: v for k, v in total_dict.items() if v > 2}
        if outlier_per_size:
            p_errors.append("[IOGO] outliers per size %s" % outlier_per_size)

        if not p_errors:
            return True

        if not self.lm_enabled_drives:
            raise TestError("\n".join(p_errors))

        AutovalLog.log_info("\n".join(p_errors))
        latency_monitor = LatencyMonitor(
            host=self.host,
            test_drives=self.test_drives,
            test_control=self.test_control,
            log_lm_commands=False,
        )
        latency_monitor.parse_and_validate_results(
            synth_workload_result_dir=self.dut_logdir[self.host.hostname],
            lm_enabled_drives=self.lm_enabled_drives,
            workload="ioT6",
        )
        return True

    def install_go_lang(self) -> None:
        """
        Check if Go Lang is already installed on DUT and install it if not.

        Raises:
            Exception: If there is an error installing Go Lang
        """
        result = self.host.run("go version", ignore_status=True)
        AutovalLog.log_info(f"Result of go version: {result}")
        if "command not found" in result:
            try:
                SystemUtils.install_rpms(self.host, ["golang"])
                AutovalLog.log_info(
                    "Go Lang installed successfully. Proceeding with the test."
                )
            except Exception:
                AutovalLog.log_info(
                    "Go Lang not installed, Should be installed for iogo test to progress"
                )
        else:
            AutovalLog.log_info(
                "Go Lang is already installed. Proceeding with the test."
            )

    def get_test_params(self) -> str:
        test_desc = (
            super().get_test_params()
            + " Parameters: Drive type of {} and Drive Interface of {}"
            " with max latency as {} on filesystem {} with preconditioning"
            " {} cycle(s)".format(
                self.drive_type,
                self.drive_interface,
                self.max_latency,
                self.fstype,
                self.precondition_loops,
            )
        )
        return test_desc

    def secure_erase(self, device, verify: bool = True) -> None:
        is_formatted: bool = False
        if verify:
            is_formatted = False
            self.verify_drives_can_be_mounted()

        self.validate_no_exception(
            NVMeUtils.format_nvme,
            [self.host, device, self.secure_erase_option],
            "NVME Formatting on device %s" % (device),
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        # Mount must fail, as the FS has been erased by format_nvme with secure_erase
        if verify:
            try:
                mnt = self.mnt + "_" + device
                FilesystemUtils.mount(self.host, device, mnt, force_mount=False)
            except Exception:
                is_formatted = True
            self.validate_condition(
                is_formatted,
                "Formatting verified on device %s" % (device),
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

    def verify_drives_can_be_mounted(self) -> None:
        for device in self.test_specific_drives:
            mnt = self.mnt + "_" + device.block_name
            FilesystemUtils.mount(
                self.host, device.block_name, mnt, filesystem_type=self.fstype
            )
            df = FilesystemUtils.get_df_info(self.host, device.block_name)
            self.validate_condition(
                df["type"] == self.fstype,
                "Mounted %s at %s" % (device.block_name, mnt),
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.SYSTEM_ERR,
            )
            FilesystemUtils.unmount(self.host, mnt)

    def deploy_tool(self) -> str:
        """
        Copies ioT6.go file to the dut_tmpdir
        """
        tool_path = "tools"
        templ_filename = "ioT6.go"
        file_path = FileActions.get_resource_file_path(
            os.path.join(tool_path, templ_filename), module="autoval_ssd"
        )
        AutovalLog.log_info(f"File Path: {file_path}")
        remote_path = os.path.join(self.dut_tmpdir[self.host.hostname], "ioT6.go")
        AutovalLog.log_info(f"Executable Path on the remote DUT: {remote_path}")
        SSHConn.put_file(self.host, file_path, remote_path)
        self.host.run(f"chmod +x -R {remote_path}")
        return remote_path
