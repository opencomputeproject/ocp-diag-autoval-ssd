#!/usr/bin/env python3

# pyre-unsafe
"""Drive Integrity test validates data integrity using fio jobs."""
# TestCase IDs    : USSDT_006,USSDT_007, USSDT_008
import os
import random
import re
import time
from typing import Dict, List, Union

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.test_base import TestStatus
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.file_actions import FileActions	
from autoval.lib.utils.site_utils import SiteUtils
from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.md_utils import MDUtils
from autoval_ssd.lib.utils.storage.drive import Drive
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase

# io size in %
IO_SIZE = [1, 5, 10, 25, 33, 50, 75, 100]

FIO_JOB = [
    "blocksize=4k",
    "iodepth=128",
    "direct=1",
    "group_reporting=1",
    "numjobs=1",
    "ioengine=libaio",
]

DRIVE_FILL_FIO_JOB = [
    "blocksize=128k",
    "iodepth=64",
    "direct=1",
    "group_reporting=1",
    "numjobs=1",
    "ioengine=libaio",
    "rw=write",
    "verify=md5",
    "verify_backlog=10000000",
    "verify_state_save=1",
    "verify_async=4",
    "verify_fatal=1",
    "verify_dump=1",
]
RUNTIME = 150


class FioErrorParsingException(Exception):
    """Exeption for FioError"""

    pass


