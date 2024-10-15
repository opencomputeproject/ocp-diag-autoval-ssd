#!/usr/bin/env python3

# pyre-unsafe
import copy
import os
import queue
import re
import time
from typing import List

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
from autoval_ssd.lib.utils.storage.nvme.latency_monitor_utils import LatencyMonitor
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase
from autoval_ssd.lib.utils.system_utils import SystemUtils

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
        self.precondition_loops = self.test_control.get("precondition_loops", 0)
        self.go_bin: str = "/bin/go"
        self.go_script: str = ""
        self.precondition_template = self.test_control.get(
            "precondition_template", "precondition.fio"
        )
        self.iogo_runtime = self.test_control.get("iogo_runtime", 120)
        self.trimrate = self.test_control.get("trimrate", False)
        self.workload = self.test_control.get("workload", "TrimRate")
        self.mnt = "/mnt/havoc"
        self.secure_erase_option = self.test_control.get("secure_erase_option", 0)
        self.fio_synth_options = self.test_control.get("fio_synth_options", None)
        self.lm_enabled_drives = []

    # @override
    def setup(self, *args, **kwargs) -> None:
        self.storage_test_tools.extend(["fiosynth"])
        super().setup(*args, **kwargs)
        # Setup fio
        if self.test_drives:
            self.test_control["drives"] = self.test_drives
        if self.boot_drive:
            self.test_control["boot_drive"] = self.boot_drive

    def execute(self) -> None:
        if self.fstype == "btrfs":
            self.storage_test_tools.extend(["btrfs-progs"])
        self.go_script = self.deploy_tool()
        # Check if golang is installed on DUT
        self.install_go_lang()
        if self.trimrate:
            for device in self.test_drives:
                self.secure_erase(device.block_name)

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
                resultsdir=self.resultsdir,
                options=self.fio_synth_options,
                test_drives=self.test_drives,
                test_drive_filter=self.test_drive_filter,
            )

        go_queue = queue.Queue()
        go_threads = []

        # Create a thread per device to do the following
        # 1. Create the 'write and delete' test files
        # 2. Run ioT6.go on the write test file
        # 3. Delete the delete files

        for drive in self.test_drives:
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

        # Clean up write test files
        for device in self.test_drives:
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

        self.validate_condition(
            self._parse_results(),
            "ioT6.go completed successfully",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

    def cleanup(self, *args, **kwargs) -> None:
        # Cleanup all drives except boot drive
        drives = [d for d in self.test_drives if str(d) != str(self.boot_drive)]
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
        super().cleanup(*args, **kwargs)

    def create_and_go(self, drive) -> None:
        # Create the write test file of size 16GB
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
                iogo_log, "Deleting 10x %sMB files\n" % i, append=True, host=host
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
                    block_size=str(i) + "MB",
                )
                latency_monitor.disable(
                    working_directory=self.dut_logdir[self.host.hostname],
                )

    def _run_iogo(self, host, write_file: str, iogo_log: str) -> None:
        AutovalLog.log_info("Running ioT6.go on %s" % (write_file))
        nohup_cmd = SystemUtils.make_cmd_ssh_backgroundable(
            cmd=f"{self.go_bin} run {self.go_script} {write_file}",
            logfile=iogo_log,
        )
        cmd = f"GOCACHE=/root/go/cache {nohup_cmd}"
        host.run(cmd, timeout=6000)
        # sleep till go process triggers and perform IO for 120 seconds
        time.sleep(self.iogo_runtime)

    # Parse the log files, report if the latency exceeds 10ms
    def _parse_results(self) -> bool:
        """
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
        """
        # errors = []
        passed = True
        device_dict = {}
        total_dict = {}
        size_dict = {}
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

        for device in self.test_drives:
            iogo_log = "%s/iogo_%s.log" % (
                self.dut_logdir[self.host.hostname],
                device.block_name,
            )
            try:
                file = FileActions.read_data(iogo_log, host=self.host)
            except Exception as e:
                self.log_info("Unable to open the log file %s" % iogo_log)
                raise TestError(str(e))
            passed = False

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
                elif "warning: GOPATH set to GOROOT () has no effect" in i:
                    continue
                else:
                    # line from stderr
                    p_errors.append(f"iogo_{device.block_name}.log: {i}")
        return self.validate_dict(total_dict, device_dict, passed, sizes)

    def validate_dict(
        self, total_dict, device_dict, passed: bool, sizes: List[str]
    ) -> bool:
        # Number of file sizes per device with latency outliers > 10ms
        for device in self.test_drives:
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
            passed = True
        else:
            if self.lm_enabled_drives:
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
                passed = True
            else:
                raise TestError("\n".join(p_errors))
        return passed

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
        for device in self.test_drives:
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
