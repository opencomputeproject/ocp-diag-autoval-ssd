#!/usr/bin/env python3

# pyre-unsafe
import datetime
import os
import re
from collections import defaultdict
from typing import Dict, List, TYPE_CHECKING

from autoval.lib.host.component.component import COMPONENT

from autoval.lib.utils.async_utils import AsyncJob, AsyncUtils
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.file_actions import FileActions
from autoval.lib.utils.site_utils import SiteUtils
from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.md_utils import MDUtils
from autoval_ssd.lib.utils.storage.storage_device_factory import StorageDeviceFactory

if TYPE_CHECKING:
    from autoval_ssd.lib.utils.storage.drive import Drive  # noqa


class StorageUtils:
    @staticmethod
    def get_test_drives(
        host,
        drive_type=None,
        drive_interface=None,
        drives=None,
    ) -> Dict:
        """
        Port from autotest of StorageUtils.get_test_drives()

        Get drives for test based on the input
        @param
        drive_type - hdd, ssd, md
        host - host object
        drive_type=None, drive_interface=None - return all drives
        drive_interface - nvme, sas, sata
        drives - List[str] - Allows user to specify drive devices.  If none are
                             specified or found, method returns empty dictionary.
        return - dict of device_block:device_obj
        """

        test_drives = {}

        if drive_type == "md":
            drives = MDUtils.list_md_arrays(host)
            test_drives = dict(zip(drives, drives))
            return test_drives

        if not drives:
            # If list of drives has not been specified, ALL drives will be processed
            drives = DiskUtils.get_storage_devices(host, drive_type=drive_type)
            if not drives:
                return test_drives

        drive_objs = StorageDeviceFactory(host, drives).create()

        for drive in drive_objs:
            if drive_type:
                type_match = drive.get_type().value == drive_type
            else:
                type_match = True
            if drive_interface:
                # pyre-fixme[16]: `Drive` has no attribute `interface`.
                interface_match = drive.interface.value == drive_interface
            else:
                interface_match = True

            if type_match and interface_match:
                test_drives[drive.block_name] = drive

        return test_drives

    @staticmethod
    def save_drive_logs(
        host, log_dir, block_names=None, drive_dict=None, drive_list=None
    ) -> None:
        """
        Port from autotest of StorageUtils.save_drive_logs()

        Stores drive logs in <drive_serial.json>

        Parameters
        ----------

        host: Autoval 'Host' object of target DUT
        block_names: List[str] - User can optionally send names of desired
                                 block devices on DUT
        drive_dict: Dict[str:Drive] - User can optionally send a dict of existing
                              'Drive' objects instead of strs. If used, call to
                              StorageDeviceFactory will be skipped.
        drive_list: List[Drive] - User can aoptionally send a list of existing
                              'Drive' objects instead of strs. If used, call to
                              StorageDeviceFactory will be skipped.

        Note: If valid drive parameter is NOT included, test error will be raised
        """
        drive_objs = []

        if block_names:
            drive_objs = StorageDeviceFactory(host, block_names).create()
        elif drive_dict:
            drive_objs = [drive_dict[thing] for thing in drive_dict]
        elif drive_list:
            drive_objs = drive_list
        else:
            raise TestError(
                "Valid drive parameter not included. Please provide block names, \
                drive dict, or drive list. "
            )
            return

        StorageUtils.save_drive_logs_async(host, drive_objs, log_dir)

    @staticmethod
    def save_drive_logs_async(host, drives, log_dir) -> None:
        """
        Uses AsyncUtils to dump multiple drives data as JSON in <log_dir>

        Parameter
        ---------
        host:   Autoval 'Host' object for target DUT
        drives:  List of 'Drive' objects whose data is to be written to JSON
        log_dir: Path to desired log storage location
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        drives_args = [(drive, timestamp, log_dir) for drive in drives]

        AsyncUtils.run_async_jobs(
            [
                AsyncJob(func=StorageUtils.save_single_drive_log, args=[this_drive])
                for this_drive in drives_args
            ]
        )

    @staticmethod
    def save_single_drive_log(drive_args) -> None:
        """
        Dumps drive data (for a single drive) as JSON at specified location

        Parameter
        ---------

        drive_args: Tuple(Drive,str,str)
            drive_args[0]: Drive - Autoval 'Drive' object
            drive_args[1]: str - timestamp
            drive_args[2]: str - path to log file storage location
        """
        if len(drive_args) < 3:
            raise TestError(
                "Drive logging requires Tuple(Drive,timestamp,path). Provided \
                Tuple contains less than 3 values."
            )
            return

        drive = drive_args[0]
        timestamp = drive_args[1]
        log_dir = drive_args[2]

        serial_number = drive.serial_number
        file_name = "{}.json".format(serial_number)
        FileActions.mkdirs(os.path.join(log_dir, timestamp))
        file_path = os.path.join(log_dir, timestamp, file_name)
        FileActions.write_data(file_path, drive.collect_data(), append=False)

    @staticmethod
    def print_drive_summary(drives: List["Drive"]) -> None:
        grouped_drive_attr = {
            "manufacturer": {
                # e.g. fill-in
                # "SEAGATE": ["sdb", "sdc", ...],
            },
            "model": {},
            "type": {},
            "interface": {},
        }
        for attr in grouped_drive_attr.keys():
            grouped_drive_attr[attr].update(
                StorageUtils.group_drive_by_attr(attr, drives)
            )
        grouped_drive_attr["firmware_version"] = StorageUtils.group_drive_by_firmware(
            drives
        )
        for attr, _dict in grouped_drive_attr.items():
            if attr:
                attr = attr[0].upper() + attr[1:]  # upper case first char
                AutovalLog.log_info(attr)

                for attr_val, drive_list in _dict.items():
                    drive_list = ", ".join(drive_list)
                    AutovalLog.log_info(f"\t{attr_val}: {drive_list}")

    @staticmethod
    def group_drive_by_attr(attr: str, drives: List["Drive"]) -> Dict[str, List[str]]:
        """e.g. Return {"SEAGATE": ['sdb', 'sdc', ...], ...}"""
        grouped = defaultdict(list)
        for drive in drives:
            grouped[getattr(drive, attr, "Unknown")].append(
                getattr(drive, "block_name", "Unknown")
            )
        return grouped

    @staticmethod
    def group_drive_by_firmware(drives: List["Drive"]) -> Dict[str, List[str]]:
        """e.g. Return {"K001": ['sdb', 'sdc', ...], ...}"""
        grouped = defaultdict(list)
        firmware_list = AsyncUtils.run_async_jobs(
            [AsyncJob(func=drive.get_firmware_version) for drive in drives]
        )
        fw_map = zip([drive.block_name for drive in drives], firmware_list)
        for block_name, fw in fw_map:
            grouped[fw].append(block_name)
        return grouped

    @staticmethod
    def format_all_drives(drives: List["Drive"], secure_erase_option: int = 0) -> None:
        """Format All Drives.
        This method format the drives as a pre-requisite.
        Parameters
        ----------
        drives::obj: Drive
        Drives objects of class StorageTestBase.
        """
        AsyncUtils.run_async_jobs(
            [
                AsyncJob(func=StorageUtils._format, args=[drive, secure_erase_option])
                for drive in drives
            ]
        )

    @staticmethod
    def _format(drive, secure_erase_option: int = 0) -> None:
        """Helper function to format specific drive in thread"""
        drive.format_drive(secure_erase_option=secure_erase_option)  # noqa

    @staticmethod
    def get_all_drives_temperature(drives: List["Drive"]) -> Dict[str, int]:
        """All Drives Sensor Temperature values.

        This method collect the sensor temperature data of all drives.

        Returns
        -------
        drives_temperature_value : Dictionary
            Temperature value of all drives.
        """
        drives_temperature_value = {}
        for drive in drives:
            sensor_temp = drive.get_drive_temperature()
            drives_temperature_value[drive.block_name] = sensor_temp
        return drives_temperature_value

    @staticmethod
    def change_nvme_io_timeout(host, test_phase: str, new_timeout: int) -> None:
        """Change NVME io_timeout file value to new_timeout

        NVME io_timeout file(File PATH : /sys/module/nvme_core/parameters/io_timeout) controls after how many seconds all NVME related commands will timeout.
        Example : If timeout value is 3 seconds and if NVME command takes more than 3 second to give output , the NVME command will automatically be timed out.
        Implementing this code as part of requirement in the latest boot SSD spec.

        Args:
            host: Host object. Used to run commands on DUT.
            test_phase: String. When changing NVME io_timeout we usually do it on setup() or cleanup() phase of HAVOC test. To mention in which phase we are currently now in use this argument.
            new_timeout: Integer. The value to which we'll change the NVME io_timeout to.

        Returns:
            return1: None. This function returns nothing , All code flow is implemented as part of function.

        Raises:
            Exception1: If there's any issue on NVME io_timeout file change to new value this exception will be triggered
        """
        # NVME IO command timeout value check
        nvme_io_timeout_file_absolute_path = (
            "/sys/module/nvme_core/parameters/io_timeout"
        )
        file_value_change_command = (
            f"echo {new_timeout} > {nvme_io_timeout_file_absolute_path}"
        )

        try:
            # Checking if file exists before trying to open it
            if FileActions.exists(nvme_io_timeout_file_absolute_path):
                # Change file value if file already exist
                host.run(file_value_change_command, sudo=True)
            else:
                # If file does not exist , Creating file
                AutovalLog.log_debug(
                    f"{nvme_io_timeout_file_absolute_path} NVME io_timeout file does not exist in DUT , Creating file"
                )
                host.run(file_value_change_command, sudo=True)

        except Exception as exe:
            AutovalLog.log_debug(
                f"This error occured while trying to change NVME io_timeout value at {nvme_io_timeout_file_absolute_path} : {str(exe)}"
            )

        finally:
            AutovalUtils.validate_equal(
                host.run(f"cat {nvme_io_timeout_file_absolute_path}"),
                str(new_timeout),
                f" In {test_phase} phase - Validate NVME IO timeout value",
                component=COMPONENT.SSD,
                error_type=ErrorType.DRIVE_ERR,
            )

    @staticmethod
    def validate_persistent_event_log_support(host, drive: str) -> None:
        """This function is to check if the SSD drive supports the persistent
        event log types as per OCP specification.
        This feature is only for boot drive.

        Args:
            drive: The name of the drive Ex: nvme1n1
        """
        cmd = "nvme get-log -i 0xd --lpo=480 --lsp=0 -l 32 /dev/%s" % drive
        out = host.run(cmd)
        data_out = re.search(r"0000:\s+(\w+\s+\w+)", out)
        # pyre-ignore
        event_log_data = data_out.group(1).split(" ")
        event_log_data = event_log_data[::-1]
        seq_log_data = "".join(event_log_data)
        # Only the 14 bits are needed, so taking only the 14 bits
        binary_val = format(int(seq_log_data, base=16), "014b")
        AutovalLog.log_info(f"The persistent event log bit data is {binary_val}")
        events_dic = {}
        supported_event_list = [
            "Thermal Excursion Event Support",
            "Telemetary Log Create Event Support",
            "Set Feature Event Support",
            "Sanitize Completion Event Support",
            "Sanitize Start Event Support",
            "Format NVM Completion Event Support",
            "Format NVM Start Event Support",
            "Change Namespace Event Support",
            "NVM Subsystem Hardware Error Event Support",
            "Power-on or Reset Event Supported",
            "Timestamp Change Event Supported",
            "Firmware Commit Event Supported",
            "SMART/Health Log Snapshot Event Supported",
            "Reserved",
        ]
        for value, event in zip(binary_val, supported_event_list):
            events_dic[event] = int(value)
        not_supported_event = []
        for event, value in events_dic.items():
            if int(value) == 0 and event != "Reserved":
                not_supported_event.append(event)
        AutovalLog.log_info(f"Persistent Event Log type values {events_dic}")
        AutovalUtils.validate_equal(
            len(not_supported_event),
            0,
            f"Not supported Persistent Event log type list is {not_supported_event}",
            component=COMPONENT.SSD,
            error_type=ErrorType.DRIVE_ERR,
        )

    @staticmethod
    def prepare_hdd_log_collection(
        host, drive_vendor: str, block_name: str, vslot_no: int, drive_serial_no: str
    ):
        AutovalLog.log_info(
            f"Start collecting vendor logs for drive {drive_vendor} with serial {drive_serial_no}."
        )
        tmpdir = SiteUtils.get_dut_tmpdir(host.hostname)
        out = host.run("ls -1 %s | wc -l " % tmpdir)
        if int(out) == 0:
            log_tarball_path = host.deploy_tool(
                f"{drive_vendor}_log_collection_util.tgz"
            )
            AutovalUtils.run_remote_module(
                module="autoval.lib.utils.generic_utils",
                method="extract",
                class_name="GenericUtils",
                host=host,
                params=[log_tarball_path, tmpdir],  # noqa
            )
        append_to_dir_name = block_name + "_" + drive_serial_no + "_" + str(vslot_no)
        tmpdir_system_log = tmpdir + "/" + append_to_dir_name
        tmp_dir_path_system_log = FileActions.mkdirs(tmpdir_system_log, host)
        AutovalLog.log_info("Starting to run the vendor script to collect logs")
        return tmpdir, tmp_dir_path_system_log

    @staticmethod
    def find_interface_type(host, block_name: str) -> str:
        """This function is used to check if the drive is SATA or SAS type

        Args:
            block_name: Name of the block device

        Returns:
            Will return the type of the interface.
        """
        device_factory_obj = StorageDeviceFactory(host, [block_name])
        is_sas = device_factory_obj._is_drive_sas(block_name)  # noqa
        device_factory_obj._cache_sata_drives_name()
        is_sata = device_factory_obj._is_drive_sata(block_name)
        return "SATA" if is_sata else "SAS"

    @staticmethod
    def get_hdd_vendor_name(host, blockname: str) -> str:
        """This function will return the drive vendor name"""
        cmd = "smartctl -x /dev/%s | grep -i 'Device Model'" % blockname
        out = host.run(cmd=cmd)
        vendor_name = out.split(":")
        vendor_name = vendor_name[1].strip()
        return vendor_name
