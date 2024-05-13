#!/usr/bin/env python3

# pyre-unsafe
"""
Test validates the MD5 checkusm on the SSD/HDD
by doing an fio write, get MD5 value on the written data,
reboot and again check the MD5 value and compare it with
original value using the MD5 function or FIO based on the
input control file for  filesystem and raw drives.
The size to be written for fio is based on the user input
from the control file.This test supports all interfaces like
NVME, SATA and SAS.
"""
import time

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.filesystem_utils import FilesystemUtils
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase

MOUNT_PATH = "/mnt/fio_test_%s/"


class DriveMd5Verify(StorageTestBase):
    """
    Test validates the MD5 checksum on the SSD/HDD for both
    filesystem and raw drives using the MD5 function or the fio md5, based
    on the input. For the fio the size to be written is calculated based on
    the input from the control file. Once the FIO write is completed it goes
    for a reboot, then goes for FIO read and verify and checksum calculation.
    This test supports all interfaces like NVME, SATA and SAS.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initializes the SSD MD5 test.

        This method initializes the basic configuration for logging
        information, load and store the input details gathered from
        input/control (json) file.
        """
        super().__init__(*args, **kwargs)
        self.cycle_type_list = self.test_control.get("cycle_type_list", ["warm"])
        self.cycle_count = self.test_control.get("cycle_count", 1)
        self.filesystem = self.test_control.get("filesystem", False)
        self.percent_write_size = self.test_control.get("percent_write_size", 5)
        self.md5_verification = self.test_control.get("md5_verification", True)
        self.write_fio = self.test_control["write_fio"]
        self.read_fio = self.test_control["read_fio"]
        self.verify_fio = self.test_control["verify_fio"]
        self.wait_time = self.test_control.get("wait_time", 10)
        self.drives_md5 = {}
        self.file_io = "file1" if self.filesystem else ""

    def setup(self, *args, **kwargs) -> None:
        super().setup(*args, **kwargs)
        # Setup fio
        if self.test_drives:
            self.test_control["drives"] = self.test_drives
        if self.boot_drive:
            self.test_control["boot_drive"] = self.boot_drive
        fio_runner = FioRunner(self.host, self.test_control)
        self.validate_no_exception(
            fio_runner.test_setup,
            [],
            "Fio setup()",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

    def get_test_params(self) -> str:
        """
        Returns a string of test_params for the Test Summary
        """
        params = (
            f"\nCycle count: {self.cycle_count}. Cycle type: {self.cycle_type_list}. "
        )
        params += f"Use filesystem: {self.filesystem}. MD5 verification: {self.md5_verification}"
        return params

    def execute(self) -> None:
        """
        This method calls the functions where it calculates size to be given
        for fio write and updates the same to the FioRunner function where it
        process the input json file.
        Test flow:
        1.Checks the filesystme type, number of cycles and capacity to
        from the input json. The capacity is in percentage.For ex, if its 10,
        it means,the size to be written in 10% of the least capacity drive.
        2.Call the fio run method where it schedules the fio run
        3.Calculate the MD5 value.(Based on the json check MD5 calculation
          will be done by fio or the inbuilt function used
        4.Power cycle the DUT
        6.Mount the drives again if it's a filesystem test
        7.Calculate the MD5 value after reboot (This is also based on the json
          check)
        8.Compare the MD5 values if the function method is used for checking the
          MD5 values.
        """
        # calculate the drive size
        initial_size = self.write_fio["ssd_md5"]["args"]["SIZE"]
        size = self.calculate_size_for_fio()
        if initial_size != size:
            self.log_info(f"Fio size has changed from {initial_size} to {size}")
        self.write_fio["ssd_md5"]["args"]["SIZE"] = size
        self.read_fio["ssd_md5"]["args"]["SIZE"] = size
        self.verify_fio["ssd_md5"]["args"]["SIZE"] = size
        for i in range(1, self.cycle_count + 1):
            self.log_info(f"Starting cycle - {i}")
            self.log_info("FIO Write is starting")
            self.run_fio(self.write_fio, job_name="write")
            # MD5 value checking
            if self.md5_verification:
                md5_before_power_cycle = self.get_md5_value()
            # power cycle
            self.power_cycle()
            # FIO read
            self.log_info("FIO Read is starting")
            self.run_fio(self.read_fio, job_name="read")
            # FIO verify
            self.log_info("FIO Verify is starting")
            self.run_fio(self.verify_fio, job_name="verify")
            # MD5 value checking
            if self.md5_verification:
                md5_after_power_cycle = self.get_md5_value()
                # validate the dictionary values of MD5 before and after
                # reboot. Key is the device and value is MD5
                # pyre-fixme[61]: `md5_before_power_cycle` is undefined, or not
                #  always defined.
                diffs = self.diff_configs(md5_before_power_cycle, md5_after_power_cycle)
                self.validate_empty_diff(
                    diffs,
                    "MD5 checksum differences",
                    raise_on_fail=True,
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )

    def run_fio(self, fio_input, job_name: str = "") -> None:
        """
        FIO Job of the SSD MD5 Test.
        This method executes the FIO start test method where the
        FIO process is started(creationg FIO job to  scheduling
        it on the DUT)

        Parameters
        ----------
        fio_input : String
           The fio configuration
        """
        if job_name:
            self.test_control["job_name"] = job_name
        self.test_control["run_definition"] = fio_input
        fio_runner = FioRunner(self.host, self.test_control)
        fio_runner.start_test()

    def calculate_size_for_fio(self) -> str:
        """
        This function will get the final size to be written
        on the disk for the fio operation.The return value will
        get updated on the fio job file.
        Example:if in the control file,if the percent_disk_size mentioned
        is 10,so it will calculate the 10% size of the all the drives and
        return 10% value of the least size drive which will be updated
        on the fio run definition size.
        """
        final_size = DiskUtils.calculate_min_size_of_drives(
            self.host, self.percent_write_size, self.test_drives
        )
        return final_size

    def power_cycle(self) -> None:
        """Power Cycle of the SSD MD5 Test.

        This method executes the power cycle for SSD MD5 test by
        executing the power cycle command on the DUT through OutOfBand
        based on the cycle type.
        """
        for cycle_type in self.cycle_type_list:
            if self.wait_time and cycle_type.lower() in ["on", "12v-on"]:
                self.log_info(
                    "%s seconds waiting to power on host %s"
                    % (self.wait_time, self.host.hostname)
                )
                # If cycle type is 'off' or '12v-off' follwed by 'on' or '12v-on'
                # waiting to power on the dut as per the wait_time.
                time.sleep(self.wait_time)
            self.log_info("Running %s power_cycle" % cycle_type)
            self.host.cycle_host(self.host, cycle_type)

    def get_md5_value(self):
        """
        This function calculates the md5 checksum which has been written on
        the mounted drive file.

        Returns
        -------
        md5values : Dict
            The md5 checksum value to its respective device.
        """
        md5values = {}
        self.drives_md5 = {
            d.block_name: (
                MOUNT_PATH % d.block_name + self.file_io
                if self.filesystem
                else f"/dev/{d.block_name}"
            )
            for d in self.test_drives
            if d.block_name != str(self.boot_drive)
        }
        if self.drives_md5:
            self.log_info(f"Checking MD5 on Data drives: {self.drives_md5}")
            md5values = DiskUtils.get_md5_for_drivelist(self.host, self.drives_md5)
        if str(self.boot_drive) in str(self.test_drives):
            path = (
                MOUNT_PATH % self.boot_drive + self.file_io
                if self.filesystem
                else f"/dev/{self.boot_drive}"
            )
            if DiskUtils.is_drive_mounted(self.host, str(self.boot_drive)):
                path = FioRunner.MOUNTED_DRIVE_FIO_PATH
            self.log_info(f"Checking MD5 on Boot drive: {self.boot_drive}")
            md5 = DiskUtils.get_md5_sum(self.host, path)
            md5values.update({self.boot_drive: md5})
        self.log_info(f"MD5 values: {md5values}")
        return md5values

    def cleanup(self, *args, **kwargs) -> None:
        """
        This method cleans up the mounted directories.
        """
        self.validate_no_exception(
            FilesystemUtils.unmount_all,
            [self.host, list(self.drives_md5.keys()), MOUNT_PATH],
            "Clean drive",
            raise_on_fail=False,
            log_on_pass=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        super().cleanup(*args, **kwargs)
