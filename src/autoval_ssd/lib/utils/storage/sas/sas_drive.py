#!/usr/bin/env python3autoval_ssd.lib.utils.

# pyre-unsafe
"""library to manage SAS drives"""
import os
import re

from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.generic_utils import GenericUtils

from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.hdparm_utils import HdparmUtils
from autoval_ssd.lib.utils.sdparm_utils import SdparmUtils
from autoval_ssd.lib.utils.storage.drive import Drive, DriveInterface


class SASDriveException(TestError):
    """Class for drive error"""

    pass


SAS_CONFIG_DIR = "sas_smart"
TARGET_ERROR_FIELDS = "target_errors.json"
DEFAULT_VALIDATE_CONFIG = "validate_instr.json"


class SASDrive(Drive):
    """
    Interface for interacting with SAS drives
    @param Host host: host object
    @param String block_name: drive name in /dev/ path
    @param String config: json file that controls how drive data is
    collected and validated
    """

    def __init__(self, host, block_name, config=None) -> None:
        super().__init__(host, block_name, config=config)
        self.interface = DriveInterface.SAS
        smart_data = self.get_smartctl_output()
        self.serial_number = self._get_serial_number(smart_data)
        self.model = self._get_model_number(smart_data)
        self.sector_size = self._get_sector_size(smart_data)
        self.manufacturer = self._get_manufacturer(smart_data)
        if config is None:
            config = DEFAULT_VALIDATE_CONFIG
        self.validate_config = self._load_config(config)

    def collect_data(self):
        return {
            "SMART": self.get_smart_log(),
            "manufacturer": self.manufacturer,
            "block_name": self.block_name,
            "serial_number": self.serial_number,
            "firmware_version": self.get_firmware_version(),
            "capacity": self.get_capacity(),
            "model": self.model,
            "interface": self.interface.value,
            "type": self.type.value,
            "sector_size": self.sector_size,
            "write_cache": self.get_write_cache(),
            "drive_temperature": self.get_drive_temperature(),
        }

    def get_smart_log(self):
        """Return smart log"""
        log = {}
        try:
            smart_data = self.get_smartctl_output()
            log["health"] = self.get_health_status(smart_data)
            log["element_in_grown_defect"] = self._get_element_in_grown_defect(
                smart_data
            )
            log.update(self._get_uncorrected_errors(smart_data))
            log.update(self._get_target_errors(smart_data))
            return log
        except TestError as exc:
            raise TestError(f"Error getting SMART log on /dev/{self.block_name}: {exc}")

    def get_health_status(self, smart_data=None):
        """Return drive health status"""
        if not smart_data:
            smart_data = self.get_smartctl_output()
        pattern = r"SMART Health Status:\s+(\w+)"
        return self.extract_smart_field("Health status", smart_data, pattern)

    def get_firmware_version(self):
        """Return drive FW version"""
        smart_data = self.get_smartctl_output()
        pattern = r"Revision:\s+(\w+)"
        return self.extract_smart_field("firmware version", smart_data, pattern)

    def get_interface_speed(self):
        """Return drive interface speed"""
        sas_address = self._get_sas_address()
        sym_link = self._find_end_device_with_sas_address(sas_address)
        cbt = self._get_channel_bus_target_from_sym_link(sym_link)
        phy_id = self._get_phy_id_from_cbt_address(cbt)
        speed = self._get_link_speed_from_os((cbt[0], cbt[1], phy_id))
        return speed

    def get_read_lookahead(self) -> int:
        """
        @return int: 1 for enabled, 0 or disabled
        """
        return SdparmUtils.get_read_lookahead(self.host, self.block_name)

    def enable_read_lookahead(self, save: bool = False) -> None:
        """
        @param boolean save: if True will set current mode and the saved mode
        """
        SdparmUtils.enable_read_lookahead(self.host, self.block_name, save=save)

    def disable_read_lookahead(self, save: bool = False) -> None:
        """Disable read cache"""
        SdparmUtils.disable_read_lookahead(self.host, self.block_name, save=save)

    def get_write_cache(self) -> int:
        """
        Return write cache: 1 for enabled, 0 or disabled
        """
        return SdparmUtils.get_write_cache(self.host, self.block_name)

    def enable_write_cache(self, save: bool = False) -> None:
        """Enable write cache"""
        SdparmUtils.enable_write_cache(self.host, self.block_name, save=save)

    def disable_write_cache(self, save: bool = False) -> None:
        """Disable write cache"""
        SdparmUtils.disable_write_cache(self.host, self.block_name, save=save)

    def _load_config(self, config_file: str):
        """
        @param string config_file:
        @return dictionary
        """

        cfg_dir = "cfg/" + SAS_CONFIG_DIR
        relative_cfg_file_path = os.path.join(cfg_dir, config_file)
        return GenericUtils.read_resource_cfg(file_path=relative_cfg_file_path).get(
            "sas"
        )

    def _get_uncorrected_errors(self, smart_data):
        """
        Get total read, write, verify uncorrected error counters from SMART log.

        e.g.
        Error counter log:
            ...
           Errors Corrected by           Total   Correction     Gigabytes    Total
               ECC          rereads/    errors   algorithm      processed    uncorrected
           fast | delayed   rewrites  corrected  invocations   [10^9 bytes]  errors
            read:    0     0       0         0      81224     117210.962           0
            write:   0     0       0         0      14771     168577.072           0
            verify:  0     9       0         9      23574          7.516           0

        @param string smart_data
        @return {}
        """
        log = {}
        #  for op in ["read", "write", "verify"]:
        for op in ["read", "write"]:
            _type = op + "_uncorrected_errors"
            _patt = r"{}:(?:\s+\d+)+\s+\d+\.(?:\d+)?\s+(\d+)".format(op)
            log[_type] = int(self.extract_smart_field(_type, smart_data, _patt))
        return log

    def _get_element_in_grown_defect(self, smart_data) -> int:
        """Return Elements in grown defect from SMART"""
        pattern = r"Elements in grown defect list:\s+(\w+)"
        return int(
            self.extract_smart_field("Elements in grown defect", smart_data, pattern)
        )

    def _get_target_errors(self, smart_data):
        """Return dictionary of errors on target SMART"""
        log = {}

        cfg_dir = "cfg/" + SAS_CONFIG_DIR
        relative_cfg_file_path = os.path.join(cfg_dir, TARGET_ERROR_FIELDS)

        fields = GenericUtils.read_resource_cfg(file_path=relative_cfg_file_path).get(
            "fields"
        )
        drive_expander_log = self._get_expander_drive_log(smart_data)
        for _field in fields:
            # e.g.
            # Loss of dword synchronization count: 0
            # Phy reset problem = 0
            _pattern = r"{}\s?[:=]\s+(\w+)".format(_field)
            log[_field] = int(
                self.extract_smart_field(_field, drive_expander_log, _pattern)
            )
        return log

    def _get_expander_drive_log(self, smart_data) -> str:
        """
        Get expander log in 'Protocol Specific port log page for SAS SSP' section
            in SMART log

        @param string smart_data:
        @return string: expander device log page
        """
        log = []
        is_expander_log = False
        for line in smart_data.splitlines():
            if "attached device type: expander device" in line:
                is_expander_log = True
            if "attached device type: no device attached" in line:
                is_expander_log = False
            if is_expander_log:
                log.append(line)
        return "\n".join(log)

    def _get_manufacturer(self, smart_data):
        pattern = r"Vendor:\s+(\w+)"
        return self.extract_smart_field("manufacturer", smart_data, pattern)

    def _get_serial_number(self, smart_data):
        pattern = r"Serial number:\s+(\w+)"
        return self.extract_smart_field("serial number", smart_data, pattern)

    def _get_user_capacity(self, smart_data):
        pattern = r"User Capacity:\s+(\w+)"
        field = self.extract_smart_field("user capacity", smart_data, pattern)
        return field.replace(",", "")

    def _get_model_number(self, smart_data):
        pattern = r"Product:\s+(\w+)"
        return self.extract_smart_field("device model", smart_data, pattern)

    def _get_sector_size(self, smart_data):
        pattern = r"Logical block size:\s+(\w+)\sbytes"
        return self.extract_smart_field("sector size", smart_data, pattern)

    def _get_channel_bus_target_from_sym_link(self, link):
        """
        Get drive's C:B:T from sym link

        @param string link: symbolic link of drive
            e.g. ...host6/port-6:1/expander-6:1/port-6:1:9/end_device-6:1:9/...
        @return tuple(str, str, str): tuple of C:B:T
        """
        match = re.search(r"end_device-([0-9]+)\:([0-9]+)\:([0-9]+)", link)
        if match:
            return match.groups()
        raise TestError(
            "Fail to find /dev/%s C:B:T address from sym link: %s"
            % (self.block_name, link)
        )

    def _get_phy_id_from_cbt_address(self, cbt):
        """
        With SAS expander topology, there may be a target/phy missmatch.
            From C:B:T we can get phy identifier

        @param cbt tuple(str, str, str): tuple of C:B:T
        @return string: phy id of drive
        """
        cmd = "cat /sys/class/sas_device/end_device-"
        cmd += "%s:%s:%s/phy_identifier" % cbt
        phy_id = self.host.run(cmd=cmd)
        return phy_id

    def _get_link_speed_from_os(self, cb_phy_id):
        """
        Get link speed from OS, addressed as phy-C:B:Phy

        @param cbt tuple(str, str, str): tuple of C:B:Phy_ID
        @return string: represents link speed of drive
        """
        cmd = "cat /sys/class/sas_phy/phy-%s:%s:%s/" % cb_phy_id
        cmd += "negotiated_linkrate"
        link_spd = self.host.run(cmd=cmd)  # noqa
        return link_spd

    def _get_sas_address(self) -> str:
        cmd = "cat /sys/block/%s/device/sas_address" % self.block_name
        address = self.host.run(cmd=cmd)
        return address

    def _find_end_device_with_sas_address(self, sas_add) -> str:
        # 2 search /sys for the an end_device with matching sas_address
        cmd = "find /sys -type f -name 'sas_address' -print0 | "
        cmd += "xargs -0 grep %s | grep -m 1 end_device" % sas_add
        sym_link = self.host.run(cmd=cmd)
        return sym_link

    def format_drive(self, secure_erase_option: int = 0) -> None:
        """Format Drive
        To perform secure erase operation on SAS drive.
        """
        if self.type.value == "ssd":
            HdparmUtils.ssd_secure_erase(self.host, self.block_name)
        elif self.type.value == "hdd":
            DiskUtils.format_hdd(
                self.host, self.block_name, secure_erase_option=secure_erase_option
            )

    def drive_health_check(self) -> None:
        """Check drive for errors"""
        cmd = f"smartctl -l error /dev/{self.block_name}"
        out = self.host.run(cmd=cmd)
        match = re.search(r"No Errors Logged", out)
        if not match:
            raise TestError(f"Errors found in /dev/{self.block_name}: {out}")

    def run_hdd_log_collection(self, tmpdir: str, tmp_dir_path_system_log: str) -> str:
        return tmpdir
