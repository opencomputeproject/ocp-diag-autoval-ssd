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
from typing import Any, Dict, Optional, Tuple, Union

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
from autoval_ssd.lib.utils.storage.storage_utils import StorageUtils
from autoval_ssd.lib.utils.system_utils import SystemUtils

LIB_PATH = "lib/utils/jobfile_templates"
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
        self.status_interval = args.get("status_interval", 1)
        self.rescan_data_drives = args.get("rescan_data_drives", False)
        self.enable_performance_metrics_validation = args.get(
            "enable_performance_metrics_validation", False
        )
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

        user_criteria = {
            "project_name": self.host.product_name,
        }
        try:
            FioRunner.threshold_obj_dict = ThresholdConfig().get_threshold(
                filepath=FioRunner.fio_runner_threshold_config,
                user_metric_list=["iops", "iops_diff", "latency_100"]
                + FioRunner.METRICS_TO_VALIDATE,
                user_criteria=user_criteria,
            )
        except FileNotFoundError:
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
        test_drives = StorageUtils().get_test_drives(
            self.host,
            drive_type=drive_type,
            drive_interface=drive_interface,
            drives=drives,
        )
        all_drives = list(test_drives.values())
        _len = len(all_drives)
        AutovalLog.log_info(
            "Available %s %s drives: %s" % (_len, drive_type, all_drives)
        )
        return all_drives

    def create_filesystem_mount(
        self,
        host,
        drives,
        filesystem_type: str = "xfs",
        filesystem_options: str = " -K -i size=2048",
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
                "Mounted %s at %s" % (device, mnt),
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.SYSTEM_ERR,
            )

    def create_fio_job(
        self,
        files=None,
        drive_type=None,
        drive_interface=None,
        drives=None,
        replace=None,
        templ_filename=None,
        job_name=None,
        filesystem=None,
        filesystem_type=None,
        filesystem_options=None,
        skip_fs: bool = False,
        directory=None,
        dest_job_file=None,
    ) -> str:
        """Creates FIO job.

        This method gets the list of test_drives on the DUT based on the
        options passed i.e, drive_type, drive_interface,
        all_block devices = True or False and any special drives passed
        and Creates a new job file based on the 'template' file and the test_
        drives list.

        Parameters
        ----------
        files : String
            FIO job files. Here default value is None.
        drive_type      : String
           Type of drive (HDD/SSD/MD) present on the host. Here default value
            is None.
        drive_interface : String
           Type of drive interface (NVME/SAS/SATA) present on the host. Here
           default value is None.
        drives : :obj: 'List' of 'String'
           List of drives present on the host. Here default value is None.
        job_name = Dictionary {String,String}
            Name of the FIO job. Here default value is None.
        filesystem : String
            Filesystem type. Here default value is None.
        remote : Boolean
            Set the flag to run fio jobs in remote location. Here default
            value is False.
        templ_filename  : String
            Path to file containing job definition, takes default if nothing
            is passed. Here default value is None.
        replace         : :obj: 'List' of 'String'
            List of key / value pairs to replace in template file
            additional imputs for fio can be given as key value pair
            in the name 'additional_fio_options'. Here default value is None.
        filesystem_type : String
            Contains the type of the filesystem to be created.
        filesystem_options : String
            Contains additional options while creating filesystem
        skip_fs = Dictionary {String,String}.Here default value is False.
            The skip_fs flag is being used to skip filesystem creation if already
            present.
            fio_timeout = Integer
            Maximum time allowed for the fio cmd to run before timeout.
            fio
            Use case for skip_fs flag:
                After FIO write and power cycle,if want to just mount the drives
                and not create the filesystem again for FIO read operation
                for md5 verification,this will be helpful.
                In Normal case this will not prevent creating the filesystem as the
                default value is set to False.
        Returns
        -------
        dest_job_file   : String
            Job file contains DUT log directory and templ_filename.

        """
        if replace is None:
            replace = {}
        if not files and not drives:
            drives = self.get_drives(drive_type, drive_interface, drives)
        templ_path = FileActions.get_resource_file_path(
            os.path.join(LIB_PATH, templ_filename), "autoval_ssd"
        )
        content = FileActions.read_data(templ_path)
        _size = ""
        for key, value in replace.items():
            regex = re.compile(f"={key}", re.MULTILINE)
            content = re.sub(regex, f"={value}", content)
            if key == "SIZE":
                _size = value
            if key == "RUNTIME":
                self.fio_timeout = DiskUtils.get_seconds(value) + 600
            # when allow_mounted_write value is passed as a argument value
            if key == "ALLOW_MOUNTED_WRITE":
                content = content + key.lower() + "=" + str(value)
        idx = 0
        dev_str = content + "\n"
        if filesystem and not skip_fs:
            self.create_filesystem_mount(
                self.host, drives, filesystem_type, filesystem_options
            )
        elif skip_fs:
            mnt = "/mnt/fio_test_%s/"
            FilesystemUtils.mount_all(self.host, drives, mnt, force_mount=False)
        for device in drives:
            if filesystem:
                dev_str += "[job%d]\n" % idx
                _file = "/mnt/fio_test_%s/file1" % device
                dev_str += "filename=%s\n" % _file
                dev_str += "fdatasync=1\n"
                # if size specified as %, create file,
                # otherwise fio will not be able to create file and it will fail
                file_size = self._create_file(device, _file, _size)
            elif directory:
                dev_str += "[d%d]\n" % idx
                dev_str += "directory=%s\n" % device
                dev_str += "fdatasync=1\n"
            else:
                dev_str += "[job%d]\n" % idx
                if str(device) == str(self.boot_drive) and DiskUtils.is_drive_mounted(
                    self.host, str(self.boot_drive)
                ):
                    # Safety write to boot drive
                    if files:
                        _file = files["file"]
                    else:
                        _file = FioRunner.MOUNTED_DRIVE_FIO_PATH
                    dev_str += "filename=%s\n" % _file
                    file_size = self._create_file(device, _file, _size)
                    dev_str += "size=%s\n" % file_size
                    dev_str += "fdatasync=1\n"
                else:
                    # use raw device
                    dev_str += "filename=/dev/%s\n" % str(device)
            dev_str += "new_group=1\n"
            idx += 1
        # For tests executed from BG runner
        if self.test_boot_drive and str(self.boot_drive) not in str(drives):
            if self.boot_drive != "" and str(self.boot_drive) != "rootfs":
                dev_str += "[job%d]\n" % idx
                dev_str += "new_group=1\n"
                if DiskUtils.is_drive_mounted(self.host, str(self.boot_drive)):
                    _file = files["file"] if files else FioRunner.MOUNTED_DRIVE_FIO_PATH
                    dev_str += "filename=%s\n" % _file
                    file_size = self._create_file(self.boot_drive, _file, _size)
                    dev_str += "size=%s\n" % file_size
                    dev_str += "fdatasync=1\n"
                else:
                    dev_str += "filename=/dev/%s\n" % str(self.boot_drive)
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
        AutovalLog.log_info("Job file used: %s" % dest_job_file)
        return dest_job_file

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
        self, job, opts=None, remote: bool = False, timeout: int = 86400
    ):
        """Runs FIO.

        This method runs the fio job file on the DUT with the options if given.
        The fio execution output will be stored in a file and parsed
        for any errors.

        Parameter
        ----------
        job               : String
            FIO Job file name.
        opts              : String
            Options for fio tool. Here default value is None
        remote : Boolean
            Set the flag to run fio jobs in remote location. Here default
            value is false.
        timeout          : Integer
             Set the default timeout for the fio job

        Returns
        -------
        ret               : Boolean
             Flag will sets based on error code availability.
        tmp_output_file   : String
             FIO result output file.
        """
        _time = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        filename = f"fio_{self.host.hostname}_{_time}.json"
        output_file = os.path.join(self.resultsdir, filename)
        tmp_output_file = os.path.join(self.tmp_logdir, filename)
        FioRunner.prefix_cmd = self.get_prefix_cmd(
            FioRunner.prefix_command_name
        ).replace("WORKING_DIR", self.resultsdir)
        cmd = f"{FioRunner.prefix_cmd} fio {job} --output-format=json --output={output_file}"
        AutovalLog.log_info("Running %s FIO command: %s" % (self.job_name, cmd))
        if opts:
            cmd += str(opts)
        out = self.run_fio(
            host=self.host,
            fio_command=cmd,
            working_dir=self.resultsdir,
            timeout=timeout,
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
        output_file = os.path.join(
            self.resultsdir, f"fio_{self.host.hostname}_{_time}.json"
        )
        cmd = "fio %s --output-format=json --output=%s" % (job, output_file)
        cmd += power_cmd
        AutovalLog.log_info(
            "Running %s FIO command with power trigger: %s" % (self.job_name, cmd)
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
                    _msg = "[HAVOC]: fio interrupted due to power trigger"
                    check_parse_fio_error = True
            if not check_parse_fio_error:
                raise TestError(
                    str(exc),
                    component=COMPONENT.SYSTEM,
                    error_type=ErrorType.TOOL_ERR,
                )
        self.host.check_system_health()
        if check_parse_fio_error:
            ret = self.parse_fio_error(1, _msg, output_file)
        return ret, output_file

    def get_precondition_drives(self):
        """Return data drives for FIO precondition job"""
        _drives = self.get_drives("ssd", None, self.drives)
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
            self.boot_drive = DiskUtils.get_boot_drive(self.host)
        by_model = StorageUtils.group_drive_by_attr("model", self.drives)
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
                filesystem = params.get("filesystem", False)
                files = params.get("files", None)
                skip_fs = params.get("skip_fs", False)
                remote = params.get("remote", False)
                filesystem_type = params.get("filesystem_type", "xfs")
                filesystem_options = params.get("filesystem_options", "")
                for additional_arg in additional_args:
                    if precondition_loops:
                        _drives = self.get_precondition_drives()
                        AutovalUtils.validate_non_empty_list(
                            _drives,
                            "Drives for precondition",
                            log_on_pass=False,
                            component=COMPONENT.STORAGE_DRIVE,
                            error_type=ErrorType.SYSTEM_ERR,
                        )
                        # Secure_erase all drives
                        StorageUtils.format_all_drives(_drives)
                        # If file specific Precondition file is provided, use that
                        # else, Use the default precondition
                        precondition_template = params.get(
                            "precondition_template", "precondition.fio"
                        )
                        AutovalLog.log_info(
                            f"Starting precondition on drives: {_drives}"
                        )
                        # Preconditioning on ssd drives
                        self.precondition_drives(
                            _drives,
                            precondition_loops,
                            precondition_template,
                            remote,
                            fio_opts,
                        )
                    alias = self.generate_job_name(io_type, cycle, additional_arg)
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
                    )
                    AutovalLog.log_info("Starting fio on DUT")
                    # The if condition is for running fio with power trigger
                    # command and else condition is for the normal fio job.
                    if self.power_trigger:
                        result, output_file = self.run_interupted_fio(
                            job, self.power_cycle, remote=remote
                        )
                    else:
                        result, output_file = self.run_fio_on_dut(
                            job, remote=remote, opts=fio_opts, timeout=self.fio_timeout
                        )
                    self.fio_file = output_file
                    AutovalUtils.validate_condition(
                        result,
                        "Ran fio on %s" % output_file,
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.TOOL_ERR,
                    )
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
                    if write_iops_model and not self.skip_iops:
                        AutovalLog.log_info("Compare write iops by model:")
                        self.check_iops(
                            iops=write_iops_model,
                            _type="",
                            _by_model_or_cycle="model",
                            _read_or_write="write",
                        )
                    if read_iops_model and not self.skip_iops:
                        AutovalLog.log_info("Compare read iops by model:")
                        self.check_iops(
                            iops=read_iops_model,
                            _type="",
                            _by_model_or_cycle="model",
                            _read_or_write="read",
                        )
                    if latency_ms_model:
                        AutovalLog.log_info("Checking latency_ms threshold by model")
                        self.check_latency_ms(
                            latency_ms_model, _type="", _by_model_or_cycle="model"
                        )
        # Compare results by cycle at the end
        if write_iops and not self.skip_iops:
            AutovalLog.log_info("Compare write iops by cycle:")
            self.check_iops(
                iops=write_iops,
                _type="",
                _by_model_or_cycle="cycle",
                _read_or_write="write",
            )
        if read_iops and not self.skip_iops:
            AutovalLog.log_info("Compare read iops by cycle:")
            self.check_iops(
                iops=read_iops,
                _type="",
                _by_model_or_cycle="cycle",
                _read_or_write="read",
            )
        if latency_ms:
            AutovalLog.log_info("Checking latency_ms threshold by cycle:")
            self.check_latency_ms(latency_ms, _type="", _by_model_or_cycle="cycle")

        self.update_result()

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
        AutovalLog.log_info("Parsing results: %s" % self.fio_file)
        fio = {}
        perf = {}
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
            for r_w in ["read", "write", "trim"]:
                if job[r_w] is None or (
                    "runtime" in job[r_w] and job[r_w]["runtime"] == 0
                ):
                    continue
                jobname = job["jobname"]
                perf = {}
                for field in ["bw", "bw_agg", "bw_max", "bw_min", "bw_mean"]:
                    perf["%s (Kb/s)" % field] = job[r_w][field]
                    _job_data["%s_%s" % (r_w, field)] = job[r_w][field]
                for field in ["iops", "total_ios"]:
                    perf["%s" % field] = int(job[r_w][field])
                    _job_data["%s_%s" % (r_w, field)] = int(job[r_w][field])
                for lat in ["mean", "min", "max"]:
                    if "lat_ns" in job[r_w]:
                        _job_data[f"{r_w}_{lat}_lat"] = job[r_w]["lat_ns"][lat]
                        perf["lat_%s (nsec)" % lat] = job[r_w]["lat_ns"][lat]
                for clat_perc in clat_percentiles:
                    if "percentile" in job[r_w]["clat_ns"]:
                        if clat_perc in job[r_w]["clat_ns"]["percentile"].keys():
                            if "clat_ns" in job[r_w]:
                                _job_data[f"{r_w}_{clat_perc}"] = job[r_w]["clat_ns"][
                                    "percentile"
                                ][clat_perc]
                                perf[f"{clat_perc}%"] = job[r_w]["clat_ns"][
                                    "percentile"
                                ][clat_perc]
                AutovalLog.log_debug("\n%s -- %s" % (jobname, r_w))
                AutovalLog.log_debug(
                    ", ".join(
                        "{}: {}".format(key, value) for key, value in perf.items()
                    )
                )
            # Adding latency_ms to fio_results
            if job["latency_ms"]:
                for lat in latency_ms:
                    _job_data[f"latency_ms_{lat}"] = job["latency_ms"][lat]
            fio["result"].append(_job_data)
        return fio

    def trim(self, drives, opts=None, mnt: str = "/mnt/havoc") -> None:
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
            if mnt == "/mnt/havoc":
                mnt = f"{mnt}_{dev}"
            host = self.host
            FilesystemUtils.mount(host, dev, mnt, mnt_options, fstype)
            df_info = FilesystemUtils.get_df_info(host, dev)
            AutovalUtils.validate_condition(
                df_info["type"] == fstype,
                "Mounted %s at %s" % (dev, mnt),
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
        mnt: str = "/mnt/havoc",
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

        Raises
        ------
        TestStepError
            When fails to run FIO Job.
        """
        # Save value
        saved = self.skip_iops
        self.skip_iops = True
        # unmount the drives if already mounted before running preconditioning on them
        AutovalLog.log_info("Unmount drives for precondition")
        for dev in drives:
            if mnt == "/mnt/havoc":
                mnt = f"{mnt}_{dev}"
            if FilesystemUtils.is_mounted(self.host, mnt):
                FilesystemUtils.unmount(self.host, mnt)
        # If file specific (random/seq) Precondition file exists, use that
        # else, Use the default precondition
        write_iops = {}
        read_iops = {}
        latency_ms = {}
        by_model = StorageUtils.group_drive_by_attr("model", drives)
        for _cycle in range(1, precondition_loops + 1):
            job = self.create_fio_job(
                drives=drives,
                replace={},
                templ_filename=precondition_template,
            )
            AutovalLog.log_info("Starting preconditioning cycle %s on DUT" % _cycle)
            result, output_file = self.run_fio_on_dut(
                job=job,
                remote=remote,
                timeout=self.fio_timeout,
                opts=fio_opts,
            )
            self.fio_file = output_file
            AutovalUtils.validate_condition(
                result,
                "Precondition fio job %s" % output_file,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )
            results = self.parse_results()
            if self.enable_performance_metrics_validation:
                self.validate_performance_metrics(
                    results=results, _type="precondition", by_model=by_model
                )
            result_dict = {
                "precondition_" + str(_cycle) + str(int(time.time())): results
            }
            FioRunner.raw_result.update(result_dict)
            AutovalUtils.result_handler.add_test_results(result_dict)
            AutovalUtils.validate_condition(
                results,
                "Saved results for precondition fio job",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
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
            if write_iops_model or read_iops_model:
                AutovalLog.log_info("Compare precondition iops by model:")
            if write_iops_model:
                self.check_iops(
                    iops=write_iops_model,
                    _type="precondition",
                    _by_model_or_cycle="model",
                    _read_or_write="write",
                )
            if read_iops_model:
                self.check_iops(
                    iops=read_iops_model,
                    _type="precondition",
                    _by_model_or_cycle="model",
                    _read_or_write="read",
                )
            if latency_ms_model:
                AutovalLog.log_info(
                    "Checking precondition latency_ms threshold by model:"
                )
                self.check_latency_ms(
                    latency_ms_model, _type="precondition", _by_model_or_cycle="model"
                )
            # Compare results by cycle at the end
        if write_iops or read_iops:
            AutovalLog.log_info("Compare precondition iops by cycle:")
        if write_iops:
            self.check_iops(
                iops=write_iops,
                _type="precondition",
                _by_model_or_cycle="cycle",
                _read_or_write="write",
            )
        if read_iops:
            self.check_iops(
                iops=read_iops,
                _type="precondition",
                _by_model_or_cycle="cycle",
                _read_or_write="read",
            )
        if latency_ms:
            AutovalLog.log_info("Checking latency_ms threshold by cycle")
            self.check_latency_ms(
                latency_ms, _type="precondition", _by_model_or_cycle="cycle"
            )
        # Revert back
        self.skip_iops = saved

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
    def check_run_definition_format(run_definitions: Dict) -> None:
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
        iops: Dict[str, Any],
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
                            f"{key}: {_type} compare by {_by_model_or_cycle} - {_read_or_write} iops is {value}"
                        )
                    else:
                        iops_diff_percent = int(FioRunner.IOPS_DIFF * 100)
                        AutovalUtils.validate_less_equal(
                            float(diff),
                            max(value) * FioRunner.IOPS_DIFF,
                            f"{key}: {_type} compare by {_by_model_or_cycle} - {_read_or_write} iops are {value}"
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
                AutovalLog.log_info("%s: %s is not a list" % (key, value))

    def check_latency_ms(self, latency_ms: Dict, _type, _by_model_or_cycle) -> None:
        """
        Check latency_ms

        This method is used to check the latency_ms value has met
        expected threshold.

        Parameters
        ----------
        latency_ms: Dict
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
        self, results: Dict, _filter: str, filter_results: Dict, by_model: Dict
    ) -> Tuple[Dict, Dict]:
        """
        Filter results by params.

        This method will filter the results from the fio parse_results
        based on the provided input.

        Parameters
        ----------
        results: Dict
             Fio parse Results.
        _filter: String
             Parameter whose values are to filtered.
        results: Dict
             Storage reference where the values of the parameter are to be stored.
        by_model: Dict
             Contains map of model and drives respective to the model.

        Returns
        -------
        filter_results: Dict
             Contains the fio parameter values from fio parse results
             for all drives.
        filter_results_by_model: Dict
             Contains the fio parameter values from fio parse results
             grouped by model
        """
        filter_results_by_model = {}
        key_gen = lambda x: (
            os.path.join("/dev", self.boot_drive)
            if os.path.basename(FioRunner.MOUNTED_DRIVE_FIO_PATH) in x
            else x
        )
        key_value_list = [
            (key_gen(i["opt_filename"]), i[_filter])
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

    def run_fio(
        self,
        host: Host,
        fio_command: str,
        working_dir: Optional[str] = None,
        timeout: Optional[int] = None,
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
        self, results: Dict, _type: str, by_model: Dict
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
        self, metric: str, metric_results: Dict, _type: str, _by_model_or_cycle: str
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
                    f"No values found to validate {metric} "
                    "with the expected threshold",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )

    def _convert_ns_to_s(self, value_ns: Union[int, float]) -> float:
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
