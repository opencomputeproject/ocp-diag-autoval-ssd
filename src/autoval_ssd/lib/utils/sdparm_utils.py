#!/usr/bin/env python3

# pyre-strict

import re

from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_exceptions import TestError


class SdparmUtils:
    @staticmethod
    def get_write_cache(host: Host, drive: str) -> int:
        """
        Retrieves the write cache value for a specific drive on a host.

        This function runs the 'sdparm' command on the host for the specified drive and parses
        the output to find the write cache value. If the value is not found, it raises a TestError.

        Args:
            host: The host on which to run the command.

            drive: The name of the drive for which to get the write cache value.

        Returns:
            The write cache value for the specified drive.

        Raises:
            TestError: If the 'sdparm' command output does not contain the write cache value.

        """
        cmd = "sdparm --get WCE /dev/%s" % (drive)
        output = host.run(cmd)
        pattern = re.compile(r"WCE\s+(\d+)\s+\[cha:\s+\w+", re.MULTILINE)
        match = re.search(pattern, output)
        if match:
            return int(match.group(1))
        else:
            raise TestError(
                "Failed to get write cache. 'sdparm' output: {}".format(output)
            )

    @staticmethod
    def enable_write_cache(host: Host, drive: str, save: bool = False) -> None:
        """
        Enables the write cache for a specific drive on a host.

        This function runs a series of commands on the host to enable the write cache for the specified drive.
        If the 'save' parameter is True, the 'sdparm' command is run with the '--save' flag.

        Args:
            host: The host on which to run the commands.

            drive: The name of the drive for which to enable the write cache.

            save: If True, run 'sdparm' with '--save' flag. Defaults to False.
        """
        directory = "/sys/block/" + drive + "/device/scsi_disk"
        cmd = "ls {}".format(directory)
        scsi_disk = host.run(cmd)
        cache = directory + "/" + scsi_disk + "/cache_type"
        cmd = "echo 'write back' > {}".format(cache)
        host.run(cmd)
        save_arg = "--save" if save else ""
        cmd = "sdparm --set WCE=1 %s /dev/%s" % (save_arg, drive)
        host.run(cmd)

    @staticmethod
    def disable_write_cache(host: Host, drive: str, save: bool = False) -> None:
        """
        Disables the write cache for a specific drive on a host.

        This function runs a series of commands on the host to disable the write cache for the specified drive.
        If the 'save' parameter is True, the 'sdparm' command is run with the '--save' flag.

        Args:
            host: The host on which to run the commands.

            drive: The name of the drive for which to disable the write cache.

            save: If True, run 'sdparm' with '--save' flag. Defaults to False.
        """
        directory = "/sys/block/" + drive + "/device/scsi_disk"
        cmd = "ls {}".format(directory)
        scsi_disk = host.run(cmd)
        cache = directory + "/" + scsi_disk + "/cache_type"
        cmd = "echo 'write through' > {}".format(cache)
        host.run(cmd)
        save_arg = "--save" if save else ""
        cmd = "sdparm --set WCE=0 %s /dev/%s" % (save_arg, drive)
        host.run(cmd)

    @staticmethod
    def get_read_lookahead(host: Host, drive: str) -> int:
        """
        Retrieves the read lookahead value for a specific drive on a host.

        This function runs the 'sdparm' command on the host for the specified drive and parses
        the output to find the read lookahead value. If the value is not found, it raises a TestError.

        Args:
            host: The host on which to run the command.

            drive: The name of the drive for which to get the read lookahead value.

        Returns:
            The read lookahead value for the specified drive.

        Raises:
            TestError: If the 'sdparm' command output does not contain the read lookahead value.
        """
        cmd = "sdparm --get DRA /dev/%s" % (drive)
        output = host.run(cmd)
        pattern = re.compile(r"DRA\s+(\d+)\s+\[cha:\s+\w+", re.MULTILINE)
        match = re.search(pattern, output)
        if match:
            return int(match.group(1))
        else:
            raise TestError(
                "Failed to get read lookahead. 'sdparm' output: {}".format(output)
            )

    @staticmethod
    def enable_read_lookahead(host: Host, drive: str, save: bool = False) -> None:
        """
        Enable read lookahead for the specified drive on the host.

         Args:
            host: The host object representing the remote machine.

            drive: The name of the drive for which to enable read lookahead.

            save: If True, run sdparm with the --save flag. Defaults to False.
            This flag will save the configuration changes made by sdparm to the
            device's persistent storage, making them persist across reboots.

        Note:
            This function uses the `sdparm` utility to control the read lookahead setting of the given
            drive. It executes the command `sdparm --set DRA=1 {save_arg} /dev/{drive}` on the remote
            host, where `{save_arg}` is either `--save` if `save` is True or an empty string otherwise.
            By default, this function does not save the changes to the device's persistent storage. To make
            the changes persistent across reboots, set the `save` argument to True.
        """
        save_arg = "--save" if save else ""
        cmd = "sdparm --set DRA=1 %s /dev/%s" % (save_arg, drive)
        host.run(cmd)

    @staticmethod
    def disable_read_lookahead(host: Host, drive: str, save: bool = False) -> None:
        """
        Disables read lookahead for a specified drive on a given host.

        Args:
            host: The host object representing the remote machine.

            drive: The name of the drive for which to disable read lookahead.

            save: If True, runs sdparm with the --save flag. Defaults to False.

        Note:
            This function disables read lookahead using the `sdparm` command.
            It sets the Direct Read Ahead (DRA) parameter to 0 using the following command:
            "sdparm --set DRA=0 {save_arg} /dev/{drive}"
            Where {save_arg} is "--save" if the save argument is True, and "" otherwise.
        """
        save_arg = "--save" if save else ""
        cmd = "sdparm --set DRA=0 %s /dev/%s" % (save_arg, drive)
        host.run(cmd)
