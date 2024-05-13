#!/usr/bin/env python3

# pyre-unsafe
"""Class for drive"""
import re
from enum import Enum

from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import AutoValException, TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.decorators import retry
from autoval.lib.utils.file_actions import FileActions

from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.hdparm_utils import HdparmUtils
from autoval_ssd.lib.utils.scrtnycli_utils import ScrtnyCli
from autoval_ssd.lib.utils.sdparm_utils import SdparmUtils
from autoval_ssd.lib.utils.sg_utils import SgUtils
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils


class DriveType(Enum):
    """Available drive types"""

    SSD = "ssd"
    HDD = "hdd"
    EMMC = "emmc"


class DriveInterface(Enum):
    """Available drive interface"""

    NVME = "nvme"
    SATA = "sata"
    SAS = "sas"
    EMMC = "emmc"


class Drive:
    """Main class for drive"""

    def __init__(self, host, block_name, config=None) -> None:
        """
        Interface for collecting drive data and validate drive data based on
            instructions provided in config file

        @param Host host: host object
        @param String block_name: drive name in /dev/ path
        @param String config: json file that control how drive data is collected
            and validated
        """
        self.host = host
        self.block_name = block_name
        self.model = ""
        self.reboot_models = []
        self.manufacturer = "Generic"
        self.serial_number = "Unknown"
        self.type = self.get_type()

    def get_firmware_version(self) -> str:
        """Get drive fw version"""
        # To be overridden in child classes
        return ""

    def collect_data(self):
        """
        Collect drive data at this point in time. Should be overridden in sub-classes
        """
        return {}

    def move_smart_to_upper_level(self, drive_info):
        """
        This function moves the dictionary within the dictionary one
        upper level. For example,

            dict1 {                     dict1{
                'SMART' {                     key: value
                    key: value   ==>    }
                }
            }

        This only applies if the child directory contains SMART key. If
        it doesn't contain 'SMART' key, it will return none. This function
        is only used for HDD drive type only

        @param drive_info: the dictionary of drive info passed down from
        collect_data
        """
        if "SMART" in drive_info:
            for data_key in drive_info["SMART"]:
                drive_info[data_key] = drive_info["SMART"][data_key]
            del drive_info["SMART"]
        return drive_info

    def collect_data_in_config_check_format(self):
        """
        Get the drive data and convert it to a format for config_result
        at the end of the test. The first depth key should be serial
        number and second depth will be data key and data value.
        """
        drive_info = self.collect_data()
        drive_info = self.move_smart_to_upper_level(drive_info)
        new_format = {}
        new_format[drive_info["serial_number"]] = drive_info
        return new_format

    def get_write_amplification(self, smart_before, smart_after) -> bool:
        """
        Calculate write amplification. Should be overridden in sub-classes
        """
        return True

    @retry(tries=2, sleep_seconds=3, exponential=True)
    def get_smartctl_output(self):
        """
        Return output of `smartctl -x` for a drive

        @param String dev: drive name in /dev/ path
        @return string
        """
        cmd = "smartctl -x /dev/%s" % self.block_name
        # smartctl -x sometimes give non zero exit status
        # with drive information, which should be captured regardless
        # of exit status
        ret = self.host.run_get_result(cmd=cmd, ignore_status=True)
        if ret.return_code != 0:
            errors = re.findall(r".*Error.*", ret.stdout)
            AutovalUtils.validate_condition(
                False,
                f"Drive /dev/{self.block_name} has errors: {errors}",
                warning=True,
            )
        if not ret.stdout.strip():
            raise TestError(
                f"Failed to get SMART for /dev/{self.block_name}: {ret.stdout}",
                error_type=ErrorType.SMART_COUNTER_ERR,
            )
        return ret.stdout

    def extract_smart_field(self, field, out, pattern):
        """
        Find a value for a given field in SMART output. Value of field should
            be in group 1 of regex pattern

        @param String field:
        @param String out: SMART output
        @param String pattern: regex of field and its value
        """
        match = re.search(pattern, out)
        if match:
            return match.group(1)
        raise TestError(
            "Didn't find %s in SMART output" % field,
            error_type=ErrorType.SMART_COUNTER_ERR,
        )

    def get_type(self) -> DriveType:
        """
        Check whether drive is HDD or SSD

        @return String
        """
        if self.block_name == "mmcblk0":
            return DriveType.EMMC
        cmd = "cat /sys/block/%s/queue/rotational" % self.block_name
        rot = self.host.run(cmd=cmd)
        if rot == "0":
            return DriveType.SSD
        if rot == "1":
            return DriveType.HDD
        raise AutoValException(
            f"Unknown device type '{rot}'", error_type=ErrorType.DRIVE_ERR
        )

    def get_capacity(self, unit: str = "byte") -> int:
        """Get drive capacity"""
        byte_count = SgUtils.get_hdd_capacity(self.host, self.block_name)
        return int(DiskUtils.convert_from_bytes(byte_count, unit))

    def get_last_lba(self) -> int:
        """Get last logical block on disk"""
        return SgUtils.get_hdd_last_lba(self.host, self.block_name)

    def get_bs_size(self) -> int:
        """Get current formatted block size"""
        return SgUtils.get_hdd_lb_length(self.host, self.block_name)

    def disable_write_cache(self, save: bool = False) -> None:
        """Disable write cache"""
        # pyre-fixme[16]: `Drive` has no attribute `interface`.
        if self.interface == DriveInterface.SATA:
            HdparmUtils.disable_write_cache(self.host, self.block_name, save=save)
        elif self.interface == DriveInterface.SAS:
            SdparmUtils.disable_write_cache(self.host, self.block_name, save=save)
        elif self.interface == DriveInterface.NVME:
            NVMeUtils.disable_write_cache(self.host, self.block_name)
        else:
            raise TestError(
                "Device status is unknown, unable to disable write_cache",
                error_type=ErrorType.DRIVE_ERR,
            )

    def reset(self) -> None:
        """
        Power cycle drive
        """
        # TODO: Currently no support for SATA and SAS SSD's.
        raise NotImplementedError("Reset method not implemented")

    def __str__(self) -> str:
        return f"{self.block_name}"

    def __repr__(self) -> str:
        return f"{self.block_name}"

    def remove_all_partitions(self, refresh_partitions: bool = True) -> None:
        """Remove all partitions"""
        DiskUtils.remove_all_partitions(self.host, self.block_name, refresh_partitions)

    def get_drive_temperature(self) -> int:
        """Get Drive Temperature
        Collect the temperature on SATA/SAS drive.
        """
        cmd = "smartctl -A /dev/%s" % self.block_name
        out = self.host.run(cmd)
        match = re.search(r"Temperature_Celsius.*\-\s*(\d+)\s*", out)  # noqa
        if match:
            temp = match.group(1)
        else:
            match = re.search(
                r"Current\sDrive\sTemperature.*\:\s*(\d+)\s*", out
            )  # noqa
            if match:
                temp = match.group(1)
            else:
                raise AutoValException(
                    "Current Drive Temperature not in output: %s" % out,
                    error_type=ErrorType.SMART_COUNTER_ERR,
                )
        return int(temp)

    def format_drive(self, secure_erase_option: int = 0) -> None:
        """
        Format the drive. Should be overridden in sub-classes
        """
        return

    def validate_firmware_update(self, ver: str) -> None:
        """
        Validate firmware update.

        This method will validate if the drive current firmware version
        is matching with the expected version
        Parameters
        ----------
        ver: str
            Expected version of the firmware.
        """
        AutovalUtils.validate_equal(
            self.get_firmware_version(),
            ver,
            "Validate if Firmware version %s is updated successfully" % ver,
            error_type=ErrorType.FIRMWARE_UPGRADE_ERR,
        )

    def is_drive_degraded(self):
        """Check if drive degraded"""
        raise NotImplementedError("Drive Degrade functionality is not implemented")

    def get_smartctl_wwid(self):
        """
        From the smartctl output , getting the below line(device id)
        LU WWN Device Id: 5 000039 aa8ca08b4
        """
        drive_smart_output = self.get_smartctl_output()
        wwid = re.search(r"LU WWN Device Id:\s+(\w+\s+\w+\s+\w+)", drive_smart_output)
        wwid_smartctl = wwid.group(1).replace(" ", "")
        AutovalLog.log_info("Drive wwid: %s" % wwid_smartctl)
        return wwid_smartctl

    def update_firmware_with_scrtnycli(self, fw_bin_loc: str) -> None:
        """
        This wwid_smartctl is mapped to the output scan of scrtnycli and taking the DH of the drive.
        The DH (hex value) is used in the upgrade command
        """
        wwid_smartctl = self.get_smartctl_wwid()
        # Install the scrnycli tool
        tool_path = ScrtnyCli.deploy_scrtnycli(self.host)
        # As the f/w binary is at manifold location, getting the file to the local path.
        local_bin_path = FileActions.get_local_path(self.host, fw_bin_loc)
        scrtnycli_out_ioc1 = ScrtnyCli.scan_drive_scrtnycli(self.host, tool_path)
        ioc_no = 1
        scrtnycli_ioc_map = {"1": scrtnycli_out_ioc1}
        if "coldstorage" in self.host.hostname:
            scrtnycli_out_ioc2 = ScrtnyCli.scan_drive_scrtnycli_ioc2(
                self.host, tool_path
            )
            scrtnycli_ioc_map.update({"2": scrtnycli_out_ioc2})
        dh_number = None
        wwid = wwid_smartctl.upper()
        for ioc, scrtnycli_output in scrtnycli_ioc_map.items():
            for line in scrtnycli_output.splitlines():
                wwid_pattern = re.search(r"\s+(\w+)$", line)
                if wwid_pattern:
                    if wwid == wwid_pattern.group(1):
                        dh_number = re.search(r"\s+(\w+)\s+Disk", line)
                        if dh_number:
                            ioc_no = ioc
                            break
        if dh_number is None:
            raise TestError(
                f"WWID or SAS address is not found for {self.block_name}",
                error_type=ErrorType.EXPANDER_ERR,
            )
        ScrtnyCli.update_firmware_scrtnycli(
            self.host,
            local_bin_path,
            dh_number.group(1),
            tool_path,
            ioc_no,
        )

    def check_lsiutil(self):
        """
        This function is just to check if lsiutil works on the drive for both GC and BC
        """
        out = self.host.run("lsiutil")
        return out

    def get_workload_target_status(self) -> bool:
        """
        Get workload target status

        If this drive model is capable of reaching the current performance expectations
        in workoad targets then True is returned.
        """
        return False
