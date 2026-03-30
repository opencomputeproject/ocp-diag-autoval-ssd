#!/usr/bin/env python3

# pyre-unsafe
"""library to manage fio tool"""

import datetime
import itertools
import json
import os
import random
import re
import time
from typing import Any, Optional, Tuple, Union

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.host.host import Host
from autoval.lib.test_utils.test_utils_base import TestUtilsBase
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError, ToolError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalUtils, CmdResult
from autoval.lib.utils.decorators import ignored
from autoval.lib.utils.file_actions import FileActions
from autoval.lib.utils.site_utils import SiteUtils
from autoval.lib.utils.uperf_test_util import ThresholdConfig
from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.filesystem_utils import FilesystemUtils
from autoval_ssd.lib.utils.storage.drive import Drive
from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.storage.storage_utils import StorageUtils
from autoval_ssd.lib.utils.system_utils import SystemUtils

LIB_PATH = "lib/utils/jobfile_templates"
JOBFILE_PATH = "/usr/local/FioSynth/jobfiles"
FILE = []
RUNTIME = 300
COMPARISON_MAP = {
    "<": AutovalUtils.validate_less,
    ">": AutovalUtils.validate_greater,
    "==": AutovalUtils.validate_equal,
    "!=": AutovalUtils.validate_not_equal,
    "<=": AutovalUtils.validate_less_equal,
    ">=": AutovalUtils.validate_greater_equal,
    "in": AutovalUtils.validate_in,
    "not in": AutovalUtils.validate_not_in,
}


