#!/usr/bin/env python3

# pyre-unsafe
"""Library to manage disks"""
import math
import re
import time
from typing import Dict, List, Optional

from autoval.lib.host.component.component import COMPONENT

from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval_ssd.lib.utils.filesystem_utils import FilesystemUtils
from autoval_ssd.lib.utils.sg_utils import SgUtils


class DiskUtils:
    """Class for DiskUtils"""

    md5 = {}

    @staticmethod
    def get_storage_devices(
        host, drive_type=None, power_on_all_slots: bool = False
    ) -> List[str]:
        """
        This function finds all storage devices (i.e. SSDs and HDDs) excluding
        the boot drive and any other drives that are not considered as storage devices.
        Disk types availbe are "hdd/ssd/md"

        Args:
            host : The host where the storage devices are connected.
            drive_type (str, optional): Type of the storage device to return [ssd/hdd]. Default is None.
            power_on_all_slots (bool, optional): If set True, powers on all jobd drives. Default is False.

        Returns:
            list: A list of storage devices.
        """
        devices_info = {}
        devices = []
        if drive_type == "ssd":
            devices_info = DiskUtils._get_storage_devices(
                host,
                ssd_only=1,
                power_on_all_slots=power_on_all_slots,
            )
        elif drive_type == "hdd":
            devices_info = DiskUtils._get_storage_devices(
                host,
                hdd_only=1,
                power_on_all_slots=power_on_all_slots,
            )
        else:
            devices_info = DiskUtils._get_storage_devices(
                host,
                power_on_all_slots=power_on_all_slots,
            )
        if not devices_info:
            return devices
        if devices_info:
            devices = list(devices_info.keys())
        return devices

    @staticmethod
    def _get_storage_devices(
        host, ssd_only: int = 0, hdd_only: int = 0, power_on_all_slots: bool = False
    ) -> Dict[str, Dict[str, str]]:
        """
        This function returns the list of drives from the Enclosure/RAID and
        Direct Attached drives excluding boot drives.

        Args:
            host : The host where the storage devices are connected.
            ssd_only (int, optional): If set to 1, returns only SSD drives. Default is 0.
            hdd_only (int, optional): If set to 1, returns only HDD drives. Default is 0.
            power_on_all_slots (bool, optional): If set True, powers on all jobd drives. Default is False.

        Returns:
            dict: A dictionary containing the list of drives with detailed information.
            Returns the list of drives from the Enclosure/RAID and Direct Attached drives
            excluding boot drives

        Case 1:
          Returns all storage devices discoved using the below rules

          Step 1: If there Is no controller get the block-devices from lsblk and
                 Identify the bootdrive remove remove from list

          Step 2: If there is a call for ssd/hdd devices exclusively we will
                  filter only the hdd/ssd from the device list obtained
        Case 2:
          Check for all block devices identified using lsblk command and remove
          boot drive from the list and filter for SSD/HDD if user specifies

        """
        if ssd_only:
            extra_flag = "0"
            device_type = "ssd"
        elif hdd_only:
            extra_flag = "1"
            device_type = "hdd"
        else:
            extra_flag = r"\d"
            device_type = None
        encl_devices = DiskUtils._get_storage_expander_devices(
            host, device_type, power_on_all_slots, extra_flag
        )
        devices = DiskUtils._get_storage_lsblk_devices(
            host, device_type, extra_flag, encl_devices
        )
        return devices

    @staticmethod
    def _get_storage_expander_devices(
        host, device_type, power_on_all_slots: bool, extra_flag
    ) -> Dict[str, Dict[str, str]]:
        """
        This function returns all storage drives from the specified enclosure
        and returns a list of dictionaries containing the device type and name of each drive.
        If no drives are found in enclosure, it returns the direct attached drives.

        Args:
            host : The host where the storage devices are connected.
            device_type (str, optional): Type of the storage device to return [ssd/hdd]. Default is None.
            power_on_all_slots (bool, optional): If set True, powers on all jobd drives. Default is False.
            extra_flag (str, optional): Extra flag for lsblk command.

        Returns:
            dict: A dictionary containing the device type and name of each drive.

        Raises:
            TestError: If an error occurs while getting the drives.

        """
        devices = {}
        try:
            devices = DiskUtils._get_storage_lsblk_devices(
                host, device_type, extra_flag, devices
            )
            return devices
        except Exception as exp:
            raise TestError(f"Failed to get drives: {str(exp)}")

    @staticmethod
    def _filter_device_type(devices, device_type) -> dict:
        """
        This function filters the devices dictionary to only include devices of a specific type.
        Args:
            devices (dict): A dictionary containing the device type and name of each drive.
            device_type (str): The type of device to filter for.
        Returns:
            dict: A dictionary containing only the devices of the specified type.
        """
        devices2 = {}
        if devices:
            for dev, value in devices.items():
                if device_type == value["type"]:
                    devices2[dev] = devices[dev]
        return devices2

    @staticmethod
    def _get_storage_lsblk_devices(host, device_type, extra_flag, encl_devices) -> dict:
        """
        This function gets all the drives from a system listed in lsblk and
        returns a list of drives with detailed information such as name,
        type, rotational (to determine if the device is a rotational(HDD) or solid-state drive (SSD),
        size, model and mountpoint.

        Args:
            host : The host object representing the host to get the drives from.
            device_type (str): The type of device to filter by. Default is None.
            extra_flag (str): An extra flag to pass to the lsblk command. Default is None.
            encl_devices (dict): A dictionary of enclosure devices. Default is None.

        Returns:
            dict: A dictionary containing detailed information about the drives on the system.

        Raises:
            TestError: If an error occurs while getting the drives.
        """
        try:
            devices = {}
            cmd = "lsblk -l -o NAME,TYPE,ROTA,SIZE,MODEL,MOUNTPOINT"
            lsblk = host.run(cmd)
            lsblk_devices = re.findall(r"(\w+)\s+disk\s+%s" % extra_flag, lsblk)
            # Filtering the boot drive from the list
            try:
                boot_drive = DiskUtils.get_boot_drive(host)
            except Exception:
                boot_drive = "rootfs"
                AutovalLog.log_info("No boot drive detected, assuming ramdisk")
            if boot_drive in lsblk_devices:
                lsblk_devices.remove(boot_drive)

            devices = DiskUtils._add_drive_details_from_encl(
                host, lsblk_devices, encl_devices
            )
            if device_type:
                devices = DiskUtils._filter_device_type(devices, device_type)
            return devices
        except Exception as exc:
            raise TestError("Failed to get drives: [%s]" % str(exc))

    @staticmethod
    def _add_drive_details_from_encl(host, lsblk_devices, encl_devices) -> dict:
        """
        This function populates drive details from the enclosure if the drives are from raid.

        Args:
            host : The host object representing the host to get the drives from.
            lsblk_devices (list): A list of block devices obtained from lsblk command.
            encl_devices (dict): A dictionary of enclosure devices.

        Returns:
            dict: A dictionary containing information about the drives on the system.
        """
        # Populate drive details from the enclosure if the drives are from raid
        devices = {}

        for lsblk_device in lsblk_devices:
            to_populate_disk = True
            if encl_devices:
                for dev in encl_devices.keys():
                    if lsblk_device == dev:
                        devices[lsblk_device] = encl_devices[dev]
                        to_populate_disk = False
                        break

            if to_populate_disk:
                device = {}
                device["slot"] = "unknown"
                device["type"] = "ssd"
                device["location"] = "local"
                devices[lsblk_device] = device

        return devices

    @staticmethod
    def get_block_devices(host, exclude_boot_drive: bool = True, boot_drive_physical_location: str = ""):
        """
        Return a list of block devices on the system
        @return String[]: e.g. [sda, sdb, sdc ...]
        """
        output = host.run("lsblk -o name,type")
        patt = r"^(nvme\d+n\d+|sd[a-z]*)\s+disk"
        drives = re.findall(patt, output, re.M)
        if not drives:
            raise TestError("Not able to match block devices from lsblk output")
        if exclude_boot_drive:
            if boot_drive_physical_location:
                boot_drive: str = DiskUtils.get_block_from_physical_location(
                    host,
                    [boot_drive_physical_location],
                    DiskUtils.get_block_devices_info(host),
                )
            else:
                boot_drive = DiskUtils.get_boot_drive(host)
            if boot_drive:
                drives.remove(boot_drive)
        return drives

    @staticmethod
    def get_block_devices_info(host) -> List:
        """
        Return a list of block devices on the system
        @return String[]: e.g. [nvme0n1:{}, nvme0n2:{} ...]
        """
        cmd = "lsblk -J"
        lsblk = host.run(cmd)
        lsblk = AutovalUtils.loads_json(lsblk, "%s: json conversion" % cmd)
        return lsblk["blockdevices"]

    @staticmethod
    def get_drive_location(host, drive: str) -> str:
        """
        Get the physical location of the drive from the /sys/block
        The physical location is the last B:D:F, in the /sys/block/<drive>
        eg: ls -la /sys/block/nvme0n1
            /sys/block/nvme0n1 ->
                ../devices/pci0000:00/0000:00:03.3/0000:06:00.0/nvme/nvme0/nvme0n1"
        """
        out = host.run("ls -la /sys/block/%s" % drive)
        location = re.findall(r"(\w*:\w*:\w*\.\w*)", out)
        if location:
            return location[-1]
        raise TestError("Unable to get the physical location for %s" % drive)

    @staticmethod
    def get_block_from_physical_location(
        host: "Host", location: List, devices: List
    ) -> str:
        """
        Get the logical block from drive physical location
        @param Host host : Host Object
        @param List location : List of locations got from golden config
        @param List devices : List of drives
        """
        block_dev = ""
        for device in devices:
            if device["type"] != "disk":
                continue
            drive = device["name"]
            drive_location = DiskUtils.get_drive_location(host, drive)
            if drive_location in location:
                block_dev = drive
                break
        return block_dev

    @staticmethod
    def has_mountpoint(lsblk_entry: Dict) -> bool:
        if "mountpoint" in lsblk_entry and lsblk_entry["mountpoint"] is not None:
            return True
        if "mountpoints" in lsblk_entry:
            for mountpoint in lsblk_entry["mountpoints"]:
                if mountpoint is not None:
                    return True
        return False

    @staticmethod
    def is_drive_mounted(host: "Host", drive: str) -> bool:
        """
        This method will return True if the specified drive is mounted and False otherwise.
        Args:
            host (Host): The autoval Host object representing the host to check for the drive.
            drive (str): The name of the drive to check.
        Returns:
            bool: True if the drive is mounted, False otherwise.
        """
        cmd = "lsblk -J"
        lsblk = host.run(cmd)
        lsblk = AutovalUtils.loads_json(lsblk, "%s: json conversion" % cmd)

        if lsblk["blockdevices"]:
            for device in lsblk["blockdevices"]:
                if device["name"] == drive and DiskUtils.has_mountpoint(device):
                    return True

        partitions = DiskUtils.get_partitions_and_mount_points_in_drive(host, lsblk)
        if drive in partitions:
            for part in partitions[drive]:
                if DiskUtils.has_mountpoint(part):
                    return True
        return False

    @staticmethod
    def get_boot_drive(host, boot_drive_physical_location: str = "") -> str:
        """
        This method will return the boot drive in the host
        @param Host host : Host Object
        @return String  : drive name of boot drive
        """
        boot_drive = ""
        cmd = "lsblk -J"
        lsblk = host.run(cmd)
        lsblk = AutovalUtils.loads_json(lsblk, "%s: json conversion" % cmd)
        # Assuming the /boot mountpoint is for boot drive.
        partition = DiskUtils.get_partitions_and_mount_points_in_drive(host)
        for key, value in partition.items():
            for part in value:
                if "mountpoint" in part and part["mountpoint"] == "/boot":
                    boot_drive = key
                    return boot_drive
                elif "mountpoints" in part and "/boot" in part["mountpoints"]:
                    boot_drive = key
                    return boot_drive
        # For Openbmc
        out = host.run("cat /proc/cmdline")
        match = re.search(r"root=(\S*)\s", out)
        if match:
            if "ram" in match.group(1):
                return boot_drive
        # For Non-Mounted Boot drive, This is needed for hi5
        for device in lsblk["blockdevices"]:
            if device["type"] == "disk":
                out = host.run("file -s /dev/%s" % device["name"])
                if "boot sector" in out:
                    boot_drive = device["name"]
                    AutovalLog.log_info(
                        ("[%s] : Ignoring non-mounted boot drive. " % boot_drive)
                        + "To add this drive to test. Clean the drive."
                    )
                    return boot_drive
        # If the boot drive is not mounted or doesn't have boot-sectors.
        # Filtering the boot drive based on the BOM file
        if boot_drive_physical_location:
            boot_drive = DiskUtils.get_block_from_physical_location(
                host, [boot_drive_physical_location], lsblk["blockdevices"]
            )
        return boot_drive

    @staticmethod
    def get_partitions_and_mount_points_in_drive(
        host, lsblk: Optional[str] = None
    ) -> Dict:
        """
        This method will filter the output of command "lsblk" with only the drives with partition.
        @param Host host : Host Object
        @return Dict  : Dictionary with partitioned drives and their mountpoints.
        """
        if not lsblk:
            cmd = "lsblk -J"
            lsblk = host.run(cmd)
            lsblk = AutovalUtils.loads_json(lsblk, "%s: json conversion" % cmd)
        devices = {
            device["name"]: device["children"]
            for device in lsblk["blockdevices"]
            if device["type"] in ("disk", "md", "raid0") and "children" in device
        }
        return devices

    @staticmethod
    def umount(host, mnt_point: str) -> None:
        """
        Unmount given mount point
        @param String mnt_point: Mount point to unmount
        @return: None. Throws exception on error.
        """
        if FilesystemUtils.is_mounted(host, mnt_point):
            host.run("umount -fl %s" % mnt_point, sudo=True)
            host.run("rmdir %s" % mnt_point)

    @staticmethod
    def create_partition(
        host,
        device,
        mount_point: str = "/mnt/havoc_mnt",
        part_num=None,
        start_pct=None,
        end_pct=None,
        gpt: bool = False,
        script: bool = False,
        script_args: str = "",
    ) -> None:
        """
        Method creates a partition using the parted utility.
        Args:
            device: Device on which to create partition
            part_num: Number of partition (see P* in example below)
            start_pct: Start offset in percentage
            end_pct: End offset in percentage
            gpt: See to True to create GPT
            script: Run everything that follows as a script

        Example use case:
        parted -a optimal /dev/sds mktable gpt --script mkpart P1 0% 5%
        parted -a optimal /dev/sds --script mkpart P2 5% 20%
        parted -a optimal /dev/sds --script mkpart P3 20% 100%
        parted -s /dev/nvme0n1 unit b mkpart primary 128
        """

        # unmount the device before it is partioned
        # unmounts if mounted else just ignore
        if FilesystemUtils.is_mounted(host, mount_point):
            FilesystemUtils.unmount(host, mount_point)
        time.sleep(1)
        if script:
            cmd = "parted -s /dev/%s %s" % (device, script_args)
        else:
            cmd = "parted -a optimal /dev/%s" % device
            if gpt:
                cmd += " mktable gpt"
            cmd += " --script mkpart P%d %d%% %d%%" % (part_num, start_pct, end_pct)
        try:
            host.run(cmd)  # noqa
        except Exception as exc:
            raise TestError("Failed to create partition: " + str(exc))

    @staticmethod
    def _remove_boot_drive_partitions(host, partitions):
        """
        Return a partition list without boot drives from a list of partitions
        @param string[] partitions
        @return string[]
        """
        boot_drive = DiskUtils.get_boot_drive(host)
        # e.g. nvme0n1p1, sda1
        pattern = r"%s[p]?\d+" % boot_drive
        result = []
        for part in partitions:
            if not re.match(pattern, part):
                result.append(part)
        return result

    @staticmethod
    def get_drive_partitions(
        host: "Host", block_name: str, refresh_partitions: bool = True
    ) -> List[str]:
        """Return list of drive partitions"""
        if refresh_partitions:
            host.run("partprobe", timeout=900)
            # Partitions might take more time to come up.
            time.sleep(5)
        cmd = "lsblk -i /dev/%s" % block_name
        out = host.run(cmd)
        # Example:
        #  NAME   MAJ:MIN RM   SIZE RO TYPE MOUNTPOINT
        #  sda      8:0    0 238.5G  0 disk
        #  |-sda1   8:1    0   243M  0 part /boot/efi
        #  |-sda2   8:2    0   488M  0 part /boot
        #  |-sda3   8:3    0   1.9G  0 part [SWAP]
        #  `-sda4   8:4    0 235.9G  0 part /
        pattern = r"(%s\S+).*part" % (block_name)
        partitions = re.findall(pattern, out)
        return partitions

    @staticmethod
    def get_drive_partitions_mountpoint(host: "Host", block_name: str) -> List[str]:
        """
        Example from lslbk output:
            nvme1n1      259:0    0 238.5G  0 disk
            nvme0n1      259:1    0 838.4G  0 disk
            ├─nvme0n1p1  259:2    0  23.3G  0 part /mnt/d0 <- directory
            ├─nvme0n1p2  259:3    0  23.3G  0 part /mnt/d1
            ├─nvme0n1p3  259:4    0  23.3G  0 part /mnt/d2
        """
        mountpoints = []
        cmd = "lsblk -i /dev/%s" % block_name
        out = host.run(cmd)
        for each_line in out.splitlines():
            mount_match = re.search(r"/mnt/d[0-9]+", each_line)
            if mount_match:
                mountpoints.append(mount_match.group(0))
        return mountpoints

    @staticmethod
    def umount_partition(host, part) -> None:
        """
        @param String part: partition to unmount
        """
        umount_command = "umount /dev/%s" % part
        try:
            host.run(umount_command, sudo=True)
            AutovalLog.log_info("Unmounted partition %s" % part)
        except Exception as exc:
            if "not mounted" in str(exc) or "no mount" in str(exc):
                AutovalLog.log_info("Partition %s is not mounted" % part)
            else:
                raise TestError("Fail to umount partition %s: %s" % (part, exc))

    @staticmethod
    def remove_all_partitions(
        host: "Host", device: str, refresh_partitions: bool = True
    ) -> None:
        """Remove all partitions"""
        partitions = DiskUtils.get_drive_partitions(host, device, refresh_partitions)
        for partition in partitions:
            DiskUtils.remove_partition(host, partition)

    @staticmethod
    def remove_partition(host, partition) -> None:
        """
        Method to remove the partition
        Args:
            partition (str): partition to remove
        Returns:
            None
        """
        block_name, part_num = DiskUtils.split_block_and_part_num_from_partition(
            partition
        )
        # unmounts if mounted else just ignore
        DiskUtils.umount_partition(host, partition)
        # remove the partition
        cmd = "yes | parted -a optimal /dev/%s rm %s" % (block_name, part_num)
        try:
            host.run(cmd=cmd)  # noqa
            AutovalLog.log_info("Partition %s is removed" % partition)
        except Exception as exc:
            if "may not reflect" in str(exc):
                AutovalLog.log_info("Partition %s is removed" % partition)
            if "Partition doesn't exist" in str(exc):
                AutovalLog.log_info("There is no existing partition")
            else:
                raise TestError("Failed to remove partition: %s" % partition + str(exc))

    @staticmethod
    def split_block_and_part_num_from_partition(partition):
        """
        Split sdj2 -> (sdj, 2), or nvme1n1p1 -> (nvme1n1, 1)

        @param String partition name: e.g. sda3
        @return tuple: (drive block name, partition number)
        """
        hdd_part_pattern = r"(\w+)(\d+)"  # e.g. sdj4
        nvme_part_pattern = r"(nvme\d+n\d+(?=p(\d+)))"  # e.g. nvme1n1p1
        match = re.match(nvme_part_pattern, partition)
        if match is None:
            match = re.match(hdd_part_pattern, partition)
            if match is None:
                raise TestError(
                    "Failed to get partition number from partition: %s" % partition
                )
        return match.groups()

    @staticmethod
    def get_physical_block_size(host, device) -> int:
        """
        Method to get the physical block size of the drive
        Args:
            device: drive name
        Returns:
            physical block size
        """
        cmd = "cat /sys/block/%s/queue/physical_block_size" % device
        physical_block_size = int(host.run(cmd))
        return physical_block_size

    @staticmethod
    def get_dev_size_bytes(host, device) -> int:
        """
        Method to get the device size in bytes for creating partition
        Args: drive name
        Returns: Drive size in bytes
        """
        out = host.run("cat /proc/partitions")
        pattern = r"(\d+)\s+%s$" % device
        matches = re.search(pattern, out, re.M)
        if matches:
            dev_size = int(matches.group(1))
        else:
            raise TestError("Failed to get drive %s size" % device)
        dev_size_bytes = dev_size * 1024
        return dev_size_bytes

    @staticmethod
    def convert_from_bytes(byte_count, unit):
        """
        Convert capacity from byte unit to other units
        @param int byte_count: drive size in byte
        @param string unit: unit to convert to
        @return float:
        """
        _unit = unit.lower()
        if _unit == "byte":
            size = byte_count
        elif _unit in ("gb", "g"):
            size = (byte_count) / math.pow(10, 9)
        elif _unit in ("tb", "t"):
            size = (byte_count) / math.pow(10, 12)
        elif _unit in ("mb", "m"):
            size = (byte_count) / math.pow(10, 6)
        else:
            raise TestError("{} unit is not supported".format(_unit))
        return size

    @staticmethod
    def convert_to_bytes(drive_size: int):
        """
        Convert TB/GB/MB/KB units to bytes
        @param drive_size: string that is in TB, GB, MB or KB unit.
        For example: '2GB' is the correct format to be passed on.
        """
        if isinstance(drive_size, int) or drive_size.isdigit():
            raise TestError(
                "Error: The input for convert_to_bytes is pure number."
                + " Needs to be in format of 2GB or 2TB or 2MB."
            )
        pattern = r"(?P<size>\d+)(?P<unit>(g|t|m|k))b?"
        match = re.match(pattern, drive_size, re.I)
        if match:
            size = match.group("size")
            unit = match.group("unit")
            if unit.lower() == "t":
                size_in_bytes = int(size) * 1024**4
            if unit.lower() == "g":
                size_in_bytes = int(size) * 1024**3
            if unit.lower() == "m":
                size_in_bytes = int(size) * 1024**2
            if unit.lower() == "k":
                size_in_bytes = int(size) * 1024
            # pyre-fixme[61]: `size_in_bytes` is undefined, or not always defined.
            return size_in_bytes
        raise TestError("Error: Please specify the data in TB, GB, MB or KB")

    @staticmethod
    def get_md5_sum(host_dict, path, key: str = "md5", device=None):
        """
        Get md5, sha1, sha224, sha256, sha384, sha512 sum
        path String: path of file to get md5sum
        device: String: device name sdb or nvme0n1
        key: String: type of hash to calculate
        @return String
        """
        host = host_dict
        if isinstance(host_dict, dict):
            host = Host(host_dict)
        cmd = "%ssum %s" % (key, path)
        out = host.run(cmd=cmd, timeout=36000)
        match = re.match(r"(^\S+)\s*", out)
        if match:
            md5 = match.group(1)
            if device is not None:
                DiskUtils.md5[device] = md5
            return md5
        raise TestError("Failed to find md5sum in %s" % out)

    @staticmethod
    def ramdisk(
        host,
        action,
        size: int = 1,
        fs: str = "tmpfs",
        path: str = "/mnt/havoc_test_ramdisk",
    ) -> str:
        """
        path: absolute path of ramdisk
        size: size of ramdisk (e.g. "32g")
        fs: tmpfs, ramfs
        action: "create" or "delete"
        """
        if "create" == action:
            host.run(
                "umount %s; rm -rf %s" % (path, path), ignore_status=True, sudo=True
            )
            host.run("mkdir -p %s" % path)
            cmd = "mount -t %s -o mode=1777,size=%s %s %s" % (fs, size, fs, path)
            host.run(cmd, sudo=True)
        elif "delete" == action:
            cmd = "rm -rf %s/*; umount %s; rm -rf %s/" % (path, path, path)
            host.run(cmd, ignore_status=True)
        else:
            raise TestError("Action %s not supported" % action)
        return path

    @staticmethod
    def get_seconds(_time) -> int:
        """Convert human time to integer"""
        try:
            size = int(_time)
        except Exception:
            match = re.search(r"(\d+)(\w*)", _time)
            if match is not None:
                size = int(match.group(1))
                unit = match.group(2)
                if unit is not None:
                    unit = unit.lower()
                    if unit == "s":
                        return size
                    if unit == "m":
                        return size * 60
                    if unit == "h":
                        return size * 3600
                    if unit == "d":
                        return size * 3600 * 24
                    if unit == "w":
                        return size * 3600 * 24 * 7
            raise TestError(f"Unable to convert {_time} to seconds")
        return size

    @staticmethod
    def get_bytes(_size):
        """Convert human size to integer"""
        try:
            size = int(_size)
        except Exception:
            match = re.search(r"(\d+)(\w*)", _size)
            if match is not None:
                size = int(match.group(1))
                unit = match.group(2)
                if unit is not None:
                    unit = unit.lower()
                    if unit in ("kib", "k"):
                        return size << 10
                    if unit == "kb":
                        return size * pow(10, 3)
                    if unit in ("mib", "m"):
                        return size << 20
                    if unit == "mb":
                        return size * pow(10, 6)
                    if unit in ("gib", "g"):
                        return size << 30
                    if unit == "gb":
                        return size * pow(10, 9)
                    if unit in ("tib", "t"):
                        return size << 40
                    if unit == "tb":
                        return size * pow(10, 12)
            raise TestError(f"Unable to convert {_size} to bytes")
        return size

    @staticmethod
    def get_size_of_directory(host, dir_path, size_in_unit: str = "K") -> int:
        """Return size of directory"""
        if size_in_unit == "b":
            cmd = "du -shb %s" % dir_path
        else:
            cmd = "du -sh --block-size=%s %s" % (size_in_unit, dir_path)
        output = host.run(cmd)
        pattern = re.compile(r"(\d+)")
        match = re.search(pattern, output)
        if match:
            return int(match.group(1))
        raise TestError("No match for directory size found, check if directory exists")

    @staticmethod
    def create_file(
        host,
        path,
        size,
        tool: str = "fallocate",
        bs: str = "1k",
        additional_options=None,
        timeout: int = 3600,
    ):
        """Create file"""
        # For size in human format
        if not isinstance(size, int):
            size = DiskUtils.get_bytes(size)
        if tool == "fallocate":
            cmd = "fallocate -l %s %s" % (size, path)
        elif tool == "dd":
            blocks = int(size / DiskUtils.get_bytes(bs))
            cmd = "dd if=/dev/urandom of=%s bs=%s count=%d" % (path, bs, blocks)
        else:
            raise TestError("tool '%s' not supported" % tool)
        if additional_options is not None:
            cmd += " %s" % additional_options
        out = host.run(cmd=cmd, timeout=timeout)
        return out

    @staticmethod
    def calculate_min_size_of_drives(
        host: "Host", percent_write_size: int, drive_list: List[str]
    ) -> str:
        """
        This function calculates the minimum size to be written on the drive.
        First it gets the drive list, then calculates a percentage size of all,
        drives and returns the minimum size value.
        For example, if a user want to write 10% of the drive,
        the input will be 10,it will calculate 10% size on all drives,
        and returns the minimum possible size.

        Parameters
        ----------
        host : :obj: 'Host'
           host : :obj: 'Host'
        percent_write_size: Integer
           FIO write to be written Ex: 5
        drive_list: :obj: 'list' of :obj: 'str'
           List of Drives

        Returns
        -------
        final_size_to_write : String
            size to update in FIO ,Ex: 10gb
        """

        final_size = []
        for device in drive_list:
            size = DiskUtils.get_dev_size_bytes(host, device)
            take_capacity = percent_write_size / 100 * size
            final_size.append(take_capacity)
        final_size = min(final_size)
        converted_size = DiskUtils.convert_from_bytes(final_size, "gb")
        final_size_to_int = int(converted_size)
        final_size_to_write = str(final_size_to_int) + "gb"
        return final_size_to_write

    @staticmethod
    def get_md5_for_drivelist(
        host: "Host",
        drive_path_map: Dict[str, str],
        parallel: bool = True,
        key: str = "md5",
    ) -> Dict[str, str]:
        """
        This function will get the md5 values for all the devices sent.This will work
        for both filesystem and for raw disk.

        Parameters
        ----------
        host : :obj: 'Host'
           host : :obj: 'Host'
        drive_path_map: : Dict of :obj: 'str' of :obj: 'str'
           Dict of drive and path.
        path: String
           Path eg. /mnt/fio_test_%s/file1
        key: String
            md5, sha1, sha224, sha256, sha384, sha512

        Returns
        -------
        DiskUtils.md5: dictionary
           Drive name is key and md5 is value.
        """
        if key not in ["md5", "sha1", "sha224", "sha256", "sha384", "sha512"]:
            key = "md5"
        threads = []
        host_dict = AutovalUtils.get_host_dict(host)
        for device, path in drive_path_map.items():
            if parallel:
                threads.append(
                    AutovalThread.start_autoval_thread(
                        DiskUtils.get_md5_sum, host_dict, path, device=device, key=key
                    )
                )
            else:
                DiskUtils.get_md5_sum(host, path, device=device, key=key)
        AutovalThread.wait_for_autoval_thread(threads)
        return DiskUtils.md5

    @staticmethod
    def drop_cache_emmc(host) -> None:
        """
        Method to drop cache on eMMC device
        """
        try:
            host.oob.bmc_host.run("echo 1 > /proc/sys/vm/drop_caches")
        except Exception as exc:
            AutovalLog.log_info(f"Failed to drop cache: {exc}")

    @staticmethod
    def list_scsi_devices(host):
        """Return list of scsi devices"""
        devices = []
        op = host.run("lsscsi -g")
        pattern = r"(\[\w*.*\])\s*(\w*)\s*\w*.*(\/dev\/\w*)\s*(\/dev\/\w*)"
        for line in op.split("\n"):
            device = {}
            match = re.search(pattern, line)
            if match:
                device = {
                    "channel_target_lun": match.group(1),
                    "type": match.group(2),
                    "device": match.group(3).split("/")[2],
                    "sg_device": match.group(4).split("/")[2],
                }
                devices.append(device)
        boot_drive = DiskUtils.get_boot_drive(host)
        # Exclude boot drive record from devices
        for i in range(len(devices)):
            if devices[i]["device"] == boot_drive:
                del devices[i]
                break
        return devices

    @staticmethod
    def delete_partitions(host, device, bs=None) -> None:
        """Delete partitions"""
        # Delete MBR table
        cmd = "dd if=/dev/zero of=/dev/%s bs=446 count=1 seek=0" % device
        host.run(cmd)
        # Delete Partition table
        if bs is None:
            bs = SgUtils.get_hdd_lb_length(host, device)
        cmd = "dd if=/dev/zero of=/dev/%s bs=%s count=1 seek=0" % (device, bs)
        host.run(cmd)

    @staticmethod
    def format_hdd(host, device, secure_erase_option: int = 0) -> None:
        """Format HDD"""
        # Swipe full drive, takes long time
        if secure_erase_option == 0:
            cmd = "dd if=/dev/urandom of=/dev/%s bs=1M" % device
        else:
            cmd = "shred -vfz /dev/%s" % device
        host.run(cmd, timeout=43200)

    @staticmethod
    def remove_drives(host, drives) -> None:
        """Power-off all data drives"""
        AutovalLog.log_info(f"{host.hostname}: Powering-off all drives")
        # SSD drives
        for drive in drives:
            if drive.type.value == "ssd" and str(drive):
                AutovalLog.log_info(f"{host.hostname}: Power-off {drive}")
                cmd = f"ls -l /sys/block/{drive}"
                out = host.run(cmd=cmd)
                if "nvme" in str(drive):
                    p = r"(\d+\:\w+\:\w+\.\w+)\/nvme"
                else:
                    p = r"(\d+\:\w+\:\w+\.\w+)\/ata"
                match = re.search(p, out)
                if match:
                    cmd = f"echo 1 > /sys/bus/pci/devices/{match.group(1)}/remove"
                    host.run(cmd=cmd)

    @staticmethod
    def rescan_drives(host, drives) -> None:
        """Power-on all data drives"""
        AutovalLog.log_info(f"{host.hostname}: Powering-on all drives")
        # SSD drives
        for drive in drives:
            if drive.type.value == "ssd" and str(drive):
                AutovalLog.log_info(f"Power-on {drive}")
                host.run(cmd="echo 1 > /sys/bus/pci/rescan")
                time.sleep(60)
                break

    @staticmethod
    def check_drive_health(drive_status_data):
        """
        This function will check the data drive status and check which drive
        is in abnormal state.
        Test cannot run be run on bad drives so will raise a test error if drive is
        in abnormal state
        """
        abnormal_drives = {}
        normal_drives = {}
        not_supported = {}
        for data in drive_status_data.split("\n"):
            if ":" in data:
                final_data = data.split(":")
                if "Normal" in final_data[1]:
                    normal_drives[final_data[0]] = final_data[1]
                elif "NA" in final_data[1]:
                    not_supported[final_data[0]] = final_data[1]
                elif "Abnormal" in final_data[1]:
                    abnormal_drives[final_data[0]] = final_data[1]
        if abnormal_drives:
            raise TestError(
                message=f"Following drives are in bad state: {abnormal_drives}",
                error_type=ErrorType.DRIVE_ERR,
                component=COMPONENT.STORAGE_DRIVE,
            )
        if not_supported:
            AutovalLog.log_info(
                f"Drive not supported by enclosure-util: {not_supported}"
            )
        if not normal_drives and not not_supported:
            raise TestError(
                message=f"Normal drives are absent: {drive_status_data}",
                error_type=ErrorType.DRIVE_ERR,
                component=COMPONENT.STORAGE_DRIVE,
            )
        AutovalLog.log_info(f"All data drives are in good state: {normal_drives}")

    @staticmethod
    def remove_mount_points(host, block_name) -> None:
        """
        Method to remove mount points on the host in order to prevent
        fio from running on filesystem.
        """
        mount_points = DiskUtils.get_mount_points(host, block_name)
        for mount_point in mount_points:
            DiskUtils.umount(host, mount_point)

    @staticmethod
    def get_mount_points(host, block_name) -> List:
        """
        Method to get list of mount points available on the drive.
        Example:
            1. /mnt/fio_test_nvme0n1/file_1
            2. /mnt/havoc_mnt
        """
        cmd = f"lsblk -i /dev/{block_name}"
        out = host.run(cmd)  # noqa
        mountpoints = []
        pattern = r"/mnt/[\S]+"
        for line in out.splitlines():
            mount_point = re.search(pattern, line)
            if mount_point:
                mountpoints.append(mount_point.group(0))
        return mountpoints
