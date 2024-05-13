#!/usr/bin/env python3

# pyre-unsafe
"""Utility to manage filesystems"""
import re
import time
from typing import Dict, List, Optional

from autoval.lib.connection.connection_utils import CmdResult  # noqa
from autoval.lib.host.component.component import COMPONENT
from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import AutoValException, CmdError, TestError
from autoval.lib.utils.decorators import retry

RETRY_COUNT = 2
RETRY_SLEEP_TIME = 30


class FilesystemUtils:
    """Class for Filesystem utils"""

    @staticmethod
    def create_filesystem(
        host: Host, device: str, filesystem_type: str, options: str
    ) -> str:
        """
        Creates filesystem with give FS type
        @param device: Device on which to create filesystem
        @param type: FS type. Default: ext4
        @return Output of mkfs command. Throws exception on error.
        """
        if filesystem_type in ("xfs", "btrfs"):
            force = "-f"
        else:
            force = "-F"
        ret_val = ""
        cmd = "mkfs.%s %s %s /dev/%s" % (filesystem_type, force, options, device)
        try:
            ret_val = host.run(cmd)
        except CmdError as exc:
            raise AutoValException(
                message=f"Failed to create file system. Error : {str(exc)}",
                error_type=ErrorType.DRIVE_ERR,
                component=COMPONENT.STORAGE_DRIVE,
            )
        return ret_val

    @staticmethod
    def unmount(
        host: Host,
        mnt_point: str,
        ignore_status: bool = False,
    ) -> None:
        """
        Unmount given mount point
        @param mnt_point: Mount point to unmount
        @return: None. Throws exception on error.
        """
        host.run("umount -fl %s" % mnt_point, sudo=True, ignore_status=ignore_status)
        host.run("rmdir %s" % mnt_point, ignore_status=ignore_status)

    @staticmethod
    @retry(RETRY_COUNT, RETRY_SLEEP_TIME)
    def re_mount_fs_tab_mount(host: Host, mnt_point: str) -> None:
        """
        Remount a mount point in fstab
        @param mnt_point: Mount point to mount
        @return: None. Throws exception on error.
        """
        FilesystemUtils.unmount(host, mnt_point, ignore_status=True)
        time.sleep(5)
        host.run(f"mkdir -p {mnt_point}")
        host.run(f"mount {mnt_point}", sudo=True)

    @staticmethod
    @retry(RETRY_COUNT, RETRY_SLEEP_TIME)
    def mount(
        host_dict: Dict,
        device: str,
        mnt_point: str,
        mnt_options: Optional[str] = None,
        filesystem_type: str = "ext4",
        filesystem_options: str = "",
        force_mount: Optional[bool] = True,
    ) -> None:
        """
        Mount device at mnt_point. First unmounts mount point if it already
        exists. Creates mnt_point directory if it doesn't exist.
        @param device: Device to mount
        @param mnt_point: Mount point to use
        @param options: Mount options to use. Default: None
        @return: None. Throws exception on error.
        @param force_mount: If true, then filesystem will be created on device
        before mounting
        """
        if isinstance(host_dict, dict):
            host = Host(host_dict)
        else:
            host = host_dict
        cmd = "mountpoint -q %s && echo 'mounted'" % mnt_point
        output = host.run(cmd, ignore_status=True)
        if output == "mounted":
            FilesystemUtils.unmount(host, mnt_point)
        # makedirectory where the device need to be mounted
        try:
            cmd = "mkdir -p %s" % mnt_point
            host.run(cmd)
        except Exception:
            cmd = "rm -r %s" % mnt_point
            host.run(cmd)
        if force_mount:
            FilesystemUtils.create_filesystem(
                host, device, filesystem_type, filesystem_options
            )
        cmd = "mount "
        if mnt_options:
            cmd += "-o %s " % mnt_options
        cmd += "/dev/%s %s" % (device, mnt_point)
        host.run(cmd=cmd, sudo=True)

    @staticmethod
    def get_df_info(host: Host, device: str, search: Optional[str] = None) -> Dict:
        """
        Retrieves df -T output for device and parses it into dictionary
        search - key to search in output.

        # Example output:
        # Filesystem     Type     1B-blocks     Used    Available Use% Mounted
        # /dev/sdg       ext4 1008004698112 75046912 956702400512   1%
        # /mnt/havoc_sdg
        """
        """
        if (search == "/") and host.is_container:
            # root filesystem check, in container environment drive mount points are not available, just check root folder.
            cmd = "df -B 1 -T /"
        else:
        """
        cmd = "df -B 1 -T /dev/%s*" % device
        out = host.run(cmd)
        pattern = r"(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)"
        df_info = {}
        for line in out.splitlines():
            match = re.search(pattern, line)
            if match:
                key = match.group(1)
                if key != "Filesystem":
                    df_info[key] = {}
                    df_info[key]["type"] = match.group(2)
                    # number of 1 Byte blocks
                    df_info[key]["1b_blocks"] = int(match.group(3))
                    df_info[key]["used"] = int(match.group(4))
                    # size in bytes
                    df_info[key]["available"] = int(match.group(5))
                    df_info[key]["use_pct"] = match.group(6)
                    df_info[key]["mounted_on"] = match.group(7)
            else:
                raise TestError("Failed to get df info from: \n%s" % out)
        # Filter output
        for key, value in df_info.items():
            if search is None:
                if "devtmpfs" in key or str(device) in key:
                    return value
            else:
                for _key, value2 in value.items():
                    if search == value2:
                        return value
        return df_info

    @staticmethod
    def fstrim(host: Host, path: str) -> str:
        """
        Discard unused blocks on a mounted filesystem
        """
        cmd = "fstrim -v %s" % (path)
        return host.run(cmd)

    @staticmethod
    def clean_filesystem(
        host: Host, device: str, mnt_point: Optional[str] = None
    ) -> None:
        """
        Erase filesystem from the device(e.g: /dev/sdb)
        """
        if mnt_point:
            if FilesystemUtils.is_mounted(host, mnt_point):
                FilesystemUtils.unmount(host, mnt_point)
        cmd = "dd if=/dev/zero of=/dev/%s bs=1M count=2" % device
        host.run(cmd)

    @staticmethod
    def is_mounted(host: Host, path: str) -> bool:
        """
        Return true if a given path is mounted

        @param string path:
        @return boolean
        """
        ret = host.run_get_result("mountpoint %s" % path, ignore_status=True)
        if ret.return_code != 0:
            return False
        return True

    @staticmethod
    def mount_all(
        host: Host,
        drive_list: List[str],
        mnt: str,
        mnt_options: str = "",
        fstype: str = "",
        filesystem_options: Optional[str] = "",
        force_mount: Optional[bool] = False,
    ) -> None:
        """
        This function will mount all ithe drives for the given mount path.

        Parameters
        ----------
        drive_list: :obj: 'list' of :obj: 'str'
           List of drives.
        mnt: String
           the mount path :eg :"/mnt/fio_test_%s/"
        mnt_option : String
           mount options to use, default is None.
        fstype: String
           file system type, eg : ext4, xfs
        filesystem_options : String
           filesystem options eg : " -K -i size=2048"
        force_mount : String
           force mount option to use, default is False.
        """
        for device in drive_list:
            FilesystemUtils.mount(
                host,
                device,
                mnt % device,
                mnt_options,
                fstype,
                filesystem_options,
                force_mount,
            )

    @staticmethod
    def unmount_all(host: Host, drive_list: List[str], mnt: str) -> None:
        """
        This function will unmount for all drives for the given mount path
        and clean the filesystem.

        Parameters
        ----------
        drive_list: :obj: 'list' of :obj: 'str'
           List of drive
        mnt : String
           the mount path eg :"/mnt/fio_test_%s/"
        """
        for device in drive_list:
            FilesystemUtils.clean_filesystem(host, device, mnt % device)

    @staticmethod
    def create_zero_file(
        host: Host,
        file_path: str,
        blocksize: Optional[str] = None,
        count: Optional[str] = None,
    ) -> str:
        """
        dd command is logged to copy files of /dev/zero nature
        to file_path Destination
        with 'blocksize' and 'count' as optional arguments
        """
        cmd = f"dd if=/dev/zero of={file_path}"
        if blocksize is not None:
            cmd += f" bs={blocksize}"
        if count is not None:
            cmd += f" count={count}"
        return host.run(cmd)
