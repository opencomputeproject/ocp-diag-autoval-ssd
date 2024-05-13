#!/usr/bin/env python3

# pyre-unsafe
"""library for MD ADM Utils"""
import re
import time

from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils

from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.filesystem_utils import FilesystemUtils

MDADM = "mdadm %s"
MD_SUPER_BLOCK_CLEAN = "mdadm --zero-superblock --force %s"
MD_SET_SYNC = "/sys/block/%s/md/sync_action"
SYNC_ACTION_RAID_LEVELS = ["raid1", "raid5", "raid6"]
CHECKRAID6 = "/opt/mdadm-master/raid6check"
DRIVE_FLAGS = {
    "W": "write_mostly",
    "F": "faulty",
    "S": "spare",
    "R": "replacement",
    "J": "journal",
}


class MDUtils:
    """
    Utility to manage MD devices with support of mdadm tool
    """

    @staticmethod
    def list_md_arrays(host):
        """
        Method gets detail info, including array state and participating drive state
        of md array.
        Args: None
        Returns: Dictionary of md array details
        """
        array_details = {}
        cmd = "cat /proc/mdstat"
        output = MDUtils._exec_md_cmd(host, cmd)
        for line in output.splitlines():
            array = MDUtils._parse_md_details(host, line)
            if array:
                array_details.update(array)
        return array_details

    @staticmethod
    def get_md_detail(host, device):
        """
        Method gets detailed status of a particular raid using the mdadm command
        Args:
            device: md raid device name
        Returns: md details
        """
        cmd = "mdadm --detail /dev/%s" % device
        md_details = MDUtils._exec_md_cmd(host, cmd)
        return md_details

    @staticmethod
    def check_for_active_array(host) -> bool:
        """
        Method to check for state of md array
        Returns: False if no array is available.
        True if all the arrays in the system are active else raises TestError
        """
        mds = MDUtils.list_md_arrays(host)
        if not mds:
            return False
        for array, md_array in mds.items():
            if md_array["state"] != "active":
                raise TestError("Array '%s' is not in active state" % array)
        return True

    @staticmethod
    def clean_md_super_block(host, devices):
        """
        Method to overwrite md meta with zeros
        Args:
            devices: list of md devices to clean metadata
        Returns: True
        """
        for device in devices:
            cmd = MD_SUPER_BLOCK_CLEAN % f"/dev/{device}"
            MDUtils._exec_md_cmd(host, cmd)

    @staticmethod
    def readd_drive_to_md_array(host, array_device, drive) -> bool:
        """
        Method to re-add the md drive
        """
        cmd = "mdadm --manage /dev/%s --re-add %s" % (array_device, drive)
        MDUtils._exec_md_cmd(host, cmd)
        return True

    @staticmethod
    def create_md_array(host, raid_options, devices, force: bool = True):
        """
        Method creates a new md array based on given raid create options
        Args:
            raid_options: All  options available in  'mdadm --create --help
            devices: list of md devices
            force: set to true if you insist that mdadm run the array, even if
            some of the components appear to be active in another array or filesystem
        Returns: raid_device created
        """
        raid_device = raid_options["create"].split("/")[-1]
        params = MDUtils._generate_raid_create_cmd(raid_options, devices, force)
        # clean md super block
        MDUtils.clean_md_super_block(host, devices)
        if "write-journal" in raid_options:
            MDUtils.clean_md_super_block(
                host, [raid_options["write-journal"].split("/")[-1]]
            )
        # Format drives
        for device in devices:
            device.format()
        cmd = MDADM % params
        MDUtils._exec_md_cmd(host, cmd)
        return raid_device

    @staticmethod
    def remove_md_array(host, raiddevice) -> bool:
        """
        Method deactivates and removes md array
        Args:
            raiddevice str: raiddevice to be removed
        Returns: True
        """
        # Clean md_superblock before removing the array
        arrays = MDUtils.list_md_arrays(host)
        if raiddevice not in arrays:
            return False
        d_f = FilesystemUtils.get_df_info(host, raiddevice)
        if "md0" in raiddevice and d_f["mounted_on"] == "/dev":
            # Ignore md0 partition mounted on root /
            return True
        cmd = MDADM % ("--stop /dev/") + raiddevice
        MDUtils._exec_md_cmd(host, cmd)
        MDUtils.clean_md_super_block(host, arrays[raiddevice]["drive"])
        cmd = MDADM % ("--remove /dev/") + raiddevice
        MDUtils._exec_md_cmd(host, cmd, ignore_status=True)
        AutovalLog.log_info("Deleted array %s" % raiddevice)
        return True

    @staticmethod
    def disable_md_automount(host) -> None:
        """
        Method to disable auto-assembly of raid arrays
        Args: None
        Returns: None
        """
        host.run('echo "AUTO -all" > /etc/mdadm.conf', ignore_status=True)

    @staticmethod
    def validate_sync_action(host, md_device, sync_action, raid_level) -> bool:
        """
        Method to validate the md sync async action with the expected results
        Args:
            md_device: raid_device
        Returns: True if validated successfully
        """
        _sync_action = MDUtils.get_md_sync_action(host, md_device, raid_level)
        AutovalUtils.validate_equal(
            _sync_action, sync_action, "Validate '%s' sync_action" % md_device
        )
        return True

    @staticmethod
    def remove_all_md_arrays(host) -> None:
        """Remove all md arrays"""
        arrays = MDUtils.list_md_arrays(host)
        for device in arrays:
            MDUtils.remove_md_array(host, device)

    @staticmethod
    def get_md_mount_point(host, raid_device):
        """
        @param host Host
        @param raid_device str
        @return str
        """
        mnt_point = ""
        if not raid_device:
            return mnt_point
        match = re.search(
            #   └─md0     /data/path/then_some_more_path
            #   `-md0     /data/path/then_some_more_path
            rf"(?:└─|`-){raid_device}\s+((?:\/\w+)+)",
            host.run("lsblk -o name,mountpoint"),
        )
        if match:
            mnt_point = match.group(1)
        return mnt_point

    @staticmethod
    def get_md_sync_action(host, raid_device, raid_level):
        """Get md sync async action"""
        try:
            cmd = "cat " + MD_SET_SYNC % raid_device
            return MDUtils._exec_md_cmd(host, cmd)
        except Exception as exc:
            if raid_level in SYNC_ACTION_RAID_LEVELS:
                raise exc
            return "NotEnabled"

    @staticmethod
    def set_md_sync_action(host, raid_device, action, raid_level) -> None:
        """Set md sync action"""
        cmd = "echo " + action + " > " + MD_SET_SYNC % raid_device
        if raid_level in SYNC_ACTION_RAID_LEVELS:
            AutovalUtils.validate_condition(
                MDUtils._exec_md_cmd(host, cmd), "Set md sync action as '%s'" % action
            )

    @staticmethod
    def setup_md_raid0(
        host,
        devices,
        raiddevice: str = "md125",
        fstype: str = "xfs",
        mount_point: str = "/mnt/havoc_md125",
        stripe_size: int = 128,
    ) -> None:
        """
        Method to setup mdraid0 if multiple drives
        Args:
            devices: list of devices for RAID
            raiddevice: devname to mdadm
            fstype: file system type, default xfs
            mount_point: mouting point
            stripe_size: stripe size in KB
        Returns: None
        """
        # First delete existing mdraid array
        MDUtils.remove_md_array(host, raiddevice)
        # Remove unwanted partitions
        if FilesystemUtils.is_mounted(host, mount_point):
            AutovalLog.log_info("Unmounting %s" % mount_point)
            FilesystemUtils.unmount(host, mount_point)
        partition_list = []
        MDUtils.disable_md_automount(host)
        for device in devices:
            AutovalLog.log_info("Removing partitions from device %s" % device)
            DiskUtils.remove_all_partitions(host, device)
            dev_size_bytes = DiskUtils.get_dev_size_bytes(host, device)
            DiskUtils.create_partition(
                host,
                device,
                mount_point=mount_point,
                script=True,
                script_args="mklabel gpt",
            )
            # start 1Mib or stripe size to make aligned
            start_position = stripe_size * 1024
            DiskUtils.create_partition(
                host,
                device,
                mount_point=mount_point,
                script=True,
                script_args="unit b mkpart primary %s %s"
                % (str(start_position), str(dev_size_bytes - start_position)),
            )
            DiskUtils.create_partition(
                host,
                device,
                mount_point=mount_point,
                script=True,
                script_args="set 1 raid",
            )
            partition_list.append(DiskUtils.get_drive_partitions(host, device)[0])
        AutovalLog.log_info("Creating RAID in partitions %s" % partition_list)
        time.sleep(5)
        # Now create raid volume and load XFS
        level = "0"
        raid_parms = {
            "create": "/dev/%s" % raiddevice,
            "metadata": "1.2",
            "chunk": str(stripe_size),
            "level": level,
        }
        raid_device = MDUtils.create_md_array(host, raid_parms, partition_list)
        AutovalLog.log_info("MD created: %s" % raid_device)
        log_stripe_unit = DiskUtils.get_physical_block_size(host, raiddevice)
        # Create filesystem and Mount raid onto /mnt/havoc_md125
        FilesystemUtils.mount(
            host,
            raiddevice,
            mount_point,
            mnt_options="noatime,nodiratime,discard,nobarrier ",
            filesystem_type=fstype,
            filesystem_options="-K -i size=2048 -d su=%s,sw=2 -l su=%s"
            % (stripe_size * 1024, log_stripe_unit),
        )
        d_f = FilesystemUtils.get_df_info(host, raiddevice)
        AutovalLog.log_info(d_f)

    @staticmethod
    def cleanup_md_raid0(host, partition_list, raiddevice: str = "md125") -> None:
        """
        Method deletes RAID volume of a given list of drives
        """
        d_f = FilesystemUtils.get_df_info(host, raiddevice)
        if "md0" in raiddevice and d_f["mounted_on"] == "/dev":
            # Ignore md0 partition mounted on root /
            return
        host.run("umount /dev/%s" % raiddevice, sudo=True, ignore_status=True)
        MDUtils.remove_md_array(host, raiddevice)
        for partition in partition_list:
            host.run("yes | parted -s /dev/%s rm 1" % partition, ignore_status=True)

    @staticmethod
    def _exec_md_cmd(host, cmd, ignore_status: bool = False, working_directory=None):
        md_output = host.run(
            cmd, ignore_status=ignore_status, working_directory=working_directory
        )
        return md_output

    @staticmethod
    def _generate_raid_create_cmd(params, devices, force) -> str:
        cmd = ""
        for param, value in params.items():
            cmd += "--" + param + " " + value + " "
        if force:
            cmd += " --run"
        # Appending devices to md create cmd
        cmd += (
            " --raid-devices "
            + str(len(devices))
            + " "
            + "/dev/"
            + " /dev/".join(devices)
        )
        AutovalLog.log_info(
            "Create RAID%s %s on %s "
            % (params["level"], params["create"], "  ".join(devices))
        )
        return cmd

    @staticmethod
    def _get_drive_from_mdstat(line):
        flag = "active"
        drive = {}
        name, line = line.split("[")
        number, line = line.split("]", 1)
        for key in DRIVE_FLAGS:
            if key in line:
                flag = DRIVE_FLAGS[key]
        drive[name] = {"number": int(number), "flag": flag}
        return drive

    @staticmethod
    def _parse_md_details(host, output):
        level = None
        drive = {}
        raid = {}
        lines = output.split()
        if not lines:
            return raid
        name = lines.pop(0)
        if not name.startswith("md"):
            return raid
        lines.pop(0)
        # Pulling Array state
        active = lines.pop(0)
        read_only = False
        if lines[0] in ["(read-only)", "(auto-read-only)"]:
            lines.pop(0)
            read_only = True
        # Pulling Array level
        if "[" not in lines[0]:
            level = lines.pop(0)
        if "[" in lines[0]:
            for line in lines:
                drive.update(MDUtils._get_drive_from_mdstat(line))
        raid[name] = {
            "state": active,
            "read_only": read_only,
            "level": level,
            "drive": drive,
        }
        sync_action = MDUtils.get_md_sync_action(host, name, level)
        raid[name]["sync_action"] = sync_action
        return raid