class FioRunner(TestUtilsBase):
    """FioRunner test.

    This util installs fio on the DUT drives, creates fio job file with the given
    template file, runs the fio job file on the DUT and verifies the fio result
    output file for any errors.
    """

    prefix_command_name = None
    prefix_cmd = None
    raw_result = {}
    metric_result = {}
    threshold_obj_dict = {}
    user_criteria = {}
    fio_runner_threshold_config = "/autoval/thresholds/fio_runner"
    MOUNTED_DRIVE_FIO_PATH = "/root/autoval_fio_file"
    IOPS = 0
    IOPS_DIFF = 0.0
    LATENCY_MS_100_THRESHOLD = 0
    METRICS_TO_VALIDATE = [
        "write_max_lat",
        "read_99.000000",
        "write_99.000000",
        "write_bw",
        "read_bw",
        "read_max_lat",
    ]

    METRICS_IN_NS = [
        "write_max_lat",
        "read_99.000000",
        "write_99.000000",
        "read_max_lat",
    ]

    def __init__(self, host, args) -> None:
        """Initializes the FIO Runner test.

        This method gets the logging directories and assigns the variables
        with the arguments passed for the given hosts.

        Parameters
        ----------
        host : :obj: 'Host'
            Host on which fio jobs needs to be run.
        args : Dictionary {String,String}
               Supported args are:
               drive_interface = Dictionary {String,String}. Here default
               value is None.
               drive_type = Dictionary {String,String}. Here default value
               is None.
               drives = Dictionary {String,String}. Here default value is
               None.
               job_name = Dictionary {String,String}. Here default value is
               None.
               cycle = Dictionary {String,Integer}. Here default value is 1.
               trim_arg = Dictionary {String,Dictionary{String,String}}.
               Here default value is {}.
               run_definition = Dictionary {String,String}.
        """
        logdirs = SiteUtils().get_log_dirs()
        self.precondition_params = {}
        self.tmp_logdir = logdirs["control_server_logdir"]
        if host.hostname == "localhost":
            self.resultsdir = list(logdirs["dut_logdir"].values())[0]
        else:
            self.resultsdir = logdirs["dut_logdir"][host.hostname]
        self.ignore_remote_fio_error = True
        self.host = host
        self.args = args
        self.fio_file = None
        self.fio_ver = args.get("fio_ver", "fio-3.32")
        self.remote_fio = args.get("remote_fio", False)
        self.drive_interface = args.get("drive_interface", None)
        self.drive_type = args.get("drive_type", None)
        self.drives = args.get("drives", None)
        self.test_drives = args.get("test_drives", None)
        self.boot_drive = args.get("boot_drive", None)
        self.job_name = args.get("job_name", "")
        self.cycle = args.get("cycle_count", 1)
        self.power_random_time = args.get("power_random_time", True)
        self.power_cycle = args.get("power_cycle", "warm")
        self.trim_arg = args.get("trim_arg", {})
        self.run_definition = args.get("run_definition", {})
        self.power_trigger = args.get("power_trigger", False)
        self.power_trigger_prefix = args.get("power_trigger_prefix", "")
        self.status_interval = args.get("status_interval", 1)
        self.skip_direct: bool = args.get("skip_direct", False)
        self.rescan_data_drives = args.get("rescan_data_drives", False)
        self.enable_performance_metrics_validation = args.get(
            "enable_performance_metrics_validation", False
        )
        self.boot_drive_physical_location = args.get("boot_drive_physical_location", "")
        fio_timeout = args.get("fio_timeout", 86400)
        try:
            self.fio_timeout = int(fio_timeout)
        except Exception:
            raise TestError(
                "fio_timeout should be integer",
                error_type=ErrorType.INPUT_ERR,
            )
        self.skip_iops = args.get("skip_iops_validation", False)
        self.fio_mnt_path = "/mnt/fio_test_%s"
        self.test_boot_drive = False
        if args.get("only_boot_drive", False) or args.get("include_boot_drive", False):
            self.test_boot_drive = True
        FioRunner.prefix_command_name = args.get("prefix_command_name", "")
        self.prefix_cmd_dict = {
            "workload.slice": {
                "prefix_cmd": "systemd-run -P --slice workload.slice --working-directory=WORKING_DIR",
                "logs_dir": [
                    "/sys/fs/cgroup/task/workload.slice/",
                    "/sys/fs/cgroup/workload.slice/",
                ],
            }
        }
        self.boot_drive_partitioned: bool = False
        self.create_boot_drive_partition: bool = args.get(
            "create_boot_drive_partition", False
        )
        self.boot_drive_precondition = args.get(
            "boot_drive_precondition", self.test_boot_drive
        )
        self._current_test_params: dict[str, Any] = {}
        self.test_generic_drives = args.get("test_generic_drives", False)
        self.t10_dix_format = args.get("t10_dix_format", False)
        self.qlc_perf_test = args.get("qlc_perf_test", False)
        self.slc_stress_test = args.get("slc_stress_test", False)
        self.add_qlc_trim = args.get("add_qlc_trim", False)
        self.workload_type = args.get("workload_type", None)

    def test_setup(self) -> None:
        SystemUtils.install_rpms(
            self.host, ["fio", "sshpass", "boost-program-options", "fio-engine-libaio"]
        )
        if self.remote_fio:
            self.check_fio_version(self.host.localhost)
        self.check_fio_version(self.host)
        if self.drives is not None:
            for drive in self.drives:
                mnt = self.fio_mnt_path % drive
                if FilesystemUtils.is_mounted(self.host, mnt):
                    FilesystemUtils.unmount(self.host, mnt)
        self.host.run(
            cmd=f"rm -f {FioRunner.MOUNTED_DRIVE_FIO_PATH}", ignore_status=True
        )

        user_criteria = {}
        if self.workload_type:
            user_criteria["workload"] = [self.workload_type]

        if self.create_boot_drive_partition:
            if self.drives and self.boot_drive in self.drives:
                self.boot_drive_fio_setup()
            else:
                AutovalLog.log_info(
                    "Boot drive is not in the list of test drives, skipping boot drive partition creation"
                )

        if self.t10_dix_format:
            self.format_t10_dix_drives()

        try:
            FioRunner.threshold_obj_dict = ThresholdConfig().get_threshold(
                filepath=FioRunner.fio_runner_threshold_config,
                user_metric_list=["iops", "iops_diff", "latency_100"]
                + FioRunner.METRICS_TO_VALIDATE,
                user_criteria=user_criteria,
            )
            AutovalLog.log_info("FioRunner threshold config file found")
        except FileNotFoundError as e:
            AutovalLog.log_info(f"FioRunner threshold config file not found: {e=}")
            pass
        if (
            "iops" in FioRunner.threshold_obj_dict
            and FioRunner.threshold_obj_dict["iops"]
        ):
            FioRunner.IOPS = FioRunner.threshold_obj_dict["iops"].value
            AutovalLog.log_info(f"Defined threshold : iops {FioRunner.IOPS}")
        else:
            FioRunner.IOPS = 0
            AutovalLog.log_info(f"Expected iops threshold {FioRunner.IOPS}.")

        if (
            "iops_diff" in FioRunner.threshold_obj_dict
            and FioRunner.threshold_obj_dict["iops_diff"]
        ):
            FioRunner.IOPS_DIFF = FioRunner.threshold_obj_dict["iops_diff"].value / 100
            AutovalLog.log_info(f"Defined threshold : iops_diff {FioRunner.IOPS_DIFF}")
        else:
            FioRunner.IOPS_DIFF = 0.2
            AutovalLog.log_info(f"Expected iops diff threshold {FioRunner.IOPS_DIFF}.")

        if (
            "latency_100" in FioRunner.threshold_obj_dict
            and FioRunner.threshold_obj_dict["latency_100"]
        ):
            FioRunner.LATENCY_MS_100_THRESHOLD = FioRunner.threshold_obj_dict[
                "latency_100"
            ].value
            AutovalLog.log_info(
                f"Defined threshold : latency_100 {FioRunner.LATENCY_MS_100_THRESHOLD}"
            )
        else:
            FioRunner.LATENCY_MS_100_THRESHOLD = 100
            AutovalLog.log_info(
                f"Expected latency_100 threshold {FioRunner.LATENCY_MS_100_THRESHOLD}."
            )

    def check_fio_version(self, host):
        """
        Checks FIO version on specified host.
        """
        version = self.get_version(host)
        fio_ver_dut = version.split("fio-")
        AutovalLog.log_info("fio version on the host is %s " % fio_ver_dut[1])
        fio_version = self.fio_ver.split("fio-")
        AutovalLog.log_info("Expected fio version is %s " % fio_version[1])
        if fio_ver_dut[1] >= fio_version[1]:
            AutovalLog.log_info(
                "The fio version on the host is greater than the expected version"
            )
            return True
        else:
            AutovalLog.log_info(
                "The fio version on the host is lesser than the expected version, so will update the fio before proceeding"
            )
            self.update_fio_version(host)
            return False

    def get_version(self, host) -> str:
        """Helper function to get fio version"""
        version = host.run(cmd="fio -v")
        if not version:
            AutovalLog.log_info("FIO version is UNKNOWN, reinstalling")
            self.update_fio_version(host)
            version = host.run(cmd="fio -v")
        return version

    def update_fio_version(self, host) -> None:
        """Helper function to update fio version"""
        SystemUtils.uninstall_rpms(host, ["fio"])
        SystemUtils.install_rpms(host, ["fio", "fio-engine-libaio"])

    def clean_previous_fio_session(self) -> None:
        """Kill previous FIO jobs if existed"""
        try:
            out = self.host.run(cmd="ps -aux | grep fio | grep -v grep")
            AutovalLog.log_info(
                msg=f"WARNING: Previous FIO jobs are running. Killing:\n{out}"
            )
            try:
                self.host.run(cmd="pkill fio")
            except Exception:
                AutovalLog.log_info(msg=f"Failed to kill FIO jobs:\n{out}")
        except Exception:
            pass

    def get_drives(self, drive_type, drive_interface, drives):
        """Gets the drive values on the host.

        This method gets the drive values based on the drive type and
        drive interface on the host from available drives.

        Parameters
        ----------
        host            : :obj: 'Host'
            Host on which fio needs to be run.
        drive_type      : String. May be None
            Type of drive (HDD/SSD/MD) present on the host.
        drive_interface : String. May be None
            Type of drive interface (NVME/SAS/SATA) present on the host.
         drives: list of available drive's objects. May be None

        Returns
        -------
        all_drives     : :obj: 'List' of 'String'
            List of drives present on the host.
        """
        drive_name_list = []
        if drives:
            for drive in drives:
                drive_name_list.append(drive.block_name)

        test_drives = StorageUtils().get_test_drives(
            self.host,
            drive_type=drive_type,
            drive_interface=drive_interface,
            drives=drive_name_list,
        )
        all_drives = list(test_drives.values())
        _len = len(all_drives)
        AutovalLog.log_info(f"Available {_len} {drive_type} drives: {all_drives}")
        return all_drives

    def create_filesystem_mount(
        self,
        host,
        drives,
        filesystem_type: Optional[str] = "xfs",
        filesystem_options: Optional[str] = " -K -i size=2048",
        parallel: bool = True,
    ) -> None:
        """Creates and mounts filesystem.

        This method creates and mounts the "xfs" filesystem on the host
        and verifies the created xfs using df command.

        Parameters
        ----------
        host   : :obj: 'Host'
           Host on which fio needs to be run.

        Returns
        -------
        drives : :obj: 'List' of 'String'
           List of drives present on the host.

        Raises
        ------
        TestStepError
            When fails to mount XFS File System on the drive.
        """
        threads = []
        host_dict = AutovalUtils.get_host_dict(host)
        for device in drives:
            mnt = self.fio_mnt_path % device
            if not FilesystemUtils.is_mounted(host, mnt):
                if parallel:
                    threads.append(
                        AutovalThread.start_autoval_thread(
                            FilesystemUtils.mount,
                            host_dict,
                            device,
                            mnt,
                            filesystem_type=filesystem_type,
                            filesystem_options=filesystem_options,
                        )
                    )
                else:
                    FilesystemUtils.mount(
                        host,
                        device,
                        mnt,
                        filesystem_type=filesystem_type,
                        filesystem_options=filesystem_options,
                    )
        if parallel:
            AutovalThread.wait_for_autoval_thread(threads)
        # Verify mount
        for device in drives:
            df_info = FilesystemUtils.get_df_info(host, device)
            AutovalUtils.validate_equal(
                df_info["type"],
                filesystem_type,
                # pyre-fixme[61]: `mnt` is undefined, or not always defined.
                f"Mounted {device} at {mnt}",
                log_on_pass=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.SYSTEM_ERR,
            )

    def create_fio_job(
        self,
        files: Optional[dict[str, str]] = None,
        drive_type: Optional[str] = None,
        drive_interface: Optional[str] = None,
        drives: Optional[list[str | Drive]] = None,
        replace: Optional[dict[str, str]] = None,
        templ_filename: str = "",
        job_name: Optional[str] = None,
        filesystem: Optional[bool] = None,
        filesystem_type: Optional[str] = None,
        filesystem_options: Optional[str] = None,
        skip_fs: bool = False,
        directory: Optional[bool] = None,
        dest_job_file: Optional[str] = None,
        precondition: bool = False,
        cpu_drive_mapping: Optional[dict[str, list[str]]] = None,
    ) -> str:
        """
        Creates an FIO job file based on a template and the specified drives.

        This method determines which drives to test, processes the template,
        optionally creates or mounts filesystems, adds device-specific or
        trim-based sections, writes out the job file, and copies it
        into the results directory.

        Args:
            files: FIO job files to use. Defaults to None.
            drive_type: Drive type filter (e.g. HDD, SSD). Defaults to None.
            drive_interface: Drive interface filter (e.g. NVME, SAS, SATA). Defaults to None.
            drives: Explicit list of drives to include. Defaults to None.
            replace: Placeholder replacements for the template. Defaults to {}.
            templ_filename: Template file name to base the job on. Defaults to empty string.
            job_name: Name for the generated job file. Defaults to the template name.
            filesystem: Whether to create a filesystem before running jobs.
            filesystem_type: Type of filesystem to create.
            filesystem_options: Options for filesystem creation.
            skip_fs: If true, skips filesystem creation and just mounts existing ones.
            directory: If true, uses directory mode instead of raw-device mode.
            dest_job_file: Directory where the final job file will be placed.
            precondition: Whether to include a precondition step in the job file.
            ublkb_trim: Whether to add trim sections for ublkb devices.
            trim_percent: Percentage of each drive to trim when trim is enabled.

        Returns:
            Path to the job file copied into the results directory.

        """
        file_path = False
        replace = replace or {}

        if self.qlc_perf_test:
            replace["MDSIZE"] = self.get_qlc_md_size(replace)

        if not files and not drives:
            drives = self.get_drives(drive_type, drive_interface, drives)
        if templ_filename in FILE:
            templ_path = os.path.join(JOBFILE_PATH, templ_filename)
            file_path = True
        else:
            templ_path = FileActions.get_resource_file_path(
                os.path.join(LIB_PATH, templ_filename), module="autoval_ssd"
            )
        idx = 0
        dev_str, _size = self._process_template(templ_path, replace, file_path)
        dev_str, global_blocksize_removed = self._remove_gloabal_blocksize(dev_str)

        if filesystem and not skip_fs:
            self.create_filesystem_mount(
                self.host, drives, filesystem_type, filesystem_options
            )
        elif skip_fs:
            mnt = "/mnt/fio_test_%s/"
            FilesystemUtils.mount_all(self.host, drives, mnt, force_mount=False)

        if self.slc_stress_test:
            dev_str = self._add_slc_stress_fio_options(dev_str, drives)
        else:
            numa_cpu_nodes = None
            for device in drives:
                device_name = self._get_device_name_for_test(device)

                if cpu_drive_mapping:
                    numa_cpu_nodes = next(
                        (
                            key
                            for key, value in cpu_drive_mapping.items()
                            if device_name in [str(v) for v in value]
                        ),
                        None,
                    )
                dev_str = self._add_device_fio_options(
                    dev_str,
                    device_name,
                    filesystem,
                    directory,
                    idx,
                    _size,
                    files,
                    global_blocksize_removed,
                    numa_cpu_nodes,
                )
                idx += 1
            # For tests executed from BG runner
            dev_str = self._add_boot_drive_fio_options(
                dev_str, drives, precondition, _size, idx, files
            )

            if self.add_qlc_trim:
                dev_str = self._add_qlc_trim_job(dev_str, drives, idx, replace)

        if not job_name:
            job_name = templ_filename
        job_file = os.path.join(self.tmp_logdir, job_name)
        if dest_job_file is None:
            dest_job_file = os.path.join(self.resultsdir, job_name)
        else:
            dest_job_file = os.path.join(dest_job_file, job_name)
        FileActions.write_data(job_file, dev_str)
        # Copy fio job file to result log directory
        with ignored(Exception, exception_string="already exists"):
            self.host.put_file(job_file, dest_job_file)
        AutovalLog.log_info(f"Job file used: {dest_job_file}")

        if not precondition:
            self._current_test_params.update(
                {"global_params": self.get_global_values_dict(dev_str)}
            )

        return dest_job_file

    def _process_template(
        self, templ_path: str, replace: dict[str, str], file_path: bool
    ) -> Tuple[str, str]:
        """
        Process template file and create dev string

        Args:
            templ_path: Path to template file
            replace: Dictionary of key-value pairs to replace in template file

        Returns:
            Dev string and size
        """
        if file_path:
            content = FileActions.read_data(templ_path, host=self.host)
        else:
            content = FileActions.read_data(templ_path)
        _size = ""
        for key, value in replace.items():
            regex_var = re.compile(f"\\${{{key}}}", re.MULTILINE)
            content = re.sub(regex_var, f"{value}", content)
            regex = re.compile(f"={key}", re.MULTILINE)
            content = re.sub(regex, f"={value}", content)
            if key == "SIZE":
                _size = value
            if key == "RUNTIME":
                self.fio_timeout = DiskUtils.get_seconds(value) + 600
            # when allow_mounted_write value is passed as a argument value
            if key == "ALLOW_MOUNTED_WRITE":
                content = content + key.lower() + "=" + str(value)
        dev_str = content + "\n"

        if self.skip_direct:
            if "direct=1" in dev_str:
                dev_str = dev_str.replace("direct=1", "direct=0")
            else:
                dev_str += "direct=0\n"

        return dev_str, _size

    def _remove_gloabal_blocksize(self, dev_str: str) -> Tuple[str, bool]:
        """
        Remove global blocksize from dev_str

        Args:
            dev_str: String containing dev_str

        Returns:
            String with global blocksize removed, and flag indicating if global blocksize was removed
        """
        if "bs=BLKSIZE" in dev_str:
            dev_str = dev_str.replace("\nbs=BLKSIZE", "")
            return (dev_str, True)

        return (dev_str, False)

    def _get_device_name_for_test(self, device: str | Drive) -> str:
        """
        Get device name for testing based on test_generic_drives flag.

        Args:
            device: Device object or device name string

        Returns:
            Device name string (either block_name or generic_name)

        Raises:
            TestError: If unable to get generic name for drive when test_generic_drives is True
        """
        if isinstance(device, Drive):
            device_name = (
                device.generic_name if self.test_generic_drives else device.block_name
            )
        else:
            device_name = str(device)

        if self.test_generic_drives and not device_name.startswith("ng"):
            raise TestError(
                f"Unable to get generic name for drive {device}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

        return device_name

    def _add_device_fio_options(
        self,
        dev_str: str,
        device: str,
        filesystem: Optional[bool],
        directory: Optional[bool],
        idx: int,
        _size: str,
        files: Optional[dict[str, str]],
        global_blocksize_removed: bool,
        numa_cpu_nodes: Optional[str] = None,
    ) -> str:
        """
        Add device fio options to dev_str

        Args:
            dev_str: String containing dev_str
            device: Device name
            filesystem: Filesystem type
            directory: Directory name
            idx: Index of device
            _size: Size of device
            files: Files to be used for fio

        Returns:
            String with device fio options added
        """
        if filesystem:
            dev_str += f"[job{idx}]\n"
            _file = f"/mnt/fio_test_{device}/file1"
            dev_str += f"filename={_file}\n"
            dev_str += "fdatasync=1\n"
            # if size specified as %, create file,
            # otherwise fio will not be able to create file and it will fail
            file_size = self._create_file(device, _file, _size)
        elif directory:
            dev_str += f"[d{idx}]\n"
            dev_str += f"directory={device}\n"
            dev_str += "fdatasync=1\n"
        else:
            dev_str += f"[job{idx}]\n"
            if numa_cpu_nodes:
                dev_str += f"numa_cpu_nodes={numa_cpu_nodes}\n"
            if str(device) == str(self.boot_drive):
                if self.boot_drive_partitioned:
                    dev_str += f"filename={self.get_boot_drive_fio_partition()}\n"
                    dev_str += "fdatasync=1\n"

                elif DiskUtils.is_drive_mounted(self.host, str(self.boot_drive)):
                    if not _size:
                        _size = "100%"
                    # Safety write to boot drive
                    if files:
                        _file = files["file"]
                    else:
                        _file = FioRunner.MOUNTED_DRIVE_FIO_PATH
                    dev_str += f"filename={_file}\n"
                    file_size = self._create_file(device, _file, _size)
                    dev_str += f"size={file_size}\n"
                    dev_str += "fdatasync=1\n"
                else:
                    dev_str += f"filename=/dev/{str(self.boot_drive)}\n"
            else:
                # use raw device
                dev_str += f"filename=/dev/{str(device)}\n"

        dev_str = self._add_device_block_size(global_blocksize_removed, dev_str, device)
        dev_str += "new_group=1\n"

        return dev_str

    def _add_slc_stress_fio_options(
        self, dev_str: str, drives: list[str | Drive]
    ) -> str:
        """
        Add SLC stress fio options to dev_str for each drive.

        For each drive the function creates two job sections:
        1. A write job
        2. A trim job

        Args:
            dev_str: Base string containing the fio job definitions.
            drives: List of drive names or Drive objects.

        Returns:
            The updated job string with the two job sections added for each drive.
        """
        idx = 0
        flow_id = 1
        for device in drives:
            device_name = self._get_device_name_for_test(device)

            job_definitions = (
                f"\n[job{idx}]\n"
                "rw=randwrite\n"
                f"filename=/dev/{device_name}\n"
                f"flow_id={flow_id}\n"
                "flow=1\n"
                "new_group=1\n"
            )
            idx += 1

            job_definitions += (
                f"\n[job{idx}]\n"
                "rw=randtrim\n"
                f"filename=/dev/{device_name}\n"
                f"flow_id={flow_id}\n"
                "flow=2\n"
                "new_group=1\n"
            )
            idx += 1
            flow_id += 1

            dev_str += job_definitions

        return dev_str

    def _add_device_block_size(
        self, global_blocksize_removed: bool, dev_str: str, device: str | Drive
    ) -> str:
        """
        Add device block size to dev_str

        Args:
            global_blocksize_removed: Flag indicating if global blocksize was removed
            dev_str: String containing dev_str
            device: Device name

        Returns:
            String with device block size added
        """
        if global_blocksize_removed:
            device_str = str(device)
            if re.search(r"p\d$", device_str):
                device_str = re.sub(r"p\d$", "", device_str)
            lbads_flag_value = NvmeResizeUtil.get_lbaf_details(
                self.host, device_str[0:-2], nsid=int(device_str[-1])
            )["lbads"]
            device_block_size = str(2 ** (lbads_flag_value)) + "B"
            dev_str += f"bs={device_block_size}\n"

        return dev_str

    def _add_boot_drive_fio_options(
        self,
        dev_str: str,
        drives: list[str | Drive],
        precondition: bool,
        _size: str,
        idx: int,
        files: Optional[dict[str, str]],
    ) -> str:
        """
        Add boot drive fio options to dev_str

        Args:
            dev_str: String containing dev_str
            drives: List of drives
            precondition: Flag indicating if test is precondition
            _size: Size of device
            idx: Index of device
            files: Files to be used for fio

        Returns:
            String with boot drive fio options added
        """
        if (
            self.test_boot_drive
            and str(self.boot_drive) not in str(drives)
            and (not precondition or self.boot_drive_precondition)
        ):
            if self.boot_drive != "" and str(self.boot_drive) != "rootfs":
                dev_str += f"[job{idx}]\n"
                dev_str += "new_group=1\n"
                if self.boot_drive_partitioned:
                    dev_str += f"filename={self.get_boot_drive_fio_partition()}\n"
                    dev_str += "fdatasync=1\n"

                elif DiskUtils.is_drive_mounted(self.host, str(self.boot_drive)):
                    _file = files["file"] if files else FioRunner.MOUNTED_DRIVE_FIO_PATH
                    dev_str += f"filename={_file}\n"
                    file_size = self._create_file(self.boot_drive, _file, _size)
                    dev_str += f"size={file_size}\n"
                    dev_str += "fdatasync=1\n"
                else:
                    dev_str += f"filename=/dev/{str(self.boot_drive)}\n"
        return dev_str

    def _create_file(self, device: str, _file: str, _size: str):
        """
        Create fio file if not existed. Delete if existed
        """
        if FileActions.exists(_file, self.host):
            file_size = DiskUtils.get_size_of_directory(self.host, _file, "b")
            if file_size:
                return file_size
            FileActions.rm(_file, self.host)
        if str(device) == str(self.boot_drive):
            df_info = FilesystemUtils.get_df_info(self.host, device, search="/")
            if isinstance(list(df_info.values())[0], dict):
                # New kernel showed "/dev" instead of "/"
                df_info = FilesystemUtils.get_df_info(self.host, device, search="/dev")
        else:
            df_info = FilesystemUtils.get_df_info(self.host, device)
        AutovalLog.log_info(f"Device {device} info: {df_info}")
        try:
            available_size = int(df_info[f"/dev/{str(device)}"]["available"])
        except KeyError:
            available_size = int(df_info["available"])
        available_size_75_per = round(available_size * 75 / 100)
        if _size and "%" in _size:
            # prevent out of space
            # if user input greater than 75% of the drive available size, reset to 75%
            if float(_size.strip("%")) > 75.0:
                AutovalLog.log_info(
                    f"{device}: size {_size} is greater than 75% of available size"
                )
                _size = "75%"
                file_size = available_size_75_per
            else:
                multiplicator = float(_size.strip("%")) / 100
                file_size = round(available_size * multiplicator)
        else:
            # prevent out of space
            _size_in_bytes = DiskUtils.get_bytes(_size)
            if _size_in_bytes > available_size_75_per:
                AutovalLog.log_info(
                    f"{device}: size {_size_in_bytes} is greater than 75% of available size"
                )
                file_size = available_size_75_per
            else:
                file_size = _size
        DiskUtils.create_file(self.host, _file, file_size)
        return file_size

    def run_fio_on_dut(
        self,
        job,
        opts=None,
        remote: bool = False,
        timeout: int = 86400,
        precondition: bool = False,
    ):
        """Runs FIO.

        This method runs the fio job file on the DUT with the options if given.
        The fio execution output will be stored in a file and parsed
        for any errors.

        Parameter
        ----------
        job: FIO Job file name.
        opts: Options for fio tool. Here default value is None
        remote: Set the flag to run fio jobs in remote location. Here default
            value is false.
        timeout: Set the default timeout for the fio job
        precondition: Flag to indicate if the fio job is a precondition job.

        Returns
        -------
        ret: Flag will sets based on error code availability.
        tmp_output_file: FIO result output file.
        """
        _time = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        filename = f"fio_{self.host.hostname}_{_time}.json"
        output_file = os.path.join(self.resultsdir, filename)
        tmp_output_file = os.path.join(self.tmp_logdir, filename)
        FioRunner.prefix_cmd = self.get_prefix_cmd(
            FioRunner.prefix_command_name
        ).replace("WORKING_DIR", self.resultsdir)
        cmd = f"{FioRunner.prefix_cmd} fio {job} --output-format=json --output={output_file}"
        AutovalLog.log_info(f"Running {self.job_name} FIO command: {cmd}")
        if opts:
            cmd += str(opts)
        out = self.run_fio(
            host=self.host,
            fio_command=cmd,
            working_dir=self.resultsdir,
            timeout=timeout,
            precondition=precondition,
        )
        # collect workload slice sys fs data
        self.collect_prefix_cmd_specific_logs(FioRunner.prefix_command_name, 0)
        cmd_out = out.stdout
        exit_code = out.return_code
        if remote:
            self.host.get_file(output_file, tmp_output_file)
        else:
            tmp_output_file = output_file
        if exit_code != 0:
            ret = self.parse_fio_error(exit_code, cmd_out, tmp_output_file)
        else:
            ret = True
        AutovalLog.log_info("FIO output file is copied at: %s" % tmp_output_file)
        if self.rescan_data_drives:
            drives = [d for d in self.drives if str(d) != str(self.boot_drive)]
            DiskUtils.remove_drives(self.host, drives)
            DiskUtils.rescan_drives(self.host, drives)
            self.rescan_data_drives = False
        return ret, tmp_output_file

    def run_interupted_fio(
        self, job: str, power_cycle: str, remote: bool = False
    ) -> Tuple[bool, str]:
        """Runs FIO with a dirty power off during the process.
        This function runs FIO with a dirty power off during the process and forms
        the power command with a random time value for trigger.
        Args:
            job (str): The path to the FIO job file.
            power_cycle (str): The power cycle command.
            remote (bool, optional): Whether to run FIO remotely or locally. Defaults to False.
        Returns:
            ret (bool): A flag indicating whether there were any error codes.
            tmp_output_file (str): The output file containing the FIO results.
        """
        check_parse_fio_error = False
        _msg = ""
        _time = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        if self.power_random_time:
            trigger_timeout = 60 * random.randint(2, 5)
        else:
            # Some tests required to compare result with previous one
            trigger_timeout = RUNTIME
        power_cmd = ""
        power_cmd = f" --status-interval={self.status_interval}"
        power_cmd += " --trigger-timeout=%d %s" % (
            trigger_timeout,
            self.host.oob.get_fio_trigger_cmd(power_cycle, remote=remote),
        )
        if self.power_trigger_prefix:
            power_cmd = power_cmd.replace(
                "--trigger='", f"--trigger='{self.power_trigger_prefix}; "
            )
        output_file = os.path.join(
            self.resultsdir, f"fio_{self.host.hostname}_{_time}.json"
        )
        cmd = f"fio {job} --output-format=json --output={output_file}"
        cmd += power_cmd
        AutovalLog.log_info(
            f"Running {self.job_name} FIO command with power trigger: {cmd}"
        )
        current_reboot = self.host.get_last_reboot()
        ret = True
        try:
            self.run_fio(host=self.host, fio_command=cmd, working_dir=self.resultsdir)
            # self.host.run(cmd=cmd, working_dir=self.resultsdir)
        except Exception as exc:
            for i in [
                "timed out",
                "timeout",
                "CONNECT_UNKNOWN",
                "Internal error",
                "Connection Error",
            ]:
                if i in str(exc) and not check_parse_fio_error:
                    AutovalLog.log_as_cmd(cmd)
                    AutovalLog.log_info(str(exc))
                    _msg = "[autoval]: fio interrupted due to power trigger"
                    check_parse_fio_error = True
            if not check_parse_fio_error:
                raise TestError(
                    str(exc),
                    component=COMPONENT.SYSTEM,
                    error_type=ErrorType.TOOL_ERR,
                )
        self.host.system_health_check(current_reboot, 1200)
        if check_parse_fio_error:
            ret = self.parse_fio_error(1, _msg, output_file)
        return ret, output_file

    def get_precondition_drives(self):
        """Return data drives for FIO precondition job"""
        _drives = self.get_drives("ssd", None, self.drives)
        if not self.boot_drive_precondition:
            _drives = [d for d in _drives if str(d) != str(self.boot_drive)]
        return _drives

    def start_test(self) -> None:
        """Starts FIO job.

        This method starts FIO job on the DUT and stores the logs.

        Raises
        ------
        TestStepError
            1. When fio job fails with error.
            2. When fails to find saved results of FIO run.
        """
        # fio_opts is the command line options for fio
        fio_opts = self.args.get("fio_opts", None)
        _drives = []
        if self.drives is None:
            self.drives = self.get_drives(
                drive_type=self.drive_type,
                drive_interface=self.drive_interface,
                drives=self.drives,
            )
        if self.boot_drive is None:
            self.boot_drive = DiskUtils.get_boot_drive(
                self.host, self.boot_drive_physical_location
            )
        by_model = StorageUtils.group_drive_by_attr(
            "model", self.drives, generic=self.test_generic_drives
        )
        write_iops = {}
        read_iops = {}
        latency_ms = {}
        for cycle in range(int(self.cycle)):
            if self.trim_arg:
                _drives = self.get_precondition_drives()
                self.trim(_drives, opts=fio_opts)
            for io_type, params in self.run_definition.items():
                additional_args = self.gen_args(params["args"])
                precondition_loops = params.get("precondition_loops", 0)
                remote = params.get("remote", False)

                if precondition_loops:
                    self.run_precondition(params, precondition_loops, remote, fio_opts)

                for additional_arg in additional_args:
                    alias = self.generate_job_name(io_type, cycle, additional_arg)
                    fio_return_dict = self._create_fio_job_and_run(
                        alias, additional_arg, params, remote, fio_opts
                    )
                    result = fio_return_dict.get("result", None)
                    output_file = fio_return_dict.get("output_file", None)
                    by_model = fio_return_dict.get("by_model", by_model)

                    self.fio_file = output_file
                    results = self.get_parsed_results(
                        result, output_file, alias, by_model
                    )
                    # filter results for future compare by cycle and model
                    write_iops, write_iops_model = self.filter_results_by_param(
                        results, "write_iops", write_iops, by_model
                    )
                    read_iops, read_iops_model = self.filter_results_by_param(
                        results, "read_iops", read_iops, by_model
                    )
                    latency_ms, latency_ms_model = self.filter_results_by_param(
                        results, "latency_ms_100", latency_ms, by_model
                    )
                    self.compare_iops(
                        write_iops_model,
                        read_iops_model,
                        latency_ms_model,
                        by_model=True,
                    )
        # Compare results by cycle at the end
        self.compare_iops(write_iops, read_iops, latency_ms, by_model=False)
        self.update_result()

    def _create_fio_job_and_run(
        self,
        alias: str,
        additional_arg: Any,
        params: dict[str, Any],
        remote: bool,
        fio_opts: str | None,
        cpu_drive_mapping: Optional[dict[str, list[str]]] = None,
    ) -> dict[str, Any]:
        """
        Create fio job and run on DUT.

        Args:
        alias: Alias name for the job.
        additional_arg: Additional arguments for the job.
        params: Test args dict
        remote: Flag to indicate whether to run the job remotely or locally.
        fio_opts: Options for the fio tool.

        Returns
            Dictionary containing the results and output file of the job.
        """
        fio_return_dict = {}
        filesystem = params.get("filesystem", False)
        files = params.get("files", None)
        skip_fs = params.get("skip_fs", False)
        filesystem_type = params.get("filesystem_type", "xfs")
        filesystem_options = params.get("filesystem_options", "")
        job_file = alias + ".fio"
        job = self.create_fio_job(
            files=files,
            drive_type=self.drive_type,
            drive_interface=self.drive_interface,
            drives=self.drives,
            replace=additional_arg,
            templ_filename=params["template"],
            job_name=job_file,
            filesystem=filesystem,
            filesystem_type=filesystem_type,
            filesystem_options=filesystem_options,
            skip_fs=skip_fs,
            cpu_drive_mapping=cpu_drive_mapping,
        )
        # Store parameters for RunMeasurements logging
        self._current_test_params.update(
            {
                "template": params.get("template", "unknown"),
            }
        )

        AutovalLog.log_info("Starting fio on DUT")
        # The if condition is for running fio with power trigger
        # command and else condition is for the normal fio job.
        if self.power_trigger:
            result, output_file = self.run_interupted_fio(
                job, self.power_cycle, remote=remote
            )
            by_model = StorageUtils.group_drive_by_attr("model", self.drives)
            fio_return_dict.update(
                {"result": result, "output_file": output_file, "by_model": by_model}
            )
        else:
            result, output_file = self.run_fio_on_dut(
                job, remote=remote, opts=fio_opts, timeout=self.fio_timeout
            )
            fio_return_dict.update({"result": result, "output_file": output_file})

        return fio_return_dict

    def get_parsed_results(
        self,
        result: bool,
        output_file: str,
        alias: str,
        by_model: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Get parsed results from fio output file.

        Args:
            result: Flag indicating fio ran successfully
            output_file: Path to fio output file
            alias: Name of fio job
            by_model: Dictionary of drives grouped by model

        Returns:
            Dictionary of parsed fio results
        """
        AutovalUtils.validate_condition(
            result,
            f"Ran fio on {output_file}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )
        self.fio_file = output_file
        results = self.parse_results()
        if self.enable_performance_metrics_validation:
            self.validate_performance_metrics(
                results=results, _type="", by_model=by_model
            )
        result_dict = {"fio_" + alias: results}
        FioRunner.raw_result.update(result_dict)
        AutovalUtils.result_handler.add_test_results(result_dict)
        AutovalUtils.validate_condition(
            results,
            "Saved results for fio run",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )
        return results

    def run_precondition(
        self,
        params: dict[str, Any],
        precondition_loops: int,
        remote: bool,
        fio_opts: str | None,
    ) -> None:
        """
        Setup drives for preconditioning and run precondition job

        Args:
            params: parameters for preconditioning
            precondition_loops: number of loops for preconditioning
            remote: whether to run preconditioning remotely or locally
            fio_opts: options for fio tool
        """
        _drives = self.get_precondition_drives()
        AutovalUtils.validate_non_empty_list(
            _drives,
            "Drives for precondition",
            log_on_pass=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.SYSTEM_ERR,
        )
        # Secure_erase all drives except boot drive
        StorageUtils.format_all_drives(
            [d for d in _drives if str(d) != str(self.boot_drive)]
        )
        # If file specific Precondition file is provided, use that
        # else, Use the default precondition
        precondition_template = params.get("precondition_template", "precondition.fio")
        AutovalLog.log_info(f"Starting precondition on drives: {_drives}")
        # Preconditioning on ssd drives
        self.precondition_drives(
            _drives,
            precondition_loops,
            precondition_template,
            remote,
            fio_opts,
        )

    def update_result(self):
        if FioRunner.prefix_cmd:
            FioRunner.metric_result.update({"prefix_cmd": FioRunner.prefix_cmd})
        AutovalUtils.result_handler.add_test_results(
            AutovalUtils.result_handler.save_result_threshold_data(
                raw_result=FioRunner.raw_result,
                metric_result=FioRunner.metric_result,
                metric_threshold=FioRunner.threshold_obj_dict,
            )
        )

    def parse_fio_error(self, exit_code, cmd_out, fio_output_file) -> bool:
        """Parses fio output file for error.

        This method validates for any errors in the output file for
        executed job.

        Parameter
        ---------
        exit_code       : Integer
           Fio command exit code.
        cmd_out         : String
           Fio Command output.
        fio_output_file : String
           Fio output results file location.

        Raises
        ------
        TestError
           When fails to find and/or parse the FIO output file.
        """
        fio_out = ""
        fio_output = os.path.join(self.tmp_logdir, os.path.basename(fio_output_file))
        self.host.get_file(fio_output_file, fio_output)
        if FileActions.exists(fio_output):
            fio_out = FileActions.read_data(fio_output)
            if not fio_out:
                raise TestError(
                    "Fio output is empty, \ncmd_out: %s, \nlog file: %s"
                    % (cmd_out, os.path.basename(fio_output_file)),
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.TOOL_ERR,
                )
            # Ignoring if "timeout on cmd SEND_ETA" while FIO
            # Parse Error from fio Output to ignore such error
            # if ignore_remote_fio_error set to true in control file
            # Until we find issue why SEND_ETA happens in FIO client/server;
            # we were ignoring it raising error during test
            if self.ignore_remote_fio_error:
                output = re.search(r"timeout on cmd SEND_ETA", fio_out)
                if output:
                    AutovalLog.log_info(
                        "SEND_ETA timed out with exit code: %s, \n cmd_out:- %s"
                        % (exit_code, cmd_out)
                    )
                    return True
            # Parse error code in fio command output
            error_list = re.findall(r'"error" : (\d*)', fio_out)
            if error_list:
                if int(error_list[-1]) == 0:
                    return True
                raise TestError(
                    "FIO Failed, \ncmd_out: %s, \nlog file: %s"
                    % (cmd_out, os.path.basename(fio_output_file)),
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.TOOL_ERR,
                )
            raise TestError(
                "Variable 'error' not found in FIO output, \ncmd_out: %s, \nlog file: %s"
                % (cmd_out, os.path.basename(fio_output_file)),
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.SYSTEM_ERR,
            )
        raise TestError(
            "FIO Output File Not Found",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

    def parse_results(self) -> Any:
        """Parses FIO JSON result file for FIO data.

        This method parses FIO JSON result file for FIO data.

        Parameters
        ----------
        Print result : Boolean
          Flag sets to print the result in Debug log. Here default value
          is True.

        Returns
        -------
        fio          : Dictionary {String,String}
             Parsed FIO output file data.
        """
        clat_percentiles = self.args.get("clat_percentiles", ["99.000000", "99.990000"])
        latency_ms = self.args.get("latency_ms", ["100"])
        results_data = self.get_result_data_from_dump()

        AutovalLog.log_info("Parsing results: %s" % self.fio_file)
        fio = {}
        fio["fio_version"] = results_data["fio version"]
        # Saving the Input
        fio.update(
            AutovalUtils.add_dict_key_prefix(results_data["global options"], "opt_")
        )
        fio["result"] = []
        jobs = results_data["jobs"]
        for job in jobs:
            _job_data = {}
            _job_data["error"] = job["error"]
            _job_data.update(
                AutovalUtils.add_dict_key_prefix(job["job options"], "opt_")
            )
            _job_data = self.parse_read_write_trim_results(
                job, _job_data, clat_percentiles
            )
            # Adding latency_ms to fio_results
            if job["latency_ms"]:
                for lat in latency_ms:
                    _job_data[f"latency_ms_{lat}"] = job["latency_ms"][lat]
            fio["result"].append(_job_data)

        return fio

    def parse_read_write_trim_results(
        self,
        job: dict[str, Any],
        _job_data: dict[str, Any],
        clat_percentiles: list[str],
    ) -> dict[str, Any]:
        """
        This method is used to parse the read, write and trim results.

        Args:
            job: A dictionary containing the unparsed job data.
            _job_data: The result dictionary with parsed job data.
            clat_percentiles: A list of percentile values.

        Returns:
            A dictionary containing the parsed job data.
        """
        for r_w in ["read", "write", "trim"]:
            if job[r_w] is None or ("runtime" in job[r_w] and job[r_w]["runtime"] == 0):
                continue
            jobname = job["jobname"]
            perf = {}
            for field in ["bw", "bw_agg", "bw_max", "bw_min", "bw_mean"]:
                perf[f"{field} (Kb/s)"] = job[r_w][field]
                _job_data[f"{r_w}_{field}"] = job[r_w][field]
            for field in ["iops", "total_ios"]:
                perf[f"{field}"] = int(job[r_w][field])
                _job_data[f"{r_w}_{field}"] = int(job[r_w][field])
            for lat in ["mean", "min", "max"]:
                if "lat_ns" in job[r_w]:
                    _job_data[f"{r_w}_{lat}_lat"] = job[r_w]["lat_ns"][lat]
                    perf[f"lat_{lat} (nsec)"] = job[r_w]["lat_ns"][lat]
            for clat_perc in clat_percentiles:
                if "percentile" in job[r_w]["clat_ns"]:
                    if clat_perc in job[r_w]["clat_ns"]["percentile"].keys():
                        if "clat_ns" in job[r_w]:
                            _job_data[f"{r_w}_{clat_perc}"] = job[r_w]["clat_ns"][
                                "percentile"
                            ][clat_perc]
                            perf[f"{clat_perc}%"] = job[r_w]["clat_ns"]["percentile"][
                                clat_perc
                            ]
            AutovalLog.log_debug(f"\n{jobname} -- {r_w}")
            AutovalLog.log_debug(
                ", ".join(f"{key}: {value}" for key, value in perf.items())
            )
        return _job_data

    def get_result_data_from_dump(self) -> dict[str, Any]:
        """
        This method is used to get the result data from dump.

        Returns:
            Result data in the form of dictionary.
        """
        fio_output = os.path.join(self.tmp_logdir, os.path.basename(self.fio_file))
        self.host.get_file(self.fio_file, fio_output)
        out = FileActions.read_data(fio_output)
        if self.power_trigger and "signal" in out:
            # Scrub any pre/post messages when we expect reboot
            json_start = out.find("{")
            json_end = out.rfind("}") + 1
            output = out[json_start:json_end]
        else:
            output = out
        # Split output dumps
        output_list = output.split("}\n{\n")
        if len(output_list) > 1:
            # Get previous dump to make sure all completed
            out_previous = output_list[-2]
            out_previous = "{\n" + out_previous
            out_previous += "}\n"
            try:
                results_data = json.loads(out_previous)
            except json.JSONDecodeError:
                raise TestError(
                    f"{self.fio_file} is empty or not loaded properly:\n{out}",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.TOOL_ERR,
                )
            # Parse dump manually
            for i in ["read", "write", "trim"]:
                if i in results_data["jobs"][0].keys():
                    for key, value in results_data["jobs"][0][i].items():
                        results_data["jobs"][0][i + "_" + key] = value
        else:
            try:
                results_data = json.loads(output)
            except json.JSONDecodeError:
                raise TestError(
                    f"{self.fio_file} is empty or not loaded properly:\n{out}",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.TOOL_ERR,
                )
        return results_data

    def trim(self, drives, opts=None, mnt: str = "/mnt/autoval") -> None:
        """Performs Random Trim Fio Jobs.

        This methods performs random trim fio jobs on DUT by the following
        steps:
            1. Mounting device at mnt_point/unmounts mount point if it already
            exists/Creates mnt_point directory if it doesn't exist.
            2. Retrieves df -T output for device and parses it into dictionary.
            3. Removes unused blocks on mounted Filesystem and raises exception
            for any failures.
            4. unmounts given mount point and raises exception for any
            failures.
            5. Creates and run fio job file based on given trim_args.
            6. Stores the logs and raises exception for any errors.
        Parameters
        ----------
        drives          : :obj: 'List' of 'String'
            List of SSD drives present on the host.

        opts              : String
            Options for fio tool. Here default value is None

        Raises
        ------
        TestStepError
            1. When fails to remove unused blocks on mounted file system.
            2. When fails to unmount the given mount point.
        """
        mnt_options = "noatime,nodiratime,discard,nobarrier"
        fstype = "ext4"
        for dev in drives:
            if mnt == "/mnt/autoval":
                mnt = f"{mnt}_{dev}"
            host = self.host
            FilesystemUtils.mount(host, dev, mnt, mnt_options, fstype)
            df_info = FilesystemUtils.get_df_info(host, dev)
            AutovalUtils.validate_condition(
                df_info["type"] == fstype,
                f"Mounted {dev} at {mnt}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.SYSTEM_ERR,
            )
            AutovalUtils.validate_no_exception(
                FilesystemUtils.fstrim,
                [host, mnt],
                "Trim on %s" % mnt,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.SYSTEM_ERR,
            )
            AutovalUtils.validate_no_exception(
                FilesystemUtils.unmount,
                [host, mnt],
                "Unmount %s" % dev,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.SYSTEM_ERR,
            )
            job = self.create_fio_job(
                drive_type="ssd",
                drives=self.drives,
                replace=self.trim_arg,
                templ_filename="trim_flash.fio",
            )
            AutovalLog.log_info("Starting random trim fio job on DUT")
            result, output_file = self.run_fio_on_dut(
                job, opts=opts, timeout=self.fio_timeout
            )
            self.fio_file = output_file
            AutovalUtils.validate_condition(
                result,
                "Ran random trim fio job on %s" % output_file,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )
            results = self.parse_results()
            by_model = StorageUtils.group_drive_by_attr("model", drives)
            if self.enable_performance_metrics_validation:
                self.validate_performance_metrics(
                    results=results, _type="", by_model=by_model
                )
            result_dict = {"trim_" + str(int(time.time())): results}
            FioRunner.raw_result.update(result_dict)
            AutovalUtils.result_handler.add_test_results(result_dict)
            AutovalUtils.validate_condition(
                results,
                "Saved results for random trim fio run",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )

    def precondition_drives(
        self,
        drives,
        precondition_loops,
        precondition_template,
        remote,
        fio_opts=None,
        mnt: str = "/mnt/autoval",
        precondition_params: Optional[dict[str, str]] = None,
    ) -> None:
        """Performs Precondition Fio Jobs.

        This method creates and run fio job file based on the preconditions.
        Stores the logs and raises exception for any errors.

        Parameters
        ----------
        drives          : :obj: 'List' of 'Drive' class obj
            List of SSD drives present on the host.
        precondition_loops : Integer
            No. of Precondition loops.
        precondition_template : String
            Precondition fio template file.
        remote : Boolean
            Set the flag to run fio jobs in remote location.
        fio_opts: String
            fio command line options
        precondition_params : dict
            Can be modified with string replace methods.

        Raises
        ------
        TestStepError
            When fails to run FIO Job.
        """
        # Save value
        saved = self.skip_iops
        self.skip_iops = True

        self.unmount_drives(drives, mnt)
        # If file specific (random/seq) Precondition file exists, use that
        # else, Use the default precondition
        write_iops = {}
        read_iops = {}
        latency_ms = {}
        self.precondition_params = precondition_params or {}
        by_model = StorageUtils.group_drive_by_attr("model", drives)
        for _cycle in range(1, precondition_loops + 1):
            results = self.run_precondition_fio_job(
                _cycle, drives, precondition_template, remote, fio_opts, by_model
            )
            # filter results for future compare by cycle and model
            write_iops, write_iops_model = self.filter_results_by_param(
                results, "write_iops", write_iops, by_model
            )
            read_iops, read_iops_model = self.filter_results_by_param(
                results, "read_iops", read_iops, by_model
            )
            latency_ms, latency_ms_model = self.filter_results_by_param(
                results, "latency_ms", latency_ms, by_model
            )
            self.compare_iops(
                write_iops_model,
                read_iops_model,
                latency_ms_model,
                by_model=True,
                fio_type="precondition",
            )

        self.compare_iops(
            write_iops, read_iops, latency_ms, by_model=False, fio_type="precondition"
        )
        # Revert back
        self.skip_iops = saved

    def unmount_drives(self, drives: list[Drive | str], mnt: str) -> None:
        """
        Unmounts the drives if they are already mounted.

        Args:
            drives: List of SSD drives present on the host.
            mnt: Mount point to unmount the drives.
        """
        AutovalLog.log_info("Unmount drives for precondition")
        for dev in drives:
            if mnt == "/mnt/autoval":
                mnt = f"{mnt}_{dev}"
            if FilesystemUtils.is_mounted(self.host, mnt):
                FilesystemUtils.unmount(self.host, mnt)

    def run_precondition_fio_job(
        self,
        _cycle: int,
        drives: list[Drive | str],
        precondition_template: str,
        remote: bool,
        fio_opts: str | None,
        by_model: dict[str, list[str]],
    ) -> dict[str, Any]:
        """
        Runs the precondition fio job on the DUT.

        Args:
            _cycle: Cycle number of the precondition fio job.
            drives: List of SSD drives present on the host.
            precondition_template: Precondition fio template file.
            remote: Boolean flag to run the fio job in remote location.
            fio_opts: Fio command line options.
            by_model: Boolean flag to group the drives by model.

        Returns:
            Dictionary containing the results of the precondition fio job.
        """
        # If precondition_template is a string with parameters to replace, use it directly or otherwise, treat it as a filename
        replace_params = {}
        if hasattr(self, "precondition_params") and isinstance(
            self.precondition_params, dict
        ):
            replace_params = self.precondition_params

        job = self.create_fio_job(
            drives=drives,
            replace=replace_params,
            templ_filename=precondition_template,
            precondition=True,
        )
        AutovalLog.log_info(f"Starting preconditioning cycle {_cycle} on DUT")
        result, output_file = self.run_fio_on_dut(
            job=job,
            remote=remote,
            timeout=self.fio_timeout,
            opts=fio_opts,
            precondition=True,
        )
        self.fio_file = output_file
        AutovalUtils.validate_condition(
            result,
            f"Precondition fio job {output_file}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )
        results = self.parse_results()
        if self.enable_performance_metrics_validation:
            self.validate_performance_metrics(
                results=results, _type="precondition", by_model=by_model
            )
        result_dict = {"precondition_" + str(_cycle) + str(int(time.time())): results}
        FioRunner.raw_result.update(result_dict)
        AutovalUtils.result_handler.add_test_results(result_dict)
        AutovalUtils.validate_condition(
            results,
            "Saved results for precondition fio job",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )
        return results

    def compare_iops(
        self,
        write_iops,
        read_iops,
        latency_ms,
        by_model: bool = False,
        fio_type: str = "",
    ) -> None:
        """
        Compare iops by model or by cycle.

        Args:
            write_iops: Dictionary containing write iops for each drive.
            read_iops: Dictionary containing read iops for each drive.
            latency_ms: Dictionary containing latency_ms for each drive.
            by_model: Boolean flag to group the drives by model.
            fio_type: Type of workload ran

        """
        _by_model_or_cycle = "model" if by_model else "cycle"
        if write_iops or read_iops:
            AutovalLog.log_info(f"Compare {fio_type} iops by {_by_model_or_cycle}:")
        if write_iops and (fio_type or not self.skip_iops):
            self.check_iops(
                iops=write_iops,
                _type=fio_type,
                _by_model_or_cycle=_by_model_or_cycle,
                _read_or_write="write",
            )
        if read_iops and (fio_type or not self.skip_iops):
            self.check_iops(
                iops=read_iops,
                _type=fio_type,
                _by_model_or_cycle=_by_model_or_cycle,
                _read_or_write="read",
            )
        if latency_ms:
            AutovalLog.log_info(
                f"Checking {fio_type} latency_ms threshold by {_by_model_or_cycle}:"
            )
            self.check_latency_ms(
                latency_ms, _type=fio_type, _by_model_or_cycle=_by_model_or_cycle
            )

    def generate_job_name(self, io_type, cycle, additional_arg) -> str:
        """Constructs Job Name.

        This method constructs job name by appending io type, cycle and
        additional arguments.

        Parameters
        ----------
        io_type :  String
            Type of IO to run fio jobs.
        cycle : Integer
            Cycle count.
        additional_arg : List of Dictionary
            Combinations of fio parameters according to passed 'args'.

        Returns
        -------
        name: String
            Return Fio Job name.
        """
        name = "%s_%s_cycle_%d" % (self.host.hostname, io_type, cycle)
        for key, value in additional_arg.items():
            name = name + "_" + key + str(value)
        return name

    def gen_args(self, args):
        """Generates Arguments.

        This method generates arguments based on the arguments
        mentioned by the user.

        Parameters
        ----------
        args: Dictionary(String,String)
            User provided arguments.

        Returns
        -------
         additional_arg : List of Dictionary
            Combinations of fio parameters according to passed 'args'.
        e.g:
        if args: {'RUNTIME': ['1200s'], 'RW': ['write', 'read']}
        method will return:
        {'RUNTIME': '1200s', 'RW': 'write'}, {'RUNTIME': '1200s', 'RW': 'read'}
        @param args: dictionary containing fio parameters
        """
        for k, val in args.items():
            if isinstance(val, (int, str)):
                args[k] = [val]
        values = sorted(args)
        if len(values) > 1:
            additional_args = [
                dict(zip(values, option))
                for option in itertools.product(*(args[varName] for varName in values))
            ]
        elif len(values) == 1:
            additional_args = []
            for each_val in args[values[0]]:
                additional_args.append({values[0]: each_val})
        return additional_args

    @staticmethod
    def check_run_definition_format(run_definitions: dict) -> None:
        """Check dictionary run_definition for errors"""
        if not run_definitions:
            raise TestError(
                "run_definition should not be empty",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.INPUT_ERR,
            )
        keys_to_check = ["template", "args"]
        for job, run_def in run_definitions.items():
            keys = list(run_def.keys())
            if not all(key in keys for key in keys_to_check):
                raise TestError(
                    f"Run definition {job} must contain keys: {keys_to_check}",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.INPUT_ERR,
                )

    def check_iops(
        self,
        iops: dict[str, Any],
        _type: Any,
        _by_model_or_cycle: str,
        _read_or_write: str,
    ) -> None:
        """
        check difference in iops. DIFF 20% is threshold rate
        """
        for key, value in iops.items():
            if isinstance(value, list):
                if len(value) > 1:
                    diff = max(value) - min(value)
                    if self.skip_iops:
                        AutovalLog.log_info(
                            f"{key}: {_type} compare by {_by_model_or_cycle} - {_read_or_write} iops is {sorted(value)}"
                        )
                    else:
                        iops_diff_percent = int(FioRunner.IOPS_DIFF * 100)
                        AutovalUtils.validate_less_equal(
                            float(diff),
                            max(value) * FioRunner.IOPS_DIFF,
                            f"{key}: {_type} compare by {_by_model_or_cycle} - {_read_or_write} iops are {sorted(value)}"
                            f": MAX-MIN delta is less than or equal to {iops_diff_percent}% of MAX",
                            raise_on_fail=False,
                            component=COMPONENT.STORAGE_DRIVE,
                            error_type=ErrorType.MAX_MIN_IOPS_DELTA_TOO_HIGH_ERR,
                        )
                        _data = {
                            str(_by_model_or_cycle): {
                                str(_read_or_write): {str(key): diff}
                            }
                        }
                        if _type:
                            FioRunner.metric_result.update(
                                {"iops_diff": {str(_type): _data}}
                            )
                        else:
                            FioRunner.metric_result.update({"iops_diff": _data})
                elif len(value) == 1:
                    if self.skip_iops or value[0] == 0:
                        AutovalLog.log_info(
                            f"{_type} compare by {_by_model_or_cycle} - {key} has {_read_or_write} iops: {value[0]}"
                        )
                    else:
                        AutovalUtils.validate_greater(
                            value[0],
                            FioRunner.IOPS,
                            f"{_type} compare by {_by_model_or_cycle} - {key} has {_read_or_write} iops: {value[0]}",
                            raise_on_fail=False,
                            component=COMPONENT.STORAGE_DRIVE,
                            error_type=ErrorType.MAX_MIN_IOPS_DELTA_TOO_HIGH_ERR,
                        )
                        _data = {
                            str(_by_model_or_cycle): {
                                str(_read_or_write): {str(key): value[0]}
                            }
                        }
                        if _type:
                            FioRunner.metric_result.update(
                                {"iops": {str(_type): _data}}
                            )
                        else:
                            FioRunner.metric_result.update({"iops": _data})
                else:
                    # In case of writing, read will be empty
                    # In case of reading, write will be empty
                    AutovalLog.log_info(
                        f"WARNING: {key} has {_read_or_write} iops: {value}"
                    )
            else:
                AutovalLog.log_info(f"{key}: {value} is not a list")

    def check_latency_ms(self, latency_ms: dict, _type, _by_model_or_cycle) -> None:
        """
        Check latency_ms

        This method is used to check the latency_ms value has met
        expected threshold.

        Parameters
        ----------
        latency_ms: dict
             Contains the values of the latency_ms for all drives
             or models.
        """
        for key, values in latency_ms.items():
            if len(values) != 0:
                avg = sum(values) / len(values)
                AutovalUtils.validate_less(
                    avg,
                    FioRunner.LATENCY_MS_100_THRESHOLD,
                    f"{_type} compare by {_by_model_or_cycle}: Validate if the {key} P100 value of "
                    f"latency_ms is less than 100",
                    raise_on_fail=False,
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )
                _data = {str(_by_model_or_cycle): {str(key): avg}}
                if _type:
                    FioRunner.metric_result.update({"latency_100": {str(_type): _data}})
                else:
                    FioRunner.metric_result.update({"latency_100": _data})
            else:
                raise TestError(
                    "No values found to validate latency_ms "
                    "with the expected threshold",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )

    def filter_results_by_param(
        self, results: dict, _filter: str, filter_results: dict, by_model: dict
    ) -> Tuple[dict, dict]:
        """
        Filter results by params.

        This method will filter the results from the fio parse_results
        based on the provided input.

        Parameters
        ----------
        results: dict
             Fio parse Results.
        _filter: String
             Parameter whose values are to filtered.
        results: dict
             Storage reference where the values of the parameter are to be stored.
        by_model: dict
             Contains map of model and drives respective to the model.

        Returns
        -------
        filter_results: dict
             Contains the fio parameter values from fio parse results
             for all drives.
        filter_results_by_model: dict
             Contains the fio parameter values from fio parse results
             grouped by model
        """
        filter_results_by_model = {}
        key_value_list = [
            (self.key_gen(i["opt_filename"]), i[_filter])
            for i in results["result"]
            if _filter in i and i[_filter] is not None
        ]
        if key_value_list:
            for key, value in key_value_list:
                if key not in filter_results:
                    filter_results[key] = []
                filter_results[key].append(value)
            for model, drives in by_model.items():
                values = []
                for key, value in key_value_list:
                    for drive in drives:
                        if f"{drive}" in key and value is not None:
                            values.append(value)
                filter_results_by_model[model] = values
        return filter_results, filter_results_by_model

    def key_gen(self, file_name: str) -> str:
        """
        Generate dict key based on the file path

        Args:
            file_name: File name for which the key is needed

        Return:
            The generated Key

        """
        if os.path.basename(FioRunner.MOUNTED_DRIVE_FIO_PATH) in file_name:
            return os.path.join("/dev", self.boot_drive)
        return file_name

    def run_fio(
        self,
        host: Host,
        fio_command: str,
        working_dir: Optional[str] = None,
        timeout: int = 600,
        precondition: bool = False,
    ) -> CmdResult:
        kwargs = {
            "cmd": fio_command,
            "working_directory": working_dir,
            "timeout": timeout,
            "ignore_status": True,
        }
        cmd_result = self.host.run_get_result(
            **{k: v for k, v in kwargs.items() if v is not None}
        )
        for _retry in range(2):
            if cmd_result.return_code == 0:
                break
            output = f"{cmd_result.stdout} {cmd_result.stderr}"
            if "fio: engine libaio not loadable" in output:
                AutovalLog.log_info(f"libaio engine not loadable : {output}")
                self.update_fio_version(host)
                cmd_result = self.host.run_get_result(
                    **{k: v for k, v in kwargs.items() if v is not None}
                )
            else:
                raise ToolError(f"Error in starting fio job. Reason: {output}")
        return cmd_result

    def validate_performance_metrics(
        self, results: dict, _type: str, by_model: dict
    ) -> None:
        """
        Get the threshold values from fio_runner.cconf and validate metrics in METRICS_TO_VALIDATE

        Parameters
        ----------
        results:
            Fio parse Results
        by_model:
            Contains map of model and drives respective to the model.

        """
        for metric in FioRunner.METRICS_TO_VALIDATE:
            metric_results = {}
            metric_results, metric_results_model = self.filter_results_by_param(
                results, metric, metric_results, by_model
            )
            if metric_results:
                self._validate_metric(
                    metric=metric,
                    metric_results=metric_results,
                    _type=_type,
                    _by_model_or_cycle="cycle",
                )

            if metric_results_model:
                self._validate_metric(
                    metric,
                    metric_results=metric_results_model,
                    _type=_type,
                    _by_model_or_cycle="model",
                )

    def _validate_metric(
        self, metric: str, metric_results: dict, _type: str, _by_model_or_cycle: str
    ) -> None:
        """
        Validates the fio results for metrics for given metric with the threshold values mentioned in fio_runner.cconf

        Parameters
        ----------
        metric:
            Name of the metric to validate.
        metric_results:
            Fio parse results filtered for the metric.
        _by_model_or_cycle:
            Validating by cycle or model
        """

        compare_method = COMPARISON_MAP.get(
            FioRunner.threshold_obj_dict[metric].comparison, None
        )
        threshold_value = FioRunner.threshold_obj_dict[metric].value
        if not compare_method or threshold_value is None:
            raise TestError(
                f"threshold of {metric} is not define properly in the configerator",
                component=COMPONENT.UNKNOWN,
                error_type=ErrorType.CONFIGERATOR_ERR,
            )
        for _key, values in metric_results.items():
            if len(values) != 0:
                avg = sum(values) / len(values)
                if metric in FioRunner.METRICS_IN_NS:
                    avg = self._convert_ns_to_s(avg)
                compare_method(
                    avg,
                    threshold_value,
                    f"{_key}: {_type} compare by {_by_model_or_cycle} - {metric} is {values}",
                    raise_on_fail=False,
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )
                _data = {str(_by_model_or_cycle): {str(_key): avg}}
                if _type:
                    FioRunner.metric_result.update({metric: {str(_type): _data}})
                else:
                    FioRunner.metric_result.update({metric: _data})
            else:
                raise TestError(
                    f"No values found to validate {metric} with the expected threshold",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )

    def _convert_ns_to_s(self, value_ns: int | float) -> float:
        """
        Converts given value in nanoseconds to seconds.

        Parameters
        ----------
        value_ns:
             Contains the value in nanoseconds

        Returns
        -------
        value_s:
             Contains the converted value in seconds

        """

        value_ns = float(value_ns)
        value_s = value_ns / 1_000_000_000  # Convert nanoseconds to seconds
        return value_s

    def get_prefix_cmd(self, prefix_command_name):
        if not prefix_command_name:
            return ""
        if prefix_command_name in self.prefix_cmd_dict.keys():
            return self.prefix_cmd_dict[prefix_command_name]["prefix_cmd"]
        raise TestError(f"Invalid prefix cmd {prefix_command_name} specified.")

    def collect_prefix_cmd_specific_logs(self, prefix_command_name, iteration):
        if not prefix_command_name:
            return
        if prefix_command_name in self.prefix_cmd_dict.keys():
            dut_tmp_dir = SiteUtils.get_dut_logdir(self.host.hostname)
            for log_dir in self.prefix_cmd_dict[prefix_command_name]["logs_dir"]:
                if not FileActions.exists(log_dir, host=self.host):
                    continue
                cmd = (
                    f"tar -cvzf {prefix_command_name}_iter_{iteration}.tar.gz {log_dir}"
                )
                self.host.run(cmd=cmd, working_directory=dut_tmp_dir)
                return
        raise TestError(f"Invalid prefix cmd {prefix_command_name} specified.")

    def test_cleanup(self) -> None:
        if self.drives is not None:
            for drive in self.drives:
                mnt = self.fio_mnt_path % drive
                if FilesystemUtils.is_mounted(self.host, mnt):
                    FilesystemUtils.unmount(self.host, mnt)
        self.host.run(
            cmd=f"rm -f {FioRunner.MOUNTED_DRIVE_FIO_PATH}", ignore_status=True
        )
        if self.boot_drive_partitioned:
            self.boot_drive_fio_cleanup()

    def boot_drive_fio_setup(self) -> None:
        """
        This method creates a new partition on the boot drive to run fio
        """
        root_partition_number = self.get_root_partition_number()
        original_partition_size = int(
            self.host.run(
                f"sfdisk --list --bytes -o Device,Size /dev/{self.boot_drive} 2>/dev/null | grep /dev/{self.boot_drive}p{root_partition_number} | awk '{{print $2}}'",
            )
        )
        new_partition_size = int(original_partition_size - (60 * 1024 * 1024 * 1024))
        sector_size = int(
            self.host.run(f"cat /sys/block/{self.boot_drive}/queue/logical_block_size")
        )

        try:
            self.host.run(f"btrfs filesystem resize {new_partition_size} /")

        except Exception as e:
            AutovalLog.log_info(f"Unable to resize filesystem: {e}")
            AutovalLog.log_info(
                "Skipping boot drive partition creation and running fio on filesystem"
            )
            return

        self.host.run(f"sfdisk --delete /dev/{self.boot_drive} {root_partition_number}")

        # Create new partitions
        self.host.run(
            f'echo -e "size={int(new_partition_size / sector_size)}" | sfdisk /dev/{self.boot_drive} --append --force'
        )
        self.host.run(
            f'echo -e "start=" | sfdisk /dev/{self.boot_drive} --append --force'
        )
        self.host.run(f"partprobe /dev/{self.boot_drive}")

        AutovalUtils.validate_no_exception(
            self.get_boot_drive_fio_partition,
            [],
            "Boot drive partition for fio created",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

        self.boot_drive_partitioned = True

    def get_root_partition_number(self) -> int:
        """
        This method returns the partition number of the root partition on boot drive
        """
        root_partition = self.host.run(
            "df / | grep -E '/dev/' | awk '{print $1}'"
        ).strip()

        match = re.match(r"(/dev/.*?)p?(\d+)$", root_partition)
        if not match:
            raise TestError(
                "Could not determine root partition",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
        root_partition_number = int(match.group(2))
        return root_partition_number

    def get_boot_drive_fio_partition(self) -> str:
        """
        This method returns the partition name of the boot drive for fio

        Returns
        -------
            Partition name of the boot drive for fio
        """
        fio_partition = self.host.run(
            f"sfdisk --list -o Device,Size /dev/{self.boot_drive} 2>/dev/null | grep '60G' | awk '{{print $1}}'"
        )
        return fio_partition

    def boot_drive_fio_cleanup(self) -> None:
        """
        This method deletes the new partitions on the boot drive and revert back to original partition
        """
        root_partition_number = self.get_root_partition_number()
        fio_partition_number = int(self.get_boot_drive_fio_partition().split("p")[1])

        # Delete new partitions
        self.host.run(f"sfdisk /dev/{self.boot_drive} {fio_partition_number} --delete")
        self.host.run(f"sfdisk /dev/{self.boot_drive} {root_partition_number} --delete")

        # Create original partitions with default values
        self.host.run(
            f'echo -e "start=" | sfdisk /dev/{self.boot_drive} --append --force'
        )
        self.host.run(f"partprobe /dev/{self.boot_drive}")
        self.host.run("btrfs filesystem resize max /")
        self.boot_drive_partitioned = False
        AutovalLog.log_info("Boot drive partition for fio deleted")

    def get_global_values_dict(self, dev_str: str) -> dict[str, Any]:
        """
        This method returns a dictionary of global values for a given device string.

        Args:
            dev_str: The device string for which to retrieve global values.

        Returns:
            dict[str, Any]: A dictionary containing the global values for the given device string.
        """
        global_values = {}
        in_global = False

        for line in dev_str.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            if line.startswith("[") and line.endswith("]"):
                section_name = line[1:-1].strip()
                in_global = section_name == "global"
                continue

            if in_global and "=" in line:
                key, value = line.split("=", 1)
                global_values[key.strip()] = value.strip()

            if not in_global and "in_global" in locals():
                break

        return global_values

    def format_t10_dix_drives(self) -> None:
        """
        Format the Test drives with T10 dix format 4k+64 lbaf
        """
        t10_dix_format = "4096+64"
        for drive in self.drives:
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
                f"{drive.block_name}: Format with lba {t10_dix_format}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )

    def get_qlc_md_size(self, fio_args_dict: dict[str, Any]) -> str:
        """
        Calculate the md_size per io based on the write blocksize.

        - Extracts write block size (second value if comma-separated)
        - Supports 'K' and 'M' units
        - Ensures minimum md_size of 1k

        Args:
            fio_args_dict: Fio args dict containing args for the fio job

        Returns:
            md_size in kb as string (e.g., '2k')
        """
        blocksize_str = str(fio_args_dict.get("BLOCKSIZE", "")).strip()
        if not blocksize_str:
            return "1k"

        parts = [p.strip() for p in blocksize_str.split(",") if p.strip()]
        if not parts:
            return "1k"
        if len(parts) >= 2:
            write_block_str = parts[1]
        else:
            write_block_str = parts[0]

        return self._calculate_md_size_for_blocksize(write_block_str)

    def _add_qlc_trim_job(
        self,
        dev_str: str,
        drives: list[Union[str, Drive]],
        idx: int,
        replace: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Add a randtrim job section to run alongside existing qlc workload for each drive.

        Args:
            dev_str: Base string containing the fio job definitions.
            drives: List of drive names or Drive objects.
            idx: Starting index for job numbering.
            replace: Dictionary containing the current FIO args combination,
                including TRIM_BLOCKSIZE from run_definition.args.

        Returns:
            The updated job string with trim job sections added for each drive.
        """
        replace = replace or {}
        trim_blocksize = str(replace.get("TRIM_BLOCKSIZE", "1M"))
        trim_md_size = self._calculate_md_size_for_blocksize(trim_blocksize)

        for device in drives:
            device_name = self._get_device_name_for_test(device)

            trim_section = (
                f"\n[trim_job{idx}]\n"
                "rw=randtrim\n"
                f"filename=/dev/{device_name}\n"
                f"blocksize={trim_blocksize}\n"
                f"md_per_io_size={trim_md_size}\n"
                "new_group=0\n"
            )
            dev_str += trim_section
            idx += 1

        return dev_str

    def _calculate_md_size_for_blocksize(self, blocksize_str: str) -> str:
        """
        Calculate the md_per_io_size based on the given blocksize.

        Args:
            blocksize_str: Block size string (e.g., '1M', '128K', '64M')

        Returns:
            md_per_io_size as string (e.g., '16k', '2k')
        """
        blocksize_str = blocksize_str.upper().strip()
        if not blocksize_str:
            return "1k"

        unit = blocksize_str[-1]
        try:
            value = int(blocksize_str.rstrip("KMB"))
        except ValueError:
            return "1k"

        if unit == "M":
            blocksize_kb = value * 1024
        elif unit == "K":
            blocksize_kb = value
        else:
            blocksize_kb = value

        md_size_kb = max(blocksize_kb // 64, 1)
        return f"{md_size_kb}k"
