#!/usr/bin/env python3

# pyre-unsafe
"""library to manage SATA drives"""
import os
import re

from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.generic_utils import GenericUtils

from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.hdparm_utils import HdparmUtils
from autoval_ssd.lib.utils.storage.drive import Drive, DriveInterface

OUI_WWN_MAPPING = "Oui_WWN_Mapping.json"
STAT_FIELDS = "device_statistics.json"
PHY_EVENT_FIELDS = "phy_events.json"
SATA_CONFIG_DIR = "sata_smart"
DEFAULT_VALIDATE_CONFIG = "validate_strict_hdd_instr.json"


class SATADrive(Drive):
    """
    Store data of and interact with SATA drives
    @param Host host: host object
    @param String block_name: drive name in /dev/ path
    @param String config: json file that controls how drive data is
    collected and validated
    """

    def __init__(self, host, block_name, config=None) -> None:
        super().__init__(host, block_name, config=config)
        self.interface = DriveInterface.SATA
        smart_data = self.get_smartctl_output()
        self.boot_drive = DiskUtils.get_boot_drive(host)
        self.manufacturer = self._get_manufacturer(smart_data)
        self.model = self._get_model(smart_data)
        self.serial_number = self._get_serial_number(smart_data)
        self.sector_size = self._get_sector_size(smart_data)
        if config is None:
            config = DEFAULT_VALIDATE_CONFIG
            # custom config for SSD drives with SATA interface
            # Some of them have Reallocate_NAND_Blk_Cnt in SMART
            # Some of them have Reallocated_Sector_Ct in SMART
            if self.type.value == "ssd":
                if "Reallocate_NAND_Blk_Cnt" in smart_data:
                    config = "validate_nand_instr.json"
                if "Raw_Read_Error_Rate" not in smart_data:
                    config = "validate_pseudo_instr.json"
                if "UDMA_CRC_Error_Count" not in smart_data:
                    config = "validate_hp_instr.json"
        self.validate_config = self._load_config(config)

    def get_interface_speed(self):
        """Return drive interface speed"""
        smart_output = self.get_smartctl_output()
        # Sample line to match:
        # SATA Version is:  SATA >3.2 (0x1ff), 6.0 Gb/s (current: 6.0 Gb/s)
        patt = r"SATA Version is:.*\(current: (.*)/s\)"
        return self.extract_smart_field("drive_speed", smart_output, patt)

    def get_firmware_version(self):
        """Return drive FW version"""
        smart_data = self.get_smartctl_output()
        pattern = r"Firmware Version:\s+(\w+)"
        return self.extract_smart_field("firmware version", smart_data, pattern)

    def get_read_lookahead(self) -> int:
        """
        @return int: 1 for enabled, 0 or disabled
        """
        return HdparmUtils.get_read_lookahead(self.host, self.block_name)

    def enable_read_lookahead(self, save: bool = False) -> None:
        """
        @param boolean save: Used to maintain uniform interface with SASDrive
        """
        HdparmUtils.enable_read_lookahead(self.host, self.block_name)

    def disable_read_lookahead(self, save: bool = False) -> None:
        """
        @param boolean save: Used to maintain uniform interface with SASDrive
        """
        HdparmUtils.disable_read_lookahead(self.host, self.block_name)

    def get_write_cache(self) -> int:
        """
        @return int: 1 for enabled, 0 or disabled
        """
        return HdparmUtils.get_write_cache(self.host, self.block_name)

    def enable_write_cache(self, save: bool = False) -> None:
        """
        @param boolean save: Used to maintain uniform interface with SASDrive
        """
        HdparmUtils.enable_write_cache(self.host, self.block_name, save=save)

    def disable_write_cache(self, save: bool = False) -> None:
        """
        @param boolean save: Used to maintain uniform interface with SASDrive
        """
        HdparmUtils.disable_write_cache(self.host, self.block_name, save=save)

    def collect_data(self):
        return {
            "SMART": self.get_smart_log(),
            "manufacturer": self.manufacturer,
            "block_name": self.block_name,
            "serial_number": self.serial_number,
            "firmware_version": self.get_firmware_version(),
            "capacity": self.get_capacity(),
            "interface": self.interface.value,
            "type": self.type.value,
            "model": self.model,
            "sector_size": self.sector_size,
            "write_cache": self.get_write_cache(),
            "drive_temperature": self.get_drive_temperature(),
        }

    def get_smart_log(self):
        """
        @return dictionary
        """
        log = {}
        try:
            smart_output = self.get_smartctl_output()
            log["health"] = self.get_health_status(smart_output)
            log.update(self._get_vendor_specific_smart_with_threshold(smart_output))
            log.update(self._get_phy_event_counters(smart_output))
            log.update(self._get_device_stat(smart_output))
            return log
        except TestError as exc:
            raise TestError(
                f"Error getting SMART log for /dev/{self.block_name}: {exc}"
            )

    def get_health_status(self, smart_data=None):
        """Return drive health status"""
        if not smart_data:
            smart_data = self.get_smartctl_output()
        pattern = r"SMART overall-health self-assessment test result: (\w+)"
        return self.extract_smart_field("Health status", smart_data, pattern)

    def _load_config(self, config_file: str):
        """
        @param string config_file:
        @return dictionary
        """
        cfg_dir = "cfg/" + SATA_CONFIG_DIR
        relative_cfg_file_path = os.path.join(cfg_dir, config_file)
        return GenericUtils.read_resource_cfg(file_path=relative_cfg_file_path).get(
            "sata"
        )

    def _get_vendor_specific_smart_with_threshold(self, smart_output):
        """
        Get info from section "Vendor Specific SMART Attributes with Thresholds:"
        e.g.
         ID# ATTRIBUTE_NAME          FLAGS    VALUE WORST THRESH FAIL RAW_VALUE
           5 Reallocated_Sector_Ct   -O--CK   100   100   ---    -    0
           9 Power_On_Hours          -O--CK   100   100   000    -    954
           ...

        @param str smart_output
        @return dictionary
        """
        log = {}
        pattern = (
            r"^(?:\s+)?(?P<id>\d+)\s(?P<attr>\w+)\s+(?P<flags>[A-Z-]+)"
            r"\s+(?P<value>\d+)\s+(?P<worst>\d+)\s+(?P<thresh>\S+)"
            r"\s+(?P<fail>\S+)\s+(?P<raw>\S+)"
        )
        matches = re.finditer(pattern, smart_output, re.M)
        if matches:
            for match in matches:
                attr = match.group("attr")
                items = ["value", "worst", "thresh", "raw"]
                for item in items:
                    log[attr + "-" + item] = self._int(item, match.group(item), attr)
            return log
        raise TestError("Failed to find vendor specific SMART attributes.")

    def _int(self, item, value: int, attr) -> int:
        """Helper function"""
        try:
            int_value = int(value)
        except Exception:
            msg = "Warning: SMART attribute %s has not updated %s" % (attr, value)
            if item == "thresh":
                # for SSD with SATA interface
                AutovalLog.log_info(msg)
                int_value = 0
            elif item == "raw":
                # Pass as is
                int_value = value
            else:
                raise TestError(msg)
        return int_value

    def _get_phy_event_counters(self, smart_output):
        """
        Get info from 'SATA Phy Event Counters' section in SMART data
        e.g.
            SATA Phy Event Counters (GP Log 0x11)
            ID      Size     Value  Description
            0x0001  2            0  Command failed due to ICRC error
            0x0002  4            0  R_ERR response for data FIS
            ...

        @param str smart_output
        @return dictionary
        """
        log = {}

        cfg_dir = "cfg/" + SATA_CONFIG_DIR
        relative_cfg_file_path = os.path.join(cfg_dir, PHY_EVENT_FIELDS)
        events = GenericUtils.read_resource_cfg(file_path=relative_cfg_file_path).get(
            "events"
        )
        for event in events:
            patt = r"(\d+)\s+{}".format(event)
            match = re.search(patt, smart_output)
            if match:
                log[event] = int(match.group(1))
        return log

    def _get_device_stat(self, smart_output):
        """
        Get info from 'Device Statistics' section of SMART data
        e.g
            Device Statistics (GP Log 0x04)
            Page  Offset Size        Value Flags Description
            0x01  =====  =               =  ===  == General Statistics (rev 2) ==
            0x01  0x030  6        27722663  ---  Number of Read Commands
            ...

        @param str smart_output
        @return dictionary
        """
        log = {}

        cfg_dir = "cfg/" + SATA_CONFIG_DIR
        relative_cfg_file_path = os.path.join(cfg_dir, STAT_FIELDS)
        stats = GenericUtils.read_resource_cfg(file_path=relative_cfg_file_path).get(
            "stats"
        )
        for stat in stats:
            patt = r"(\d+)\s+(?:(-[^-]+-)|[=-]+)\s+{}".format(stat)
            match = re.search(patt, smart_output)
            if match:
                log[stat] = match.group(1)
        return log

    def _get_manufacturer(self, smart_data):
        # LU WWN Device Id: 5 000c50 0b40782b6
        pattern = r"LU WWN Device Id:\s+\w+\s+(\w+)"
        wwn_id = self.extract_smart_field("manufacturer", smart_data, pattern)
        wwn_id = wwn_id.upper()

        cfg_dir = "cfg/" + SATA_CONFIG_DIR
        relative_cfg_file_path = os.path.join(cfg_dir, OUI_WWN_MAPPING)
        vendor_mapping = GenericUtils.read_resource_cfg(
            file_path=relative_cfg_file_path
        )
        if wwn_id not in vendor_mapping:
            raise TestError("/dev/%s WWN ID %s not found" % (self.block_name, wwn_id))
        return vendor_mapping.get(wwn_id)

    def _get_model(self, smart_data):
        pattern = r"Device Model:\s+(\w*.*)"
        return self.extract_smart_field("model", smart_data, pattern)

    def _get_serial_number(self, smart_data):
        pattern = r"Serial Number:\s+(\S+)"
        return self.extract_smart_field("serial number", smart_data, pattern)

    def _get_sector_size(self, smart_data):
        pattern = r"Sector Size(?:s)?:\s+(\S+)"
        return self.extract_smart_field("sector size", smart_data, pattern)

    def format_drive(self, secure_erase_option: int = 0) -> None:
        """Format Drive
        To perform secure erase operation on SATA drive.
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

    def get_rotation_speed(self) -> int:
        """Return drive rotation speed"""
        smart_output = self.get_smartctl_output()
        # Sample line to match:
        # Rotation Rate:    7200 rpm
        patt = r"Rotation Rate:    ([0-9]*) rpm"
        return int(self.extract_smart_field("rotation_speed", smart_output, patt))

    def run_hdd_log_collection(self, tmpdir: str, tmp_dir_path_system_log: str) -> str:
        return tmpdir
