#!/usr/bin/env python3

# pyre-unsafe
"""Base class for testing drives"""
import datetime
import os
import re
import time
from typing import Dict, List, Optional, Tuple, Union

import autoval_ssd.lib.utils.storage.smart_validator as smart_validator
from autoval.lib.host.component.component import COMPONENT
from autoval.lib.test_base import TestBase

from autoval.lib.utils.async_utils import AsyncJob, AsyncUtils
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.file_actions import FileActions
from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.filesystem_utils import FilesystemUtils
from autoval_ssd.lib.utils.md_utils import MDUtils
from autoval_ssd.lib.utils.storage.drive import Drive, DriveInterface, DriveType
from autoval_ssd.lib.utils.storage.storage_device_factory import StorageDeviceFactory
from autoval_ssd.lib.utils.storage.storage_utils import StorageUtils
from autoval_ssd.lib.utils.system_utils import SystemUtils

TOOLS = [
    "smartmontools",
    "hdparm",
    "sdparm",
    "fio",
    "fio-engine-libaio",
    "sg3_utils",
    "sshpass",
]

SMART_LOGS = ["smart-log", "vs-smart-add-log", "vs-nand-stats", "ocp-smart-add-log"]


class StorageTestBase(TestBase):
    """
    Base class for testing drives.
        - Create drive objects
        - Compare and validate drive metrics at the end of the test

        Test control params:
            Union(String [], Drive Object []) drives: list of drives to test: e.g. sdac, sdf,
            String drive_type: hdd, ssd, etc.
            String drive_interface: filter for drives with this interface
                to test
            String drive_model: test drives with this given model
            String drive_count: if provided, will validate if the number
                of test drives equal this value
            String drive_config: json file that controls how drive data is
                collected and validated
            String validate_firmware: if provided, will check if test drives'
                firmware matches this valueValueError
            Boolean remove_partition: Set to false to not delete the
                existing RAID and Partitions before running the actual test.
            Boolean format_partition: if set to 'true', format drives using
                nvme format to wipe out partition. On few Hi5 systems, 'parted'
                required a reboot to remove partition, so using nvme-cli instead.
            Boolean check_not_empty_test_drives: if set 'false' from control file,
                test will not validate non empty drive list.
            Boolean test_drive_filter: default True. If set to false, use
                all drives in self.drives for testing and skip drive filtering
            Optional Boolean enable_cache: if true will turn on write cache,
                if False will turn write cache off for all test drives. Otherwise
                it will be None write_cache will be left intact
            Boolean include_boot_drive: if True, will include boot drive to
                the list of test drives
                Default is False
            Boolean only_boot_drive: if True, will run test only on boot drive
                Default is False
            String boot_drive_physical_location: if provided, will use this location
                to find out the boot drive.
                Format:  <PCI domain>:<bus>:<device>.<function>
                Example: 0000:64:00.0
            Boolean unmount_before_test: If True and boot_drive is also True, will
                perform unmount on all data drives or given parameter of test
                drives.
    """

    # @override
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.drive_data = {
            "before_test": {
                # str serial_no: Dict {} of drive_data
            },
            "after_test": {},
        }
        self.drive_list = []
        self.drives = []
        self.test_drives = []
        self.device_names = []
        self.expander_info = {}
        self.storage_test_tools = TOOLS
        self.boot_drive: str = ""
        self.drive_config: str = self.test_control.get("drive_config_file", None)
        self.test_drive_filter = self.test_control.get("test_drive_filter", True)
        self.enable_cache = self.test_control.get("enable_cache", False)
        self.remove_mount_before_test = self.test_control.get(
            "unmount_before_test", True
        )
        self.collect_drive_data = self.test_control.get("collect_drive_data", True)
        self.boot_drive_physical_location = self.test_control.get(
            "boot_drive_physical_location", ""
        )
        self.smart_log_dir = ""
        self.disable_tools_upgrade = self.test_control.get(
            "disable_tools_upgrade", None
        )

        # self.test_control["drives"] is meant to be used filter the drives under test in setup
        # However a number of modules use it to pass drive objects to fio_runner.
        # Thus, pending code cleanup, a copy of the original drives list is required
        self.original_test_control_drives = self.test_control.get("drives", [])
        self.nvme_version = self.test_control.get(
            "nvme_version", "nvme-cli-1.11.2-1.fb20"
        )
        self.storage_test_tools.append(self.nvme_version)

    # @override
    def setup(self, *args, **kwargs) -> None:
        super().setup(*args, **kwargs)
        self.storage_test_setup()
        self.host.run("rm -f /root/havoc_fio_file", ignore_status=True)
        AutovalLog.log_debug("lsblk Output: %s" % self.host.run(cmd="lsblk"))
        AutovalLog.log_debug("NVMe List Output: %s" % self.host.run(cmd="nvme list"))

    def storage_test_setup(self) -> None:
        """Setup storage"""
        self._install_required_packages()
        self.smart_log_dir = os.path.join(self.resultsdir, "SMART")
        FileActions.mkdirs(self.smart_log_dir)
        self.boot_drive = self.get_boot_device()
        self.drive_list = self.get_drive_list(self.boot_drive)
        self.expander_info = self.host.get_expander()
        self.drives = self.scan_drives()
        AutovalLog.log_info("Drive info summary:")
        StorageUtils.print_drive_summary(self.drives)
        AutovalLog.log_info("Fetching test drives.")
        if self.test_drive_filter:
            self.test_drives = self.get_test_drives_from_drives(
                drive_type=self.test_control.get("drive_type", None),
                interface=self.test_control.get("drive_interface", None),
                model=self.test_control.get("drive_model", None),
                only_boot_drive=self.test_control.get("only_boot_drive", False),
                include_boot_drive=self.test_control.get("include_boot_drive", False),
            )
        else:
            self.test_drives = self.drives
        # partitioned_drives will return the list of drive namespaces with partition other than boot partition
        partitioned_drives = DiskUtils.get_partitions_and_mount_points_in_drive(
            self.host
        )
        part_drive_list = [
            key
            for key, value in partitioned_drives.items()
            if any(
                "children" in item
                and any(
                    partition == "/"
                    for partition in item["children"][0].get(
                        "mountpoints", "mountpoint"
                    )
                )
                for item in value
            )
        ]

        self.test_drives = [
            drive
            for drive in self.test_drives
            if drive.block_name not in part_drive_list
        ]
        AutovalLog.log_info(
            "Available drives: %s, Drives under test: %s"
            % (self.drives, self.test_drives)
        )

        if self.remove_mount_before_test and not self.test_control.get(
            "only_boot_drive"
        ):
            self.unmount_before_test(
                [d for d in self.drives if str(d) != self.boot_drive]
            )
        else:
            AutovalLog.log_info("++Skipping umounting before test")
        self._validate_write_cache()
        # pre-check to validate for the presence of degraded drives
        self.validate_degraded_drives_presence()
        if self.collect_drive_data:
            AutovalLog.log_info("Collecting drive data.")
            self.drive_data["before_test"] = self._collect_drive_data()
        else:
            AutovalLog.log_info("Skipping drive data collection")
        self._validate_non_empty_test_drive_list()
        self._validate_test_drives_firmware()
        self.validate_drive_health_check()
        self.validate_drive_erase_count()
        if self.test_control.get("remove_partition", True):
            AutovalLog.log_info("umount and remove raid devices")
            self._umount_and_remove_raid_devices()
            AutovalLog.log_info("Removing drive's partitions")
            self._remove_partitions()
        self._validate_hdd_drive_count(skip_power_reset=True)
        self._validate_lsblk_info(start=True)
        self._validate_data_drive_state()
        self._validate_cryptoerase_support()

    def get_boot_device(self) -> str:
        """
        This function returns the boot device
        """
        if self.boot_drive_physical_location:
            boot_device: str = DiskUtils.get_block_from_physical_location(
                self.host,
                [self.boot_drive_physical_location],
                DiskUtils.get_block_devices_info(self.host),
            )
        else:
            boot_device: str = DiskUtils.get_boot_drive(self.host)
        return boot_device

    def get_drive_list(self, boot_drive: str) -> List[str]:
        """
        This function returns the drive list
        """
        if self.original_test_control_drives:
            drive_list = self.original_test_control_drives
        else:
           drive_list = DiskUtils.get_block_devices(
                self.host,
                boot_drive_physical_location=self.boot_drive_physical_location,
            )

        if boot_drive != "" and boot_drive != "rootfs":
            drive_list.append(boot_drive)
        else:
            AutovalLog.log_info(
                "Warning - No boot drive found, check " "the test environment"
            )
        return list((set(drive_list)))

    def _validate_data_drive_state(self):
        """
        This function will check if SSD data drive is in normal state
        or abnormal state. Will not check the SSD boot drive.
        """
        try:
            self.host.oob.check_ssd_drive_health()
        except AttributeError:
            AutovalLog.log_info("Skipping BMC-based SSD drive health checking")

    def check_block_devices_available(self) -> None:
        """
        Check devices against initial list to identify the drive assertion
        and more drive related issues.
        """
        boot_drive = self.get_boot_device()
        available_drives = self.get_drive_list(boot_drive)
        expected_drives = self.drive_list
        if (
            sorted(available_drives) != sorted(expected_drives)
            and not self.is_ssd_specific_test()
        ):
            AutovalLog.log_info(
                f"Warning: Drive names have changed due to a reboot. Available drives {str(available_drives)} do not match expected drives {str(expected_drives)}"
            )
        else:
            AutovalUtils.validate_equal(
                sorted(available_drives),
                sorted(expected_drives),
                "Check available drives against initial list.",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

    def _install_required_packages(self) -> None:

        SystemUtils.install_rpms(
            self.host,
            self.storage_test_tools,
            disable_tools_upgrade=self.disable_tools_upgrade,
            force_install=True,
        )

    def _validate_write_cache(self) -> None:
        """
        This function validates the write cache setting for all drives in the test.
        It first checks if the write cache should be enabled or disabled based
        on the `enable_cache` attribute.
        For each drive, it gets the current write cache setting and
        compares it to the expected value.
        """
        expected = 0
        if self.enable_cache:
            expected = 1
            AutovalLog.log_info("Enabling write_cache")
        else:
            AutovalLog.log_info("Disabling write_cache")
        for drive in self.test_drives:
            if self.enable_cache:
                drive.enable_write_cache()
            else:
                drive.disable_write_cache()
        AutovalLog.log_info("Validating write_cache")
        for drive in self.test_drives:
            cache = drive.get_write_cache()
            if cache is not None:
                warning = False
                if str(drive) == str(self.boot_drive):
                    AutovalLog.log_info(
                        "Write_cache disabling may not supported on boot drive"
                    )
                    warning = True
                AutovalUtils.validate_equal(
                    cache,
                    expected,
                    "The drive %s write_cache validation" % drive.block_name,
                    log_on_pass=False,
                    warning=warning,
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.NVME_ERR,
                )
            else:
                AutovalLog.log_info(
                    "The drive %s not supported write_cache" % drive.block_name
                )

    def _validate_non_empty_test_drive_list(self) -> None:
        """
        This function validates that the test drives list is not empty.
        If the list is empty, an error will be raised.
        """
        if self.test_control.get("check_not_empty_test_drives", True):
            self.validate_non_empty_list(
                self.test_drives,
                "Test drives list is not empty",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

    def _validate_lsblk_info(self, start: bool = False) -> None:
        """
        Validates device names didn't change during the test.
        This method performs the 'lsblk' check for storage platforms and
        ensures that storage block device names match.
        """
        # Grab the raw output of name column with no header and sort it.
        output = self.host.run("lsblk -rno NAME -x NAME")
        device_names = sorted(output.splitlines())
        if start:
            self.device_names = device_names
        else:
            AutovalUtils.validate_equal(
                device_names,
                self.device_names,
                "Asserting device names match",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.STORAGE_DRIVE_DEVICE_NAMES_CHANGED_ERR,
            )

    def _validate_hdd_drive_count(self, skip_power_reset: bool = False) -> None:
        """
        This function is used to validate the the number of HDD's on the server.
        Also validate that the number of drives in testing matches
        the number of drives specified in the test control params.
        This check will be skipped if the test is SSD specific.

        """
        if self.is_ssd_specific_test():
            return

    def is_ssd_specific_test(self) -> bool:
        """
        This function checks if the test is specific to SSD drives or not.
        Also checks if the boot drive is SSD or not.

        Returns:
            bool: True if the test is specific to SSD drives, False otherwise.
        """
        return self.test_control.get(
            "drive_type", None
        ) == "ssd" or self.test_control.get("boot_drive", False)

    def _validate_test_drives_firmware(self) -> None:
        """This function validates the firmware of the drives under test."""
        if "validate_firmware" in self.test_control:
            _fw = self.test_control.get("validate_firmware")
            for drive in self.test_drives:
                AutovalUtils.validate_equal(
                    drive.get_firmware_version().upper(),
                    _fw.upper(),
                    f"{drive.block_name} firmware is {_fw}",
                    log_on_pass=False,
                )
            AutovalUtils.validate_condition(True, f"Test drives firmware is {_fw}.")

    def validate_drive_health_check(self) -> None:
        """
        This function checks if the drive under test has fatal error support
        and Critical warnings
        """
        for drive in self.test_drives:
            # The support for drive health check is implemented only for nvme drive
            # TODO: Support for SAS and SATA will be added later
            if DriveInterface.NVME == drive.interface:
                drive.drive_health_check()

    def validate_drive_erase_count(self) -> None:
        """
        This function calculates the diffence between the minimum erase count and
        maximum erase count.
        If the delta value is greater than 200, then raise the test error.
        """
        for drive in self.test_drives:
            # The support for validate erase count is implemented only for nvme drive
            # TODO: Support for SAS and SATA will be added later
            if DriveInterface.NVME == drive.interface:
                drive.drive_erase_count()

    def _umount_and_remove_raid_devices(self) -> None:
        """This function removes all the raid devices and unmounts all the drives."""
        raids = MDUtils.list_md_arrays(self.host)
        for raid_dev in list(raids.keys()):
            mnt_point = MDUtils.get_md_mount_point(self.host, raid_dev)
            if mnt_point:
                DiskUtils.umount(self.host, mnt_point)
            MDUtils.remove_md_array(self.host, raid_dev)

    def _remove_partitions(self) -> None:
        """
        Remove all partitions and unmount all drives, except for boot drive.
        Running fio on a raw device would fail if attempted on an
        already mounted device. Unmount the filesystem
        before starting the tests.
        If partitions still exist then format drives  only if "format partition"
        flag is set to True.
        """
        self.host.run("partprobe -s", ignore_status=True)
        time.sleep(5)  # wait for partitions to refresh
        AsyncUtils.run_async_jobs(
            [
                AsyncJob(
                    func=drive.remove_all_partitions,
                    kwargs={"refresh_partitions": False},
                )
                for drive in self.test_drives
                if drive.block_name != self.boot_drive
            ]
        )
        if self.test_control.get("format_partition", False):
            self._format_drives()

    def _format_drives(self) -> None:
        """
        Check if partitions still exists on even after using parted utility,
        and if partitions still exists, then format drive.
        """
        for drive in self.test_drives:
            partitions = DiskUtils.get_drive_partitions(
                self.host, drive.block_name, refresh_partitions=False
            )
            if partitions:
                drive.format_drive()

    def scan_drives(self) -> List:
        """
        Scan all drives and returns list of drive objects from StorageDeviceFactory
        If drive_config_file is specified in control, it will apply to all drives
        If sata_drive_config_file is specified in control, it will apply to SATA drives only
        """
        sata_drive_config = self.test_control.get("sata_drive_config_file", None)
        if sata_drive_config:
            drive_objects = []
            sata_drive_list = self._get_sata_drives()
            non_sata_drive_list = list(set(self.drive_list) - set(sata_drive_list))
            drive_objects.extend(
                StorageDeviceFactory(
                    self.host,
                    sata_drive_list,
                    sata_drive_config,
                ).create()
            )
            drive_objects.extend(
                StorageDeviceFactory(
                    self.host,
                    non_sata_drive_list,
                    None,
                ).create()
            )
        else:
            drive_objects = StorageDeviceFactory(
                self.host,
                self.drive_list,
                self.test_control.get("drive_config_file", None),
            ).create()
        return drive_objects

    def _get_sata_drives(self) -> List:
        """Returns a list of SATA drive handles from lsscsi"""
        sata_re = r"ATA.*\/dev\/(sd(?:\w+))"
        lsscsi_out = self.host.run("lsscsi")
        sata_drive_list = re.findall(sata_re, lsscsi_out)
        return sata_drive_list

    def _collect_drive_data(self) -> Dict:
        """
        Collect current drives' data for before/after comparison and validation

        @return {}: dictionary that map drive serial number -> drive_snapshot object
        """
        data: List[Dict] = AsyncUtils.run_async_jobs(
            [AsyncJob(func=drive.collect_data) for drive in self.drives]
        )
        return {each.get("serial_number"): each for each in data}

    def _validate_cryptoerase_support(self) -> None:
        for drive in self.test_drives:
            if drive.interface == DriveInterface.NVME:
                out = drive.get_crypto_erase_support_status()
                if not out:
                    self.log_info(
                        "Skip Crypto Erase validation on boot drive and drives "
                        "which dont support it"
                    )
                else:
                    AutovalUtils.validate_condition(
                        out,
                        "%s: Crypto Erase Supported" % drive,
                        raise_on_fail=False,
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.NVME_ERR,
                    )

    def _validate_drives_smart(self) -> None:
        for drive in self.test_drives:
            validate_config = getattr(drive, "validate_config", {})
            serial_no = getattr(drive, "serial_number", "")
            try:
                smart_before = self.drive_data["before_test"][serial_no]["SMART"]
                smart_after = self.drive_data["after_test"][serial_no]["SMART"]
            except KeyError:
                AutovalUtils.validate_condition(
                    False,
                    f"Missing SMART. Drive: {drive.block_name}. Serial No. {serial_no}",
                    raise_on_fail=False,
                    error_type=ErrorType.SMART_COUNTER_ERR,
                )
            else:
                if (
                    drive.interface == DriveInterface.NVME
                    and (not any(item in smart_before for item in SMART_LOGS))
                    and (not any(item in smart_after for item in SMART_LOGS))
                ):
                    AutovalLog.log_info(
                        f"Skipping SMART Validation for Non-SMART Drive: {drive.block_name}. Serial No. {serial_no}"
                    )
                    continue
                ignore_smart = self.test_control.get("ignore_smart", False)
                smart_validator.compare_drive_data(
                    serial_no,
                    validate_config,
                    smart_before,
                    smart_after,
                    ignore_smart=ignore_smart,
                )

    def _get_write_amplification(self) -> None:
        """This function calculates the write amplification for each drive in a system."""
        for drive in self.drives:
            serial_no = getattr(drive, "serial_number", "")
            try:
                smart_before = self.drive_data["before_test"][serial_no]["SMART"]
                smart_after = self.drive_data["after_test"][serial_no]["SMART"]
            except KeyError:
                AutovalUtils.validate_condition(
                    False,
                    f"Missing SMART. Drive: {drive.block_name}. Serial No. {serial_no}",
                    raise_on_fail=False,
                    error_type=ErrorType.SMART_COUNTER_ERR,
                )
            else:
                drive.get_write_amplification(smart_before, smart_after)

    def _convert_data_for_config_check(self) -> Dict:
        """
        Collect the data from each drive and store it in config check
        json format. The first key is hdd and ssd. The key in second depth
        will be serial number from each drive. The third depth will contain
        data keys and data values from each drive.

        Returns:
            Dict: A dictionary containing the data from each drive in config check format.
        """
        AutovalLog.log_info("Converting storage data for config check")
        formatted_drive_info = {"hdd": {}, "ssd": {}, "emmc": {}}
        for each_drive in self.drives:
            drive_type = str(each_drive.get_type()).lower().split(".")[1]
            formatted_drive_info[drive_type].update(
                each_drive.collect_data_in_config_check_format()
            )
        return formatted_drive_info

    # @Override
    def cleanup(self, *args, **kwargs) -> None:
        self._validate_hdd_drive_count()
        self._validate_lsblk_info()
        # Remove test file
        self.host.run("rm -f /root/havoc_fio_file", ignore_status=True)
        AutovalLog.log_debug("lsblk Output: %s" % self.host.run(cmd="lsblk"))
        AutovalLog.log_debug("NVMe List Output: %s" % self.host.run(cmd="nvme list"))
        # Remove partitions after test if they still exist
        if self.test_control.get("remove_partition", True):
            AutovalLog.log_info("umount and remove raid devices")
            self._umount_and_remove_raid_devices()
            AutovalLog.log_info("Removing drive's partitions")
            self._remove_partitions()
        # Remove mnt files
        if not self.test_control.get("only_boot_drive"):
            self.unmount_before_test(
                [d for d in self.drives if str(d) != self.boot_drive]
            )
        try:
            # Make sure test used drives are available post test execution.
            self.check_block_devices_available()
        except Exception as e:
            AutovalLog.log_info(f"Seems to be block drive missing due to : {str(e)}.")
        finally:
            config_check = kwargs.get("config_check", True)
            if config_check:
                try:
                    self.drives = self.scan_drives()
                    self.validate_drive_erase_count()
                    if self.collect_drive_data:
                        self.drive_data["after_test"] = self._collect_drive_data()
                        self._validate_drives_smart()
                        self._get_write_amplification()
                    else:
                        AutovalLog.log_info("Skipping drive data collection")
                finally:
                    super().cleanup(*args, **kwargs)
                    self._amend_config_data_with_drive_data()
            else:
                super().cleanup(*args, **kwargs)

    def _amend_config_data_with_drive_data(self) -> None:
        """
        Get the current config_result json file saved from test_base and
        attach/update storage_test_base config_data into the the
        config_result json.
        """
        conf_res_file = self.get_test_results_file_path("config_results.json")
        drive_config_data = self._convert_data_for_config_check()
        current_config_data = {}
        if FileActions.exists(conf_res_file):
            current_config_data = FileActions.read_data(conf_res_file, json_file=True)
        current_config_data.update(drive_config_data)
        current_config_data.update(self.expander_info)
        AutovalLog.log_info(
            "saving config results from storage_test_base at %s" % conf_res_file
        )
        self.result_handler._save_json(current_config_data, conf_res_file)

    def save_drive_logs_async(self, drives: List[Drive]) -> None:
        """
        Uses AsyncUtils to dump multiple drives data as JSON in <result directory>/SMART

        Parameter
        ---------
        drives: List[Drive]
            List of 'Drive' objects whose data is to be written to JSON
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        drives_time = [(drive, timestamp) for drive in drives]

        AsyncUtils.run_async_jobs(
            [
                AsyncJob(func=self.save_single_drive_log, args=[this_drive])
                for this_drive in drives_time
            ]
        )

    def save_single_drive_log(self, drive_time: Tuple) -> None:
        """
        Dumps drive data (for a single drive) as JSON in <result directory>/SMART

        Parameter
        ---------

        drive_time: Tuple(Drive,str)
            Contains a 'Drive' object and a timestamp in str form
        """
        drive = drive_time[0]
        timestamp = drive_time[1]
        file_name = "{}.json".format(drive.serial_number)
        FileActions.mkdirs(os.path.join(self.smart_log_dir, timestamp))
        file_path = os.path.join(self.smart_log_dir, timestamp, file_name)
        AutovalLog.log_info("{} Saving SMART data at {}".format(drive, file_path))
        FileActions.write_data(
            file_path,
            drive.collect_data(),
            append=False,
        )

    def get_test_drives_from_drives(
        self,
        drive_type: Optional[str] = None,
        interface: Optional[str] = None,
        model: Optional[str] = None,
        only_boot_drive: bool = False,
        include_boot_drive: bool = False,
    ) -> List[Drive]:
        """Filter drives that meet provided criteria for testing"""
        if only_boot_drive:
            # Take only boot drive
            filtered = [d for d in self.drives if str(d) == str(self.boot_drive)]
        elif include_boot_drive:
            # Add boot drive to existing data drives. Take all drives
            filtered = self.drives
        else:
            # Take all drives except boot drive
            filtered = [d for d in self.drives if str(d) != str(self.boot_drive)]
        if drive_type:
            _enum_type = DriveType(drive_type)
            filtered = self._filter_drive_by_attr(filtered, "type", _enum_type)
        if interface:
            _enum_intf = DriveInterface(interface)
            filtered = self._filter_drive_by_attr(filtered, "interface", _enum_intf)
        if model:
            filtered = self._filter_drive_by_attr(filtered, "model", model)
        return filtered

    def get_block_name_from_drive_list(self, drives: List[Drive]) -> List[str]:
        """Return list of drives from drive ojects"""
        return [drive.block_name for drive in drives]

    def _filter_drive_by_attr(
        self,
        drives: List[Drive],
        attr: str,
        value: Union[str, DriveInterface, DriveType],
    ) -> List[Drive]:
        """
        Return drives in a list that has an attribute equal a provided value

        @param String attr: attribute to compare
        @param Enum/String value: drive is included if attribute has this value
        """
        filtered = []
        for drive in drives:
            if getattr(drive, attr, None) == value:
                filtered.append(drive)
        return filtered

    def validate_degraded_drives_presence(self) -> None:
        """
        Validate degraded drives presence.

        This method will check, if there are any degraded drives.
        """
        # Drive check not implemented drive dict
        degrade_check_ni_dict = {}
        for drive in self.test_drives:
            try:
                drive.is_drive_degraded()
            except NotImplementedError:
                # TODO
                # The drive degraded check for other inerface like sata, sas.
                if not degrade_check_ni_dict.get(drive.interface.value, None):
                    degrade_check_ni_dict[drive.interface.value] = []
                degrade_check_ni_dict[drive.interface.value].append(drive.serial_number)

        if degrade_check_ni_dict:
            AutovalLog.log_info(
                "+++Skipping Drive degrade check on drives "
                f" {degrade_check_ni_dict} as degrade check is not yet implemented"
                f" for interface {list(degrade_check_ni_dict.keys())}."
            )
        AutovalLog.log_info("No degraded drives are present.")

    def unmount_before_test(self, test_drives) -> None:
        """
        Test Drives: List of drives from self.test_drives. It should
        not contain any boot_drive.
        **note that '/dev' is a default mountpath, which is a clean
        mount path that we want before the test.

        @param: test_drives
        """
        AutovalLog.log_info("Removing all mounted path")
        for drive in test_drives:
            df_info = FilesystemUtils.get_df_info(
                host=self.host, device=drive.block_name
            )
            if df_info["mounted_on"] != "/dev":
                AutovalLog.log_info(
                    "Found mount_path: %s on drive %s. Removing.."
                    % (df_info["mounted_on"], str(drive.block_name))
                )
                FilesystemUtils.unmount(host=self.host, mnt_point=df_info["mounted_on"])
        AutovalLog.log_info("Validating umount all drives")
        err_msg = []
        for drive in test_drives:
            df_info = FilesystemUtils.get_df_info(
                host=self.host, device=drive.block_name
            )
            if df_info["mounted_on"] != "/dev":
                msg = "Failed to umount on drive %s for mount_path: %s" % (
                    str(drive.block_name),
                    df_info["mounted_on"],
                )
                err_msg.append(msg)
        self.validate_empty_list(
            err_msg,
            "Validating the unmount on drives",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.SYSTEM_ERR,
        )