class DriveDataIntegrityTest(StorageTestBase):
    """Test validates data integrity for different reboot methods"""

    def __init__(self, *args, **kwargs) -> None:
        """
        Initializes the Drive data integrity test.
        This method initializes the basic configuration for logging
        information, load and store the input details
        gathered from control file having user inputs.

        Test control params:

            Int cycle_count: Number of test cycles
            String cycle_type: type of power cycle to be performed during test
            Bool power_random_time: True/False to enable/disable random time between power cycles
            Dict[str,str] ext_json_file: json file to be used for fio job
            Bool is_md: True/False to enable/disable md
            Int number_of_seq_io: Number of sequential IOs to be performed
            Bool remote_fio: True/False to enable/disable remote fio
            String drive_interface: filter for drives with this interface to test
            String drive_type: hdd, ssd, etc.
            List drives: list of drives to test: e.g. sdac, sdf,
            Int precondition_drive_fill_percent: drive fill percent before test
        """
        super().__init__(*args, **kwargs)
        self.cycle_count = self.test_control["cycle_count"]
        self.cycle_type = self.test_control["cycle_type"]
        self.power_random_time = self.test_control.get("power_random_time", True)
        self.smart_benchmark_file = self.test_control.get(
            "ext_json_file", {"nvme": "nvme_validate_fdi.json"}
        )
        self.is_md = self.test_control.get("is_md", False)
        self.number_of_seq_io = self.test_control.get("number_of_seq_io", 100)
        # Remote mode in FIO uses client/server model of FIO, the controller,
        # DUT can be in different DC and possibly IO traffic is blocked and
        # get "SEND_ETA timed out with exit code", to overcome this 'local mode'
        # in FIO should be made default.
        self.remote_fio = self.test_control.get("remote_fio", False)
        self.drive_interface = self.test_control.get("drive_interface", None)
        self.drive_type = self.test_control.get("drive_type", None)
        self.drives = self.test_control.get("drives", None)
        self.precondition_drive_fill_percent = self.test_control.get(
            "precondition_drive_fill_percent", None
        )
        self.drive_fill_timeout = self.test_control.get("cmd_timeout", 9600)
        self.test_size = random.choice(IO_SIZE)
        self.ip4 = None
        self.ipv6 = None
        self.fiolog_dir = None
        self.power_cmd = None
        self.trigger_timeout = 60
        self.status_interval = self.test_control.get("status_interval", 1)
        self.stop_fio_process_check = False
        self.control_server_logs = SiteUtils.get_control_server_logdir()
        self.fiolog_server_dir = None

    def setup(self, *args, **kwargs) -> None:
        """Prerequisite for drive data integrity test.

        This method creates log directories for the test,
        verifies the DUT is accessible by both Inband and OutofBand, stores the
        OpenBMC and System configuration before the testcase execution.

        Includes functionality from legacy method '_test_setup' to:

        Install dependencies and gets FIO version/ip address to perform
        Data integrity test.

        This method installs the dependencies for running Data integrity testcase,
        checks for the FIO version and gets the IPv4 address from the host.

        Raises
        ------
        TestStepError
            When fails to install fio rpm.
        CmdError
            When fails to execute the FIO installation command on the host.
        """
        super().setup(*args, **kwargs)
        if "sled" in self.cycle_type:
            self.power_random_time = False
            if len(self.hosts) > 1:
                num_sleds = self.check_same_sled_hosts()
                self.validate_equal(
                    num_sleds,
                    1,
                    f"Hosts are from {num_sleds} sleds, but from same sled expected",
                    log_on_pass=False,
                    error_type=ErrorType.TEST_TOPOLOGY_ERR,
                )
        self.check_supported_fio_version()
        if self.remote_fio:
            self._get_server_log_dir()
        else:
            self._get_log_dir()
        self.ip4 = self._is_hostname_ip4()
        self.ipv6 = self.get_ipv6_addr()
        self.power_cmd = self._fio_trigger_cmd()

    def check_same_sled_hosts(self) -> int:
        """Check if DUTs from same sled"""
        sled_ids = [self.hosts[index]["sled_id"] for index in range(len(self.hosts))]
        return len(set(sled_ids))

    def _is_hostname_ip4(self) -> bool:
        """Gets ipv4 address.

        This method gets the ipv4 address and matches with the hostname
        of the Host obj.

        Returns
        -------
        Boolean
            Returns true when Ipv4_re matches with the hostname.
        """
        ipv4_re = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
        return re.match(ipv4_re, self.host.hostname) is not None

    def _get_log_dir(self) -> None:
        """Assigns log directory.

        This method assigns a log directory for the FIO output.
        """
        self.fiolog_dir = os.path.join(
            self.dut_logdir[self.host.hostname], "fio_results"
        )
        if not FileActions.exists(self.fiolog_dir, self.host):
            FileActions.mkdirs(self.fiolog_dir, self.host)
    
    def _get_server_log_dir(self) -> None:
        """
        This method sets up the directory for storing FIO log files on the control server.
        It creates a directory named `fio_results` in the `control_server_logs` directory
        if it does not already exist.
        """
        self.fiolog_server_dir = os.path.join(self.control_server_logs, "fio_results")
        if not FileActions.exists(self.fiolog_server_dir, self.host.localhost):
            FileActions.mkdirs(self.fiolog_server_dir, self.host.localhost)

    def execute(self) -> None:
        """Executes FIO jobs on the given hosts.

        This methods performs power cycle for the mentioned cycle_type
        (ac, dc, warm)on OpenBMC and for cycle_type(inband_reboot) on DUT.
        Runs the FIO jobs on the drives for the mentioned iterations(cycle_count)
        and again perform power cycle for the mentioned cycle_type.
        Compare Drive logs before and after the Power Cycle.

        Raises
        ------
        TestError
            When fails to detect boot drives.
        TestStepError
            When the test drive list is empty and fails in drive data
            integrity check.
        """
        if self.precondition_drive_fill_percent:
            self.run_fio_precondition_drive_fill("Precondition_Drive_Fill")
        # Get test drives from host
        for i in range(1, self.cycle_count + 1):
            if self.is_md:
                test_drives = list(MDUtils.list_md_arrays(self.host).keys())
            else:
                test_drives = self.test_drives.copy()
            self.save_drive_logs_async(test_drives)
            self.fio_test(test_drives, i)
            self.validate_condition(
                True,
                "Verify Flash Integrity for Cycle - %s" % i,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
            self.cleanup_test_file(force_delete=True)
        self.check_drives_presence()

    def run_fio_precondition_drive_fill(self, cycle: str) -> None:
        """
        Runs FIO to fill the test drives to a given percent_capacity

        Parameter
        ---------
        cycle         : String
           Test cycle/step.
        """
        self.test_size = self.precondition_drive_fill_percent
        self.log_info("Cycle %s - Write in progress" % cycle)
        self.run_fio(
            DRIVE_FILL_FIO_JOB, self.test_drives, "write", cycle, power_trigger=False
        )
        self.precondition_drive_fill_percent = None

    def get_ipv6_addr(self) -> str:
        """Method to get the ipv6 address

        Returns
        -------
        ip_addr : str
            ipv6 addr is returned
        """
        ip_addr = self.get_ip(ip_type="inet6")
        return ip_addr

    def get_ip(self, ip_type: str = "inet", interface: str = "eth0"):
        """
        Return IP for selected interface
        ip_type can be inet or inet6
        """
        # ip_type can be inet or inet6
        out = self.host.run("ip addr show %s" % interface)
        if ip_type == "inet":
            match = re.search(r"%s (\S+)\/.*" % ip_type, out)
            if match:
                ip = match.group(1)
                AutovalLog.log_debug(
                    f"IP of {self.host.hostname} with {interface}: %s" % ip
                )
                return ip
            raise TestError("Did not find IP type %s in %s" % (ip_type, out))
        if ip_type == "inet6":
            pattern = re.compile(
                r"inet6\s+([a-z0-9:]+).*(?:scope global)",
                re.MULTILINE,
            )
            match = pattern.search(out)
            if match:
                ip = match.group(1)
                AutovalLog.log_debug(
                    f"IP of {self.host.hostname} with {interface} is: {ip}"
                )
                return ip
            else:
                ip = self.get_link_local_ip_rdma(interface, out)
                if ip:
                    AutovalLog.log_debug(
                        f"IP of {self.host.hostname} with {interface} is: {ip}"
                    )
                    return ip
            raise TestError("Did not find IP type %s in %s" % (ip_type, out))
        raise TestError("Unknown IP type %s" % ip_type)

    def fio_test(self, test_drives, cycle) -> None:
        """Runs FIO tests on the given hosts.

        This method runs fio for the following jobs in sequential order:
        a. write
        b. read
        c. verify

        Parameter
        ---------
        test_drives : Dictionary {String, String}
           All drives for the given drive type.
        cycle         : Integer
           No. of test cycle value.

        Raises
        ------
        TestStepError
            When fails to run the FIO job.
        """
        if self.power_random_time:
            # Get a random trigger_timeout
            self.trigger_timeout = self.test_control.get(
                "trigger_timeout", 30 * int(random.randint(3, 5))
            )
        else:
            self.trigger_timeout = RUNTIME
        # Get random size
        self.test_size = random.choice(IO_SIZE)
        self.validate_no_exception(
            self.write_io,
            [test_drives, cycle],
            "Cycle %d: Fio write job completed." % cycle,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )
        # make sure to all drives are populated.
        self._validate_hdd_drive_count()
        self.check_block_devices_available()
        # When using a trigger, last in-flight IO will not be loaded
        # into the state file, but reading back the last wrote IO
        # can cause MPECC error. This read is to capture that MPECC error
        self.start_fio_monitor()
        self.validate_no_exception(
            self.read_io,
            [test_drives, cycle],
            "Cycle %d: Fio read job completed." % cycle,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )
        self.stop_fio_monitor()

        for drive in test_drives:
            if drive.block_name == self.boot_drive:
                if self.cycle_type in ["ac", "dc", "warm"]:
                    test_drives.remove(drive)
                    self.log_info("Skipping Fio Verify Job for Boot drive")
        # Since power loss module not available in boot drive,
        # we will get error like bad header while executing fio verify.
        # Hence, fio verify only for data drives.
        # More info available in T86898653.
        if test_drives:
            # read with verify
            self.start_fio_monitor()
            self.validate_no_exception(
                self.verify_io,
                [test_drives, cycle],
                "Cycle %d: Fio verify job completed." % cycle,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.TOOL_ERR,
            )
            self.stop_fio_monitor()

    def monitor_fio_process(self) -> None:
        """
        Check if the FIO process is currently running on the host machine.

        Args:
            None

        Returns:
           None
        """
        cmd = "ps -eaf | grep fio"
        fio_started_running = False
        fio_stopped_running = False
        while not self.stop_fio_process_check:
            time.sleep(5)
            out = self.host.run(cmd=cmd)
            fio_is_running = "fio_" in out
            AutovalLog.log_as_cmd(
                f"FIO process is {'' if fio_is_running else 'not'} running"
            )
            if not fio_started_running and fio_is_running:
                AutovalLog.log_info("FIO started running")
                fio_started_running = True
            if fio_started_running and not fio_is_running:
                AutovalLog.log_info("WARNING:  FIO stopped running")
                fio_stopped_running = True
            if fio_stopped_running and fio_is_running:
                AutovalLog.log_info(
                    "WARNING:  FIO is started running again (after it stopped)"
                )

    def start_fio_monitor(self) -> None:
        """
        Start FIO process check

        Args:
            None

        Returns:
            None
        """
        self.fio_process_queue = []
        self.stop_fio_process_check = False
        self.fio_process_queue.append(
            AutovalThread.start_autoval_thread(
                self.monitor_fio_process,
            )
        )

    def stop_fio_monitor(self) -> None:
        """
        Stop FIO process check

        Args:
            None

        Returns:
            None
        """
        self.stop_fio_process_check = True
        if len(self.fio_process_queue):
            AutovalLog.log_info("INSIDE STOP_FIO_CHECK")
            AutovalThread.wait_for_autoval_thread(self.fio_process_queue)

    def cleanup_test_file(self, force_delete: bool = False) -> None:
        """Cleanup test file and cache"""
        # Delete test file
        self.host.run(cmd="rm -f /root/fio_file", ignore_status=True)  # noqa
        # Delete state files
        if self.test_status == TestStatus.PASSED or force_delete:
            cmd = "rm -f *state"
            self.host.run(
                cmd=cmd, working_directory=self.fiolog_dir, ignore_status=True
            )
        self.host.clear_cache()

    def write_io(self, test_drives, cycle) -> None:
        """Run "write" FIO jobs on the hosts.

        This method constructs the parameters to create and run
        "write" fio jobs on the host.

         Parameters
         ----------
         test_drives : Dictionary {String, String}
            All drives for the given drive type.
         cycle         : Integer
            No. of test cycle value.
        """
        self.log_info("Cycle %s" % cycle)
        self.log_info("Write in progress")
        write_job = list(FIO_JOB)
        w_params = [
            "rw=randwrite",
            "runtime=10m",
            "time_based",
            "verify=md5",
            "verify_backlog=10000000",
            "verify_state_save=1",
            "verify_async=4",
            "verify_fatal=1",
            "verify_dump=1",
        ]
        write_job.extend(w_params)
        self.run_fio(write_job, test_drives, "write", cycle, power_trigger=True)

    def read_io(self, test_drives, cycle) -> None:
        """Run "read" FIO jobs on the given hosts.

        This method constructs the parameters to create and run
        "read" fio job on the hosts.

        Parameters
        ----------
        test_drives : Dictionary {String, String}
           All drives for the given drive type.
        cycle         : Integer
           No. of test cycle value.
        """
        read_job = list(FIO_JOB)
        _runtime = self.trigger_timeout * 2
        r_params = [
            "rw=randread",
            "runtime=%s" % _runtime,
            "time_based",
            "verify=md5",
            "verify_backlog=10000000",
            "verify_state_load=1",
            "verify_async=4",
            "verify_fatal=1",
            "verify_dump=1",
        ]
        read_job.extend(r_params)
        self.log_info("Read in progress")
        self.run_fio(read_job, test_drives, "read", cycle)

    def verify_io(self, test_drives, cycle) -> None:
        """Run "verify" FIO jobs on the given hosts.

        This method constructs the parameters to create and run
        "verify" fio job on hosts.

        Parameters
        ----------
        test_drives : Dictionary {String, String}
            All drives for the given drive type..
        cycle         : Integer
            No. of test cycle value.
        """
        verify_job = list(FIO_JOB)
        r_params = [
            "rw=randread",
            "verify=md5",
            "verify_backlog=10000000",
            "verify_state_load=1",
            "verify_async=4",
            "verify_fatal=1",
            "verify_dump=1",
        ]
        verify_job.extend(r_params)
        self.log_info("Verify in progress")
        self.run_fio(verify_job, test_drives, "verify", cycle)

    def run_fio(
        self,
        job_args: List[str],
        test_drives: Dict[str, str],
        name: str,
        cycle: Union[str, int],
        power_trigger: bool = False,
    ) -> None:
        """Run FIO jobs on the given hosts.

        This method creates the FIO job file based on job_args
        and runs the job file based on mode(remote/local).
        Also raises FioErrorParsingException.

        Parameter
        ---------
        job_args      : 'List' of :obj: 'Strings'
            FIO global parameters along with job specific parameters.
        test_drives : Dictionary {String, String}
            All drives for the given drive type.
        name          : String
            Fio file name.
        cycle         : Integer
            Iteration number.
        power_trigger : Boolean
            If True fio will run with trigger. Here the default value is False.
        """
        di_job = self.create_fio_job(job_args, test_drives, name, cycle)
        if self.remote_fio:
            fio_output_file = (
                f"{self.fiolog_server_dir}/fio-cycle_{cycle}_{name}.log".format(
                    cycle, name
                )
            )
            self._run_fio_remote(di_job, fio_output_file, power_trigger=power_trigger)
        else:
            fio_output_file = (
                f"{self.fiolog_dir}/fio-cycle_{cycle}_{name}.log".format(cycle, name)
            )
            self._run_fio_local(di_job, fio_output_file, power_trigger=power_trigger)

    def _run_fio_cmd(self, cmd: str, timeout: int, power_trigger: bool) -> None:
        """
        Run an fio command with the given arguments.

        Args:
            cmd (str): The fio command to run.
            timeout (int): The maximum time to wait for the command to complete.
            power_trigger (bool): Whether to trigger a power event during the test.

        Returns:
            None
        """
        self.log_info(f"Running command: {cmd}")
        self.host.run(cmd=cmd, working_directory=self.fiolog_dir, timeout=timeout)

    def _run_fio_local(
        self, di_job: str, fio_output_file: str, power_trigger: bool = False
    ) -> None:
        """Runs FIO from the DUT.
        This method runs fio from the DUT (local mode). Retry if FIO output
        is not collected due to interruption. Also raises Exception when
        failed to run the job in local.
        Args:
            di_job (str): Path to fio job file.
            fio_output_file (str): Filelocation to dump fio output.
            power_trigger (bool, optional): If True fio will run with trigger. Default is False.
        Raises:
            TimeoutError: When fails to collect output in FIO output file.
        """
        cmd_timeout = 1200
        if self.precondition_drive_fill_percent:
            cmd_timeout = self.drive_fill_timeout
        check_parse_fio_error = False
        _msg = ""
        current_reboot = ""
        cmd = "fio %s --output-format=json --output=%s" % (di_job, fio_output_file)
        if power_trigger:
            current_reboot = self.host.get_last_reboot()
            cmd += f" --status-interval={self.status_interval}"
            cmd += f" --trigger-timeout={self.trigger_timeout} {self.power_cmd}"
            AutovalLog.log_info(
                f"Power trigger enabled and current reboot is {current_reboot}"
            )
        try:
            self._run_fio_cmd(cmd, cmd_timeout, power_trigger)
            time.sleep(30)
            out = self.host.bmc.power_status().upper()
            if "OFF" in out:
                self.host.bmc.power_on()
        except Exception as exc:
            valid_exceptions = [
                "timed out",
                "timeout",
                "CONNECT_UNKNOWN",
                "Internal error",
                "failed with [36]",
                "Connection Error",
                "AutovalThread",
                "Warning: Server FPGA fw version is missing or not ready, control via BIC\r\n",
            ]
            for i in valid_exceptions:
                if i in str(exc) and not check_parse_fio_error:
                    AutovalLog.log_as_cmd(cmd)
                    AutovalLog.log_info(str(exc))
                    if power_trigger:
                        _msg = "Fio was likely interrupted due to power trigger"
                        self.log_info(_msg)
                    try:
                        self.host.bmc.bmc_host.wait_for_reconnect(False, timeout=180)
                    except Exception as e:
                        AutovalLog.log_info(
                            f"When trying to reconnect to BMC we got this error : {str(e)}"
                        )
                        time.sleep(30)
                    out = self.host.bmc.power_status().upper()
                    if "OFF" in out:
                        self.host.bmc.power_on()
                    check_parse_fio_error = True
            if not check_parse_fio_error:
                AutovalLog.log_info(str(exc))
                if power_trigger:
                    self.host.reconnect(timeout=2400)
                    self.host.check_system_health()
                raise TestError(str(exc), error_type=ErrorType.DRIVE_ERR)
        if power_trigger:
            self.host.check_system_health()
        if check_parse_fio_error:
            AutovalLog.log_info("check_parse_fio_error running...")
            self.parse_fio_error(1, _msg, fio_output_file)

    def _run_fio_remote(
        self, di_job: str, fio_output_file: str, power_trigger: bool = False
    ) -> None:
        """Runs FIO from the remote machine.
        This method runs fio in client-server mode.
        Args:
            di_job (str): Path to fio job file.
            fio_output_file (str): File location to dump fio output.
            power_trigger (bool, optional): If True fio will run with trigger. Defaults to False.
        Raises:
            TestError: When errors are present in the FIO output file.
        """
        self.start_fio_daemon()
        cmd = "fio --client=ip%s:%s %s --output-format=json --output=%s" % (
            "" if self.ip4 else "6",
            self.ipv6,
            di_job,
            fio_output_file,
        )
        if power_trigger:
            current_reboot = self.host.get_last_reboot()
            cmd += f" --status-interval={self.status_interval}"
            cmd += f" --trigger-timeout={self.trigger_timeout} {self.power_cmd}"
            AutovalLog.log_info(
                f"Power trigger enabled and current reboot is {current_reboot}"
            )
        ret = self.host.localhost.run_get_result(
            cmd=cmd,
            working_directory=self.fiolog_server_dir,
        )
        if ret.return_code != 0:
            self.parse_fio_error(ret.return_code, ret.stdout, fio_output_file)
        if power_trigger:
            self.host.check_system_health()

    def check_drives_presence(self) -> None:
        """Verifies the drives presence.

        This method checks for the drives presence in the host
        after each test cycle completion.

        Raises
        ------
        TestStepError
            When fails to get available drives on the host.
        """
        available_drives = self.get_block_name_from_drive_list(self.scan_drives())
        drives_before_stress = self.get_block_name_from_drive_list(self.drives)
        AutovalUtils.validate_equal(
            drives_before_stress.sort(),
            available_drives.sort(),
            "Check drive availability",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def get_custom_filter(self):
        """Gets custom filter.
        This method appends the Config filter details for every cycle test.

        Returns
        -------
        cfg_filter: Dictionary {String,String}
            Updates the filter name as cycle test.
        """
        cfg_filter = []
        cfg_filter.append({"filter_name": "cycletest"})
        return cfg_filter

    def create_job_content(
        self, dev_str: str, device, index, options=None, job=None
    ) -> str:
        """Creates content for each job in job file for FIO run.

        This method creates a job content with the available "job_str" parameters for
        the drives.

        Parameters
        ----------
        dev_str    : String
           Contains fio file content for global, other jobs would to added
        device     : String
           drive for which the job would be created
        index      :  Integer
           Fio file name.
        options    : List
           device options
        job        : String
           fio job

        Returns
        -------
        dev_str   : String
           Returns the fio content for each job.
        """
        job_name = "trim" if job == "trim" else "job"
        # if selected io size 100%, then there is no space to run trim option
        # hence, skipping fio trim
        if job == "trim" and self.test_size == 100:
            self.log_info(
                f"Since, drive {device} total size used for fio write operation, can't do trim"
            )
            return dev_str
        dev_str += "[%s%d]\n" % (job_name, index)
        if str(device) == str(self.boot_drive):
            if job == "write":
                dev_str += "rw=randwrite\n"
            if job == "trim":
                dev_str += "rw=randtrim\n"
                dev_str += "offset=20%\n"
            if DiskUtils.is_drive_mounted(self.host, str(self.boot_drive)):
                dev_str += "filename=/root/fio_file\n"
            else:
                dev_str += "filename=/dev/%s\n" % str(device)
            # fio does not support size in %
            dev_str += "size=60g\n"
            dev_str += "fdatasync=1\n"
        else:
            remaining_size = self.test_size
            if job == "write":
                dev_str += "rw=randwrite\n"
            if job == "trim":
                dev_str += "rw=randtrim\n"
                # trim need to start from end of write job allocated size.
                # otherwise, write, trim is going to use same memory
                # and will fail with bad magic header.
                dev_str += f"offset={self.test_size}%\n"
                remaining_size = 100 - self.test_size
            dev_str += "filename=/dev/%s\n" % str(device)
            dev_str += f"size={remaining_size}%\n"
        if options:
            for option in options:
                dev_str += "%s\n" % option
        dev_str += "new_group=1\n"
        return dev_str

    def create_fio_job(self, job_str, drives, name, cycle):
        """Creates job file for FIO run.

        This method creates a job file with the available "job_str" parameters for
        the drives.

        Parameters
        ----------
        job_str    : :obj: 'List' of :obj: 'Strings'
           FIO parameters.
        drives     : Dictionary {String,String}
           Drives of specified drive type on the host.
        name   :  String
           Fio file name.

        Returns
        -------
        job_file   : String
           JobFile name along with location.
        """
        idx = 0
        dev_str = "[global]\n" + "\n".join(job_str) + "\n"
        filename = f"seq_io_{name}_cycle_{cycle}.fio"
        if isinstance(drives, dict):
            for device, options in drives.items():
                if name == "write":
                    dev_str = self.create_job_content(
                        dev_str, device, idx, options=options, job=name
                    )
                else:
                    dev_str = self.create_job_content(
                        dev_str, device, idx, options=options
                    )
                idx += 1
            # trim job info need to append at the end of fio job file,
            # otherwise fio write job will fail
            # create *-verify.state file with different name,
            # then fio read job will fail with stale file issue
            # due to different verify.state file.
            for device, options in drives.items():
                if self.is_trim_needed(name, device):
                    dev_str = self.create_job_content(
                        dev_str, device, idx, options=options, job="trim"
                    )
                    idx += 1
        else:
            for device in drives:
                if name == "write":
                    dev_str = self.create_job_content(dev_str, device, idx, job=name)
                else:
                    dev_str = self.create_job_content(dev_str, device, idx)
                idx += 1
            # trim job info need to append at the end of fio job file,
            # otherwise fio write job will fail
            # create *-verify.state file with different name,
            # then fio read job will fail with stale file issue
            # due to different verify.state file.
            for device in drives:
                if self.is_trim_needed(name, device):
                    dev_str = self.create_job_content(dev_str, device, idx, job="trim")
                    idx += 1
        if self.remote_fio:
            job_file = os.path.join(self.fiolog_server_dir, filename)
            FileActions.write_data(job_file, dev_str)
        else:
            # if trigger timeout chosen less than 60sec, then written fio job file data
            # will be unavailable post cycle cmd. Hence, either delay needed to write the
            # data from cache to drive or sync cmd need to execute. Here, I am using sync
            # command in FileActions module write_data method.
            job_file = os.path.join(self.fiolog_dir, filename)
            FileActions.write_data(job_file, dev_str, host=self.host, sync=True)
        return job_file

    def is_trim_needed(self, name: str, device: Union[Drive, str]) -> bool:
        """Checks if trim is needed for the given drive.
        TRIM is needed only for SSD's and not for HDD's.

        Args:
            name (str): The name of the drive to check.
            device (Union[str,Drive]): The device to check.
                          This can be either a string representing the device path
                          or a `StorageDevice` object.

        Returns:
            bool: True if trim is needed for the given drive, False otherwise.
        """
        return (
            name == "write"
            and (str(device) != str(self.boot_drive))
            and not self.precondition_drive_fill_percent
            and "nvme" in str(device).lower()
        )

    def start_fio_daemon(self) -> None:
        """Starts FIO daemon on the hosts.

        This method kills the fio and setup fio server on the host.
        """
        self.host.run("killall fio", ignore_status=True)  # noqa
        # Setup fio server on the host
        self.host.run("rm -f /tmp/fio.pid", ignore_status=True)  # noqa
        cmd = "fio --server=ip%s:%s --daemonize=/tmp/fio.pid" % (
            "" if self.ip4 else "6",
            self.ipv6,
        )
        self.log_info(f"Running command: {cmd}")
        self.host.run(cmd=cmd)  # noqa

    def parse_fio_error(self, exit_code, cmd_out, fio_output_file: str) -> None:
        """Parse the FIO output file for error code.

        This method checks for any error in the fio output file, increments
        the count value and raises TestError Exception.

        Parameters
        ----------
        exit_code       : Integer
           FIO command exit code.
        cmd_out         : String
           FIO Command output.
        fio_output_file : String
           FIO output results file location.

        Raises
        ------
        TestError
           When errors present in the FIO output file.
        """
        # Ignoring if "timeout on cmd SEND_ETA" while FIO
        if re.search(r"timeout on cmd SEND_ETA", cmd_out):
            self.log_info(
                "SEND_ETA timed out with exit code: %s,\ncmd_out: %s"
                % (exit_code, cmd_out)
            )
            return
        err_count = self._count_fio_err(fio_output_file)
        if err_count == 0:
            return
        self.log_info(f"FIO Failed - cmd output: {cmd_out}")
        raise TestError(
            "FIO Failed, \ncmd_out: %s, \nlog file: %s"
            % (cmd_out, os.path.basename(fio_output_file))
        )

    def _count_fio_err(self, fio_output_file: str) -> int:
        """Counts error from FIO output file on the host.

        This method matches error count from an FIO result file
        and return error count. Also raise FioErrorParsingException and
        TestError when failed to find the fio output file.

        Parameters
        ----------
        fio_output_file  : String
            Path to FIO result file.

        Returns
        -------
        err_count     : Integer
            fio error count.

        Raises
        ------
        FioErrorParsingException
             When fails to find errors in FIO output file.
        Testerror
            When fails to find FIO output in output file path.
        """
        if FileActions.exists(fio_output_file, host=self.host):
            fio_out = FileActions.read_data(fio_output_file, host=self.host)
            if not fio_out:
                raise TestError(f"Fio output file is empty: {fio_output_file}")
            error_list = re.findall(r'"error" : (\d*)', fio_out)
            if error_list:
                return int(error_list[-1])
            self.log_info(f"Could not find error count from fio output file: {fio_out}")
            raise FioErrorParsingException(
                "Could not find error count from fio output file %s" % fio_output_file
            )
        self.log_info(f"Fio output file not found - {fio_output_file}")
        raise TestError("Fio output file does not exist: %s" % fio_output_file)

    def check_supported_fio_version(self) -> None:
        """Check supported fio version for the DUT or/and Controller"""
        if self.remote_fio:
            fio_runner = FioRunner(self.host.localhost, self.test_control)
            # Might be fio not installed on the controller.
            # Hence, not required to validate fio ver in remote method disabled case.
            fio_runner.check_fio_version(self.host.localhost)
        fio_runner = FioRunner(self.host, self.test_control)
        fio_runner.check_fio_version(self.host)

    def cleanup(self, *args, **kwargs) -> None:
        """Cleanup for drive data integrity test.

        This method collects and saves the DUT and OpenBMC Configurations
        and compares between the pre and post test configurations,and
        saves the test result and command metrics information.

        Raises
        ------
        TestStepError
            When fails to collect the configuration from DUT and/or OpenBMC and
        mismatch values between the pre and post configuration for DUT and
        OpenBMC.
        """
        AutovalLog.log_info("Starting to clean up drive data integrity test")
        self.stop_fio_monitor()
        try:
            self.cleanup_test_file()
            out = self.host.bmc.power_status().upper()
            if "OFF" in out:
                self.host.bmc.power_on()
        except Exception as exc:
            AutovalLog.log_info(str(exc))
        finally:
            super().cleanup(*args, **kwargs)

    def get_test_params(self) -> str:
        if self.remote_fio:
            io_type = "fio ran in server-client mode"
        else:
            io_type = "fio jobs ran on DUT while power were cut off"
        return (
            f"Cycle type: {self.cycle_type}.\n"
            f"Number of iteration: {self.cycle_count}\n"
            f"{io_type}."
        )

    def _fio_trigger_cmd(self) -> str:
        """Gets fio trigger command.

        This method includes trigger option to the fio command based
        on the cycle type.

        Returns
        -------
        power_cmd : String
            Trigger option which is added to the fio command.
        """
        power_cmd = self.host.bmc.get_fio_trigger_cmd(
            self.cycle_type, remote=self.remote_fio
        )
        return power_cmd
