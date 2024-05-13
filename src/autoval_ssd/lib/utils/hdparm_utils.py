#!/usr/bin/env python3

# pyre-strict
"""
library to manage drives by Hdparm utils
"""
import re

from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_exceptions import TestError


class HdparmUtils:
    """
    Class for Hdparm utils
    """

    @staticmethod
    def get_write_cache(host: Host, drive: str) -> int:
        """
        Retrieves the write cache status of a specified drive on a given host.

        This function runs the 'hdparm' command on the specified drive and parses the output
        to find the write cache status. If the status is found, it is returned as an integer.
        If not, a TestError is raised.

        Args:
            host: The host on which the drive is located.

            drive: The name of the drive for which to retrieve the write cache status.

        Returns:
            The write cache status of the specified drive.

        Raises:
            TestError: If the 'hdparm' command does not return a write cache status.
        """
        cmd = "hdparm -W /dev/%s" % (drive)
        output = host.run(cmd)
        pattern = re.compile(r"write-caching =\s+(\d+)", re.MULTILINE)
        match = re.search(pattern, output)
        if match:
            return int(match.group(1))
        raise TestError("Failed to get write cache. 'hdparm' output: {}".format(output))

    @staticmethod
    def enable_write_cache(host: Host, drive: str, save: bool = False) -> None:
        """
        Enables the write cache for a specified drive on a given host.

        This function modifies the cache type of the specified drive to 'write back', effectively enabling the write cache.
        It also runs the 'hdparm' command to ensure the write cache is enabled. If the 'save' parameter is set to True,
        the changes are saved.

        Args:
            host: The host on which the drive is located.

            drive: The name of the drive for which to enable the write cache.

            save: Whether to save the changes. Defaults to False.
        """
        directory = f"/sys/block/{drive}/device/scsi_disk"
        cmd = "ls {}".format(directory)
        scsi_disk = host.run(cmd=cmd)
        cache = f"{directory}/{scsi_disk}/cache_type"
        cmd = f"echo 'write back' > {cache}"
        host.run(cmd=cmd)
        cmd = f"hdparm -W1 /dev/{drive}"
        host.run(cmd=cmd)

    @staticmethod
    def power_sleep_hdd(host: Host, drive: str) -> None:
        """
        Sets the power sleep mode on a specified drive on a given host.

        This function runs the 'hdparm' command with the '-Y' option on the
        specified drive, which sends the drive into a low power sleep mode.

        Args:
            host: The host on which the drive is located.

            drive: The name of the drive for which to set the power sleep mode.
        """
        cmd = "hdparm -Y /dev/%s" % drive
        host.run(cmd)

    @staticmethod
    def power_idle_hdd(host: Host, drive: str) -> None:
        """
        Sets the power idle mode on a specified drive on a given host.

        This function runs the 'hdparm' command with the '-y' option on
        the specified drive, which sends the drive into a low power idle mode.

        Args:
            host: The host on which the drive is located.

            drive: The name of the drive for which to set the power idle mode.
        """
        cmd = "hdparm -y /dev/%s" % drive
        host.run(cmd)

    @staticmethod
    def disable_write_cache(host: Host, drive: str, save: bool = False) -> None:
        """
        Disables the write cache for a specified drive on a given host.

        This function modifies the cache type of the specified drive to 'write through',
        effectively disabling the write cache. It also runs the 'hdparm' command to ensure the write
        cache is disabled. If the 'save' parameter is set to True, the changes are saved.

        Args:
            host: The host on which the drive is located.

            drive: The name of the drive for which to disable the write cache.

            save: Whether to save the changes. Defaults to False.
        """
        directory = f"/sys/block/{drive}/device/scsi_disk"
        cmd = f"ls {directory}"
        scsi_disk = host.run(cmd=cmd)
        cache = f"{directory}/{scsi_disk}/cache_type"
        cmd = f"echo 'write through' > {cache}"
        host.run(cmd=cmd)
        cmd = f"hdparm -W0 /dev/{drive}"
        host.run(cmd=cmd)

    @staticmethod
    def get_read_lookahead(host: Host, drive: str) -> int:
        """
        Retrieves the read lookahead cache status of a specified drive on a given host.

        This function runs the 'hdparm' command on the specified drive and parses the output
        to find the read lookahead cache status. If the status is found, it is returned as an
        integer. If not, a TestError is raised.

        Args:
            host: The host on which the drive is located.

            drive: The name of the drive for which to retrieve the read lookahead cache status.

        Returns:
            The read lookahead cache status of the specified drive.

        Raises:
            TestError: If the 'hdparm' command does not return a read lookahead cache status.
        """
        cmd = "hdparm -A /dev/%s" % (drive)
        output = host.run(cmd=cmd)
        pattern = re.compile(r"look-ahead\s+ =\s+(\d+)", re.MULTILINE)
        match = re.search(pattern, output)
        if match:
            return int(match.group(1))
        raise TestError(
            "Failed to get read lookahead. 'hdparm' output: {}".format(output)
        )

    @staticmethod
    def enable_read_lookahead(host: Host, drive: str) -> None:
        """
        Enables the read lookahead cache for a specified drive on a given host.

        This function runs the 'hdparm' command with the '-A1' option
        on the specified drive, which enables the read lookahead cache.

        Args:
            host: The host on which the drive is located.

            drive: The name of the drive for which to enable the read lookahead cache.
        """
        cmd = f"hdparm -A1 /dev/{drive}"
        host.run(cmd=cmd)

    @staticmethod
    def disable_read_lookahead(host: Host, drive: str) -> None:
        """
        Disables the read lookahead cache for a specified drive on a given host.

        This function runs the 'hdparm' command with the '-A0' option
        on the specified drive, which disables the read lookahead cache.

        Args:
            host: The host on which the drive is located.

            drive: The name of the drive for which to disable the read lookahead cache
        """
        cmd = f"hdparm -A0 /dev/{drive}"
        host.run(cmd=cmd)

    @staticmethod
    def is_drive_secure_with_password(host: Host, drive: str) -> bool:
        """
        Checks if a specified drive on a given host is secured with a user password.

        This function runs the 'hdparm' command with the '-I' option on the specified drive,
        and parses the output to determine if the drive is secured with a user password.
        If the drive is secured, it returns True. If not, it returns False.
        If the security status cannot be determined, a TestError is raised.

        Args:
            host: The host on which the drive is located.

            drive: The name of the drive to check for security.

        Returns:
            True if the drive is secured with a user password, False otherwise.

        Raises:
            TestError: If the 'hdparm' command does not return a security status, or if an error occurs during command execution.
        """
        try:
            cmd = f"hdparm -I /dev/{drive}"
            out = host.run(cmd=cmd)
            if "Security:" in out:
                for line in out.split("\n"):
                    if "enabled" in line:
                        if "not" in line:
                            return False
                        return True
                return False
            else:
                raise TestError(
                    f"Unable to find security status on /dev/{drive}: {out}"
                )
        except Exception as exc:
            raise TestError(
                "Error %s in %s execution for /dev/%s"
                # pyre-fixme[61]: `cmd` is undefined, or not always defined.
                % (str(exc), cmd, drive)
            )

    @staticmethod
    def ssd_secure_erase(host: Host, drive: str) -> None:
        """
        This function securely erases an SSD drive using the hdparm utility.

        It first checks if the drive is secure with a password. If not, it sets a user password.
        Then it tries to perform a secure erase with the 'security-erase-enhanced' command.
        If this fails, it falls back to the 'security-erase' command.

        Args:
            host: The host object on which the command is to be run.

            drive: The drive to be securely erased. It should be specified as a string, e.g., 'sda'.

        Raises:
            TestError: If there is an error in setting the password or in the secure erase process.
        """
        cmd = "time hdparm --user-master u "
        if not HdparmUtils.is_drive_secure_with_password(host, drive):
            try:
                cmd1 = cmd + "--security-set-pass pass /dev/%s" % drive
                host.run(cmd1)
            except Exception as exc:
                raise TestError(
                    "Error %s in setting password for /dev/%s" % (exc, drive)
                )
        # Some drives support security-erase-enhanced, some only security-erase
        try:
            cmd2 = cmd + "--security-erase-enhanced pass /dev/%s" % drive
            host.run(cmd2)
        except Exception:
            try:
                cmd3 = cmd + "--security-erase pass /dev/%s" % drive
                host.run(cmd3)
            except Exception as exc:
                raise TestError("Error %s in secure erase for /dev/%s" % (exc, drive))
