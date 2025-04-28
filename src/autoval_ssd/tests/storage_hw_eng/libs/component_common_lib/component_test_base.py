# pyre-unsafe
import copy
import json
import os
import re
import typing as t

import pandas as pd
from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_exceptions import SystemInfoException, TestError
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalLog, AutovalUtils
from autoval.lib.utils.decorators import retry
from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.md_utils import MDUtils
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils

# Data Records
from autoval_ssd.tests.storage_hw_eng.libs.data_types.dmesg_record import (
    Dmesg,
    DmesgEntry,
)
from autoval_ssd.tests.storage_hw_eng.libs.data_types.fio_data.fio_data import (
    FioJobInputParams,
)
from autoval_ssd.tests.storage_hw_eng.libs.data_types.smart_record import (
    SmartctlInfo,
    SmartInfoFactory,
)
from autoval_ssd.tests.storage_hw_eng.libs.ext_test_base.extended_test_base import (
    ExtendedTestBase,
)
from autoval_ssd.tests.storage_hw_eng.libs.ext_test_base.tasks import TestTask

from .common_dmesg_check import DmesgCheckComponent
from .component_data_base import ComponentInputBase, ComponentOutputBase


class ComponentTestBase(ExtendedTestBase):
    """
    The Component Test Base
    """

    def __init__(
        self, inputT=ComponentInputBase, outputT=ComponentOutputBase, **kwargs
    ):
        if not issubclass(inputT, ComponentInputBase):
            TestError(
                f"Type {inputT} is not a subclass of {ComponentInputBase}!"
                + " The HDD Test base requires that the input type be a subclass."
            )
        if not issubclass(outputT, ComponentOutputBase):
            TestError(
                f"Type {outputT} is not a subclass of {ComponentOutputBase}!"
                + " The HDD Test base requires that the output type be a subclass."
            )

        super().__init__(inputT=inputT, outputT=outputT, **kwargs)

    def setup(self, **kwargs):
        """
        Setup for the Component Tests.
        """
        super().setup(**kwargs)
        if self.input_params.collect_dmesg:
            self.log_info("Collecting initial dmesg")
            init_dmesg = self.get_host_dmesg(clear=True)
            self.output.initial_dmesg_raw = init_dmesg
            self.output.initial_dmesg = Dmesg.from_dmesg_output(init_dmesg)

    def execute(self):
        pass

    def cleanup(self, **kwargs):
        """
        This is the cleanup function. This will be called after the execute function.
        Note that this will be called regardless of pass condition on execute.
        """

        if (
            self.host is not None
            and hasattr(self, "output")
            and hasattr(self, "input_params")
        ):
            # Check dmesg

            if self.input_params.collect_dmesg:
                self.log_info("Collecting final dmesg")
                fin_dmesg = self.get_host_dmesg(clear=True)
                self.output.final_dmesg_raw = fin_dmesg
                parsed_dmesg = Dmesg.from_dmesg_output(fin_dmesg)
                self.output.final_dmesg = Dmesg.from_dmesg_output(fin_dmesg)

                if self.input_params.check_dmesg:
                    self.output.final_dmesg_check = self.check_dmesg_errors(
                        parsed_dmesg
                    )

        super().cleanup(**kwargs)

    @retry(3, 5)
    def get_host_dmesg(
        self, host=None, clear: bool = False
    ) -> t.Tuple[str, t.List[DmesgEntry]]:
        """
        Gets dmesg from the hosts.

        Params:
        host (Host) : The host to get the dmesg from.
        clear (bool, optional) : Clear the dmesg after retrieving.

        Returns:
        The dmesg logs.
        """

        host = self._default_host_if_none(host)

        output = host.run(Dmesg.dmesg_command(clear=clear))

        return output

    def check_dmesg_errors(self, dmesg: Dmesg) -> t.List[t.Tuple]:
        """
        Checks the dmesg for a particular set of errors.
        """
        checker = DmesgCheckComponent()
        return checker.check(dmesg, ts_only=False)

    @retry(3, 5)
    def get_smartlog(
        self,
        *,
        devname: str,
        host=None,
        raw: bool = False,
        ignore_status: bool = False,
        extended: bool = True,
    ) -> t.Optional[t.Union[str, SmartctlInfo]]:
        """
        Gets smartlog for a drive from a host.

        Params:
        host (Host) : The host to get the smartlog from.
        devname (str) : The devname for the drive to get the smartlog from.

        Return:
        The Smartlog output.
        """

        host = self._default_host_if_none(host)

        if extended:
            log = host.run_get_result(
                f"smartctl -x {devname}",
                ignore_status=ignore_status,
            )

        else:
            log = host.run(
                f"smartctl -i {devname}",
                ignore_status=ignore_status,
            )

        if raw:
            return log

        return SmartInfoFactory().create_smart_info(log.stdout)

    def operate_on_devnames(
        self,
        *,
        task: TestTask,
        host: t.Optional[Host] = None,
        devnames: t.List[str],
        max_workers: t.Optional[int] = None,
        submit_delay: float = 1.0,
        full_devname: bool = True,
    ):
        """ """
        if type(devnames) == str:
            processed_devnames = [
                self.format_devname(devnames, to_full_path=full_devname)
            ]
        else:
            processed_devnames = [
                self.format_devname(d, to_full_path=full_devname) for d in devnames
            ]
        return self.run_task_swept_kwargs(
            task=task,
            groups={"host": [host], "devname": processed_devnames},
            max_workers=max_workers,
            submit_delay=submit_delay,
        )

    def run_fio(
        self,
        *,
        devname: t.Optional[str],
        fio_params: FioJobInputParams,
        job_name: t.Optional[str] = None,
        additional_job_params: t.Optional[t.List[FioJobInputParams]] = None,
        host=None,
        bg: bool = False,
        return_fio_params: bool = False,
        ignore_status: bool = False,
        outfile: t.Optional[str] = None,
        timeout: int = 600,
    ):
        """
        Run Fio on a host on a device.
        """
        host = self._default_host_if_none(host)

        params = copy.deepcopy(fio_params)
        params.filename = devname
        params.name = job_name
        params.output_format = "json+"

        # Check timeout if it exists
        if params.runtime is not None:
            timeout += int(params.runtime)
        if params.ramp_time is not None:
            timeout += int(params.ramp_time)

        if additional_job_params is None:
            additional_job_params = []

        # Create the Fio Command
        cmd = FioJobInputParams.create_cmd_from_multiple(params, *additional_job_params)

        bg_str = " in the background." if bg else "."

        self.log_info(
            f"Running fio on {devname} on {host.hostname}{bg_str}"
            + f" Timeout of {timeout}. :: {cmd}."
        )

        if bg:
            outfile = outfile if outfile is not None else "/dev/null"
            run_data = self.remote_bg_execute(
                cmd, host=host, ignore_status=ignore_status, outfile=outfile
            )
        else:
            if outfile is not None:
                cmd = f"{cmd} > outfile"

            run_data = host.run(
                cmd,
                timeout=timeout,
                ignore_status=ignore_status,
            )

        if not return_fio_params:
            return run_data
        else:
            return (run_data, params)

    def precondition_multi_drives(
        self, host: Host, devnames: t.List[str], wl: FioJobInputParams
    ):
        """
        Preconditions a list of drives in parallel.
        """
        results = self.operate_on_devnames(
            task=TestTask(func=self.precondition_drive, kwargs={"wl": wl}),
            devnames=devnames,
            host=host,
        )

        return results

    def precondition_drive(self, *, host: Host, devname: str, wl: FioJobInputParams):
        """
        Preconditions a single drive.
        """
        self.log_info(f"Preconditioning drive {devname} on host {host.hostname}")
        self.run_fio(
            devname=devname,
            job_name=f"precondition_{self.format_devname(devname, to_full_path=False)}",
            fio_params=self.input_params.precondition_wl,
        )

    @staticmethod
    def format_devname(devname: str, to_full_path: bool = True):
        """
        Format the devname into one of two formats -- /dev/DEVICE or DEVICE. Converts
        between the two.

        Params:
            devname (str):
                The device name to format.
            to_full_path (bool, optional):
                Format to full /dev/DEVICE name. Otherwise, format to just DEVICE.

        Returns:
            (str) The formatted devname.
        """
        valid_devname_pattern = r"/?dev/[a-z0-9]+"
        dev_match = re.match(valid_devname_pattern, devname)

        if to_full_path:
            return devname if dev_match else f"/dev/{devname}"
        else:
            return (
                devname
                if not dev_match
                else devname[devname.find("dev/") + len("dev/") :]
            )

    ## Function for Entries ##
    def entry_get_drive(
        self,
        host: Host,
        devname: str,
        drives: pd.DataFrame,
        *,
        msgs: t.List[str],
        as_drive_obj: bool = True,
    ):
        matching_drives = drives[
            (drives.devname == devname) & (drives.hostname == host.hostname)
        ]
        drive = None
        if len(matching_drives) == 1:
            drive = matching_drives.iloc[0]
        else:
            err_str = f"Cannot find matching drive for devname {devname}!"
            msgs.append(err_str)
            self.log_warning(err_str)

        if as_drive_obj and drive is not None:
            return drive.drive_obj
        return drive

    def entry_get_smartlog(
        self, host: Host, devname: str, *, smartlog_type: str, msgs: t.List[str]
    ):
        """
        Function to help get smartlogs for an entry.
        """
        smartlog_val = ""

        if self.input_params.collect_smart:
            smartlog = self.get_smartlog(
                devname=devname,
                host=host,
                raw=True,
                ignore_status=True,
            )
        else:
            smartlog = None

        if smartlog is not None:
            self.log_info(f"Collected {smartlog_type} smartlog on {devname}")
            if smartlog.return_code != 0:
                smt_warning_str = (
                    f"The {smartlog_type} Smartlog had rc={smartlog.return_code}"
                )
                self.log_warning(smt_warning_str)
                msgs.append(smt_warning_str)
            smartlog_val = smartlog.stdout

        return smartlog_val

        """
        Method to MD Raid process
        """

    def delete_raid_array(self):
        """
        Method to delete MD Raid array
        """
        active_array = MDUtils.list_md_arrays(self.host)
        for array in active_array:
            ret = MDUtils.remove_md_array(self.host, array)
            self.validate_condition(ret, "Verify '%s' removal" % (array))
        for drive in self.test_drives:
            DiskUtils.remove_all_partitions(self.host, drive)

    def create_raid_array(self, raid_control):
        """
        Method to create MD Raid with values in control file
        """
        raid_to_drive_mapping = {}
        for raid in raid_control["raid_details"]:
            device = []
            if self.test_drives:
                if "number_of_device" in raid:
                    device = self.test_drives[: int(raid["number_of_device"])]
                    self.test_drives = [k for k in self.test_drives if k not in device]

                elif raid.get("devices", None) == ["ALL"]:
                    device = [str(i) for i in self.test_drives]

                elif "devices" in raid:
                    device = raid["devices"]
                else:
                    device = [str(i) for i in self.test_drives]

            self.validate_condition(device, "Verify that devices are available")

            raid["values"] = dict(sorted(raid["values"].items()))
            raid_device = MDUtils.create_md_array(self.host, raid["values"], device)

            self.validate_condition(raid_device, "Array '%s' created" % (raid_device))

            if "set_sync_action" in raid:
                MDUtils.set_md_sync_action(
                    self.host,
                    raid_device,
                    raid["set_sync_action"],
                    "raid%s" % raid["values"]["level"],
                )

            raid_to_drive_mapping[raid["values"]["create"]] = device
        return raid_to_drive_mapping

    def display_fiosynth_version(self):
        """
        Display the 'FioSynth Version' of the config.
        """
        cmd = "fiosynth -v"
        output = self.host.run(cmd)  # noqa
        return output

    def display_fio_version(self):
        """
        Display the 'Fio Version' of the config.
        """
        cmd = "fio -v"
        output = self.host.run(cmd)  # noqa
        return output

    @staticmethod
    def get_physical_block_size(host, device):
        """
        Method to get the physical block size of the drive
        Args:
            device: drive name
        Returns:
            physical block size
        """
        cmd = "cat /sys/block/%s/queue/physical_block_size" % device
        physical_block_size = host.run(cmd)
        return physical_block_size

    @staticmethod
    def override_kernel_parameters(
        host,
        drive_list,
        preferred_scheduler=None,
        io_timeout=None,
        discard_max_bytes=None,
        max_sectors_kb=None,
    ):
        ComponentTestBase.set_preferred_scheduler(host, drive_list, preferred_scheduler)
        ComponentTestBase.set_NVMe_io_timeout(host, drive_list, io_timeout)
        ComponentTestBase.set_discard_max_bytes(host, drive_list, discard_max_bytes)
        ComponentTestBase.set_max_sectors_kb(host, drive_list, max_sectors_kb)

    @staticmethod
    def get_preferred_scheduler(host, device):
        """
        Method to get the preferred scheduler of the drive
        Args:
            device: drive name
        Returns:
            preferred scheduler
        """
        cmd = "cat /sys/block/%s/queue/scheduler" % device
        preferred_scheduler = host.run(cmd)
        return preferred_scheduler

    @staticmethod
    def set_preferred_scheduler(host, device_list, scheduler_name):
        if scheduler_name is None or scheduler_name == "":
            return
        pref_scheduler_queue = []
        for device in device_list:
            pref_scheduler_queue.append(
                AutovalThread.start_autoval_thread(
                    ComponentTestBase.set_preferred_scheduler_drive,
                    host,
                    device,
                    scheduler_name,
                )
            )
        if len(pref_scheduler_queue):
            AutovalThread.wait_for_autoval_thread(pref_scheduler_queue)

    @staticmethod
    def set_preferred_scheduler_drive(host, device, scheduler_name):
        """
        Method to set preferred scheduler drive of the drive

        """

        cmd = "echo %s > /sys/block/%s/queue/scheduler" % (scheduler_name, device)
        preferred_scheduler = host.run(cmd)
        preferred_scheduler = ComponentTestBase.get_preferred_scheduler(host, device)
        preferred_scheduler = preferred_scheduler.split("[")[1].split("]")[0]
        AutovalUtils.validate_equal(
            scheduler_name,
            preferred_scheduler,
            "Successfully scheduler set to %s" % (scheduler_name),
        )

    @staticmethod
    def get_centos_release(host):
        cmd = "cat /etc/centos-release"
        output = host.run(cmd)  # noqa
        centos = re.search(r"release\s(\d+?\d*)", output)
        if centos:
            return centos.group(1)
        else:
            raise SystemInfoException("CMD: %s failed" % (cmd))

    @staticmethod
    def get_discard_max_bytes(host, device):
        """
        Method to get discard max bytes of the drive
        Args:
            device: drive name
        Returns:
            discard max bytes
        """
        cmd = "cat /sys/block/%s/queue/discard_max_bytes" % device
        discard_max_bytes = host.run(cmd)
        return discard_max_bytes

    @staticmethod
    def set_discard_max_bytes(host, device_list, discard_max_bytes):
        """
        Method to set discard max bytes of the drive
        """
        if discard_max_bytes is None or discard_max_bytes == "":
            return
        pref_discard_max_bytes_queue = []
        for device in device_list:
            pref_discard_max_bytes_queue.append(
                AutovalThread.start_autoval_thread(
                    ComponentTestBase.set_discard_max_bytes_drive,
                    host,
                    device,
                    discard_max_bytes,
                )
            )
        if len(pref_discard_max_bytes_queue):
            AutovalThread.wait_for_autoval_thread(pref_discard_max_bytes_queue)

    @staticmethod
    def set_discard_max_bytes_drive(host, device, discard_max_bytes):
        """
        Method to set discard max bytes of the drive
        """

        cmd = "echo %s > /sys/block/%s/queue/discard_max_bytes" % (
            discard_max_bytes,
            device,
        )
        new_discard_max_bytes = host.run(cmd)
        new_discard_max_bytes = ComponentTestBase.get_discard_max_bytes(host, device)
        AutovalUtils.validate_equal(
            discard_max_bytes,
            new_discard_max_bytes,
            "Successfully discard_max_bytes set to %s" % (discard_max_bytes),
        )

    @staticmethod
    def get_NVMe_io_timeout(host, device):
        """
        Method to get NVMe io timeout of the drive
        Args:
            device: drive name
        Returns:
            io timeout
        """
        cmd = "cat /sys/block/%s/queue/io_timeout" % device
        io_timeout = host.run(cmd)
        return io_timeout

    @staticmethod
    def set_NVMe_io_timeout(host, device_list, io_timeout):
        """
        Method to set NVMe io timeout of the drive
        """
        if io_timeout is None or io_timeout == "":
            return
        pref_io_timeout_queue = []
        for device in device_list:
            pref_io_timeout_queue.append(
                AutovalThread.start_autoval_thread(
                    ComponentTestBase.set_NVMe_io_timeout_drive,
                    host,
                    device,
                    io_timeout,
                )
            )
        if len(pref_io_timeout_queue):
            AutovalThread.wait_for_autoval_thread(pref_io_timeout_queue)

    @staticmethod
    def set_NVMe_io_timeout_drive(host, device, io_timeout):
        """
        Method to set NVMe io timeout of the drive
        """
        cmd = "echo %s > /sys/block/%s/queue/io_timeout" % (io_timeout, device)
        new_io_timeout = host.run(cmd)
        new_io_timeout = ComponentTestBase.get_NVMe_io_timeout(host, device)
        AutovalUtils.validate_equal(
            io_timeout,
            new_io_timeout,
            "Successfully io_timeout set to %s" % (io_timeout),
        )

    @staticmethod
    def get_max_sectors_kb(host, device):
        """
        Method to get max sectors kb of the drive
        Args:
            device: drive name
        Returns:
            max sectors kb
        """
        cmd = "cat /sys/block/%s/queue/max_sectors_kb" % device
        discard_max_bytes = host.run(cmd)
        return discard_max_bytes

    @staticmethod
    def set_max_sectors_kb(host, device_list, max_sectors_kb):
        """
        Method to set max sectors kb of the drive
        """
        if max_sectors_kb is None or max_sectors_kb == "":
            return
        pref_max_sectors_kb_queue = []
        for device in device_list:
            pref_max_sectors_kb_queue.append(
                AutovalThread.start_autoval_thread(
                    ComponentTestBase.set_max_sectors_kb_drive,
                    host,
                    device,
                    max_sectors_kb,
                )
            )
        if len(pref_max_sectors_kb_queue):
            AutovalThread.wait_for_autoval_thread(pref_max_sectors_kb_queue)

    @staticmethod
    def set_max_sectors_kb_drive(host, device, max_sectors_kb):
        """
        Method to set max sectors kbof the drive
        """
        cmd = "echo %s > /sys/block/%s/queue/max_sectors_kb" % (
            max_sectors_kb,
            device,
        )
        new_max_sectors_kb = host.run(cmd)
        new_max_sectors_kb = ComponentTestBase.get_max_sectors_kb(host, device)
        AutovalUtils.validate_equal(
            max_sectors_kb,
            new_max_sectors_kb,
            "Successfully max_sectors_kb set to %s" % (max_sectors_kb),
        )

    @staticmethod
    def get_fua(host, device):
        """
        Method to get fua of the drive
        Args:
            device: drive name
        Returns:
            fua
        """
        cmd = "cat /sys/block/%s/queue/fua" % device
        fua = host.run(cmd)
        return fua

    @staticmethod
    def set_fua(host, device_list, fua):
        """
        Method to set fua of the drive
        """
        if fua is None or fua == "":
            return
        pref_fua_queue = []
        for device in device_list:
            pref_fua_queue.append(
                AutovalThread.start_autoval_thread(
                    ComponentTestBase.set_fua_drive,
                    host,
                    device,
                    fua,
                )
            )
        if len(pref_fua_queue):
            AutovalThread.wait_for_autoval_thread(pref_fua_queue)

    @staticmethod
    def set_fua_drive(host, device, fua):
        """
        Method to set fau of the drive
        """
        cmd = "echo %s > /sys/block/%s/queue/fua" % (
            fua,
            device,
        )
        new_max_sectors_kb = host.run(cmd)
        new_max_sectors_kb = ComponentTestBase.get_max_sectors_kb(host, device)
        AutovalUtils.validate_equal(
            fua,
            new_max_sectors_kb,
            "Successfully FUA set to %s" % (fua),
        )

    @staticmethod
    def update_JSON_file(host, file_path, JSON_key_path, new_value):
        """
        Method to update the JSON parameters of Cachebench Config
        """
        cmd = "mJSON=$(cat %s | jq '%s = %s') && echo \"$mJSON\" > %s" % (
            file_path,
            JSON_key_path,
            new_value,
            file_path,
        )
        host.run(cmd)
        updated_JSON_value = ComponentTestBase.get_JSON_file_key(
            host, file_path, JSON_key_path
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

        cmd = "jq %s %s" % (JSON_key_path, file_path)
        return host.run(cmd)

    @staticmethod
    def power_state(host, test_drives, power_state_set_key):
        """
        Method to update the power state mode of the test drives
        """
        bootDrive = DiskUtils.get_boot_drive(host)
        for drive in test_drives:
            if str(drive) != bootDrive:
                drive_supported_power_modes = []
                cmd = f"nvme id-ctrl /dev/{drive}"
                out = host.run(cmd)
                for line in out.splitlines():
                    match = re.search(r"^ps\s+(\d+)\s+:\s+.*W\s+operational\s+.*", line)
                    if match:
                        drive_supported_power_modes.append(int(match.group(1)))

                if power_state_set_key != drive.get_power_mode():
                    npss = NVMeUtils.get_id_ctrl(host, drive.block_name)["npss"]

                    if npss >= 8:
                        if power_state_set_key in drive_supported_power_modes:
                            set_state = drive.set_power_mode(power_state_set_key)
                            get_state = drive.get_power_mode()
                            AutovalUtils.validate_equal(
                                set_state,
                                get_state,
                                f"Current power-mode has set to ps: {power_state_set_key} on /dev/{drive}",
                            )
                    elif npss < 8:
                        AutovalLog.log_info(
                            f"supported power modes on /dev/{drive} are: {drive_supported_power_modes} and it does not support power state ps: {power_state_set_key}"
                        )

                elif power_state_set_key == drive.get_power_mode():
                    AutovalLog.log_info(
                        f"/dev/{drive} has already set to power state ps: {power_state_set_key}"
                    )

    @staticmethod
    def drives_executable(test_drives, w_config):
        """
        Method to filter the required test drives from the host
        """

        test_devices = []
        try:
            if w_config["perform_raid"]:
                if w_config["raid_details"][0]["devices"] == ["ALL"]:
                    devices = test_drives
                else:
                    devices = w_config["raid_details"][0].get("devices", None)

            elif "devices" not in w_config:
                if w_config["workload_suites"][0]["parameters_override"][
                    "cache_config.writeAmpDeviceList"
                ]:
                    devices = w_config["workload_suites"][0]["parameters_override"].get(
                        "cache_config.writeAmpDeviceList", None
                    )
            if devices is not None:
                for device_name in devices:
                    for drive in test_drives:
                        if str(drive) == str(device_name):
                            test_devices.append(drive)
            else:
                test_devices = test_drives

        except Exception:
            if w_config["devices"] == ["ALL"]:
                test_devices = test_drives

            else:
                devices = w_config["devices"]
                for device in devices:
                    device = os.path.split(device)[-1]
                    for drive in test_drives:
                        if str(drive) == device:
                            test_devices.append(drive)

        return test_devices


class SmartctlLogParser:
    @staticmethod
    def remove_empty_string(list_data):
        while "" in list_data:
            list_data.remove("")
        return list_data

    @staticmethod
    def create_pairs(junk_data, out_dict):
        for elem in junk_data:
            if ":" in elem:
                key, value = elem.split(":")[0].strip(), elem.split(":")[1].strip()
                out_dict[key] = value
        return out_dict

    @staticmethod
    def clean_data(data_to_clean):
        """
        Clean data from Error Information, SMART/Health Information, START OF SMART DATA SECTION, Supported LBA Sizes,
        Supported Power States

        :param data_toClean: raw data from initial_smartctl & final_smartctl
        :return: dict
        """

        """ Error Information """
        error_info = data_to_clean.split("Error Information (NVMe Log")
        if (
            "No Errors Logged" not in error_info[1]
            and len(error_info[1].split("\n")) > 1
        ):
            trimmed_error_info = [
                info.strip() for info in error_info[1].split("\n")[1:-3]
            ]
            temp_errors = []
            for row_data in trimmed_error_info:
                temp_errors.append(
                    SmartctlLogParser.remove_empty_string(row_data.split(" "))
                )

            df = pd.DataFrame(temp_errors[1:], columns=temp_errors[0])
            error_info_out = json.loads(df.to_json(index=False, orient="table"))["data"]

        else:
            error_info_out = {}

        """ SMART/Health Information """
        health_info = error_info[0].split("SMART/Health Information (NVMe Log 0x02)")
        trimmed_health_info = [
            info.strip() for info in health_info[1].split("\n")[1:-2]
        ]
        health_info_out = SmartctlLogParser.create_pairs(
            junk_data=trimmed_health_info, out_dict={}
        )

        """ START OF SMART DATA SECTION """
        smart_section = health_info[0].split("=== START OF SMART DATA SECTION ===")
        trimmed_smart_section = [
            info.strip() for info in smart_section[1].split("\n")[1:-2]
        ]
        smart_section_out = SmartctlLogParser.create_pairs(
            junk_data=trimmed_smart_section, out_dict={}
        )

        """ For Supported Power States """
        support_LBA = smart_section[0].split("Supported LBA Sizes")
        trimmed_support_LBA = [
            info.strip() for info in support_LBA[1].split("\n")[1:-2]
        ]
        temp_support_LBA = []

        for row_data in trimmed_support_LBA:
            temp_support_LBA.append(
                SmartctlLogParser.remove_empty_string(row_data.split(" "))
            )

        df1 = pd.DataFrame(temp_support_LBA[1:], columns=temp_support_LBA[0])
        support_LBA_out = json.loads(df1.to_json(index=False, orient="table"))["data"]

        """ Supported LBA Sizes """
        support_power = support_LBA[0].split("Supported Power States")
        trimmed_support_power = [
            info.strip() for info in support_power[1].split("\n")[1:-2]
        ]
        temp_support_power = []

        for row_data in trimmed_support_power:
            temp_support_power.append(
                SmartctlLogParser.remove_empty_string(row_data.split(" "))
            )

        df2 = pd.DataFrame(temp_support_power[1:], columns=temp_support_power[0])
        support_power_out = json.loads(df2.to_json(index=False, orient="table"))["data"]

        """ START OF INFORMATION SECTION """
        start_info = support_power[0].split("=== START OF INFORMATION SECTION ===")
        trimmed_smart_info = [info.strip() for info in start_info[1].split("\n")[1:-2]]
        start_info_out = SmartctlLogParser.create_pairs(
            junk_data=trimmed_smart_info, out_dict={}
        )

        return {
            "START OF INFORMATION SECTION": start_info_out,
            "Supported Power States": support_power_out,
            "Supported LBA Sizes": support_LBA_out,
            "START OF SMART DATA SECTION": smart_section_out,
            "SMART/Health Information": health_info_out,
            "Error Information": error_info_out,
        }
