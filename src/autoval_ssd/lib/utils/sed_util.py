#!/usr/bin/env python3

# pyre-strict
import re
from typing import List, Tuple 
from autoval.lib.host.host import Host

from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_utils import AutovalLog, AutovalUtils

from autoval_ssd.lib.utils.disk_utils import DiskUtils	
from autoval_ssd.lib.utils.storage.nvme.nvme_drive import NVMeDrive, OwnershipStatus

class SedUtils:
    @staticmethod
    def take_ownership(host: Host, drive: NVMeDrive, password: str = "debug") -> None:
        """
        Takes ownership of a given NVMeDrive on a specified host server.

        This method is used to take ownership of a drive by executing the sed-util commands.
        It first checks the current ownership status of the drive. If the status is NOT_SET,
        it executes the command to set the password and take ownership. If the ownership is
        already set, it raises a TestError.

         Args:
            host: The host server on which the drive is located.

            drive: The target drive object for which ownership is to be taken.

            password: The password to execute the sed-util commands. Defaults to "debug".

        Raises:
            TestError: If the TCG Ownership is already set.
        """
        AutovalLog.log_info("Taking ownership.")
        status = drive.get_tcg_ownership_status()
        if status == OwnershipStatus.NOT_SET:
            cmd = f"sedutil-cli -v -n --setSIDPassword {password} facebook /dev/{drive.block_name}"
            out = host.run(cmd)
            AutovalLog.log_info(out)
            AutovalUtils.validate_equal(
                str(drive.get_tcg_ownership_status()),
                str(OwnershipStatus.SET),
                "Validating if Ownership is taken.",
            )
        else:
            raise TestError(
                f"Ownership cannot be taken, because TCG Ownership is {status.name}"
            )

    @staticmethod
    def _check_locking(host: Host, drive: NVMeDrive) -> str:
        """
        Checks the locking status of a given NVMeDrive on a specified host server.

        This helper function runs a sedutil-cli query command on the host server to check
        the locking status of the specified drive. It then parses the output to extract
        the LockingEnabled status.

        Args:
            host: The host server on which the drive is located.

            drive: The target drive object for which the locking status is to be checked.

        Returns:
            The LockingEnabled status of the drive. Returns '0' if no match is found.
        """
        cmd = f"sedutil-cli --query /dev/{drive.block_name}"
        out = host.run(cmd=cmd)
        match = re.search(r"LockingEnabled\s*=\s*(\S)", out)
        status = "0"
        if match:
            status = match.group(1)
        return status

    @staticmethod
    def _init_drive(host: Host, drive: NVMeDrive, password: str = "debug") -> str:
        """
        Helper function to initialize a NVMeDrive.

        This function uses the `sedutil-cli` command to initialize a given NVMeDrive.
        If the drive is not initialized, it logs an info message and runs the command
        to initialize the drive.

        Args:
            host: The host on which the drive is located.

            drive: The drive to be initialized.

            password: The password to be used for the initialization. Defaults to "debug".

        Returns:
            The output of the host run command.

        Raises:
            Exception: If the host run command fails, an exception is raised.
        """
        AutovalLog.log_info(f"Drive {drive} is not initialized. Initializing...")
        cmd = f"sedutil-cli -v --initialsetup {password} /dev/{drive.block_name}"
        out = host.run(cmd=cmd, ignore_status=True)
        return out

    @staticmethod
    def revert_take_ownership(
        host: Host, drive: NVMeDrive, password: str = "debug"
    ) -> None:
        """
        Revert the take ownership.

        This method is used to revert the taken ownership by setting the
        device back to factory defaults.

        Args:
            host: The host server.

            drive: The target drive object.

            password: The password to execute the sed-util commands. Defaults to "debug".

        Raises:
            TestError: If the TCG Ownership is not set, the function raises a TestError.
        """
        AutovalLog.log_info(f"Reverting ownership taken on drive {drive}")
        status = drive.get_tcg_ownership_status()
        if status == OwnershipStatus.SET:
            lock = SedUtils._check_locking(host, drive)
            if lock == "0" or lock == "N":
                # Initialize drive
                out = SedUtils._init_drive(host, drive, password=password)
                if "AUTHORITY_LOCKED_OUT" in out:
                    boot_drive = DiskUtils.get_boot_drive(host)
                    warning = False
                    if str(drive) == str(boot_drive):
                        AutovalLog.log_info(f"Drive {drive.block_name} is BOOT drive")
                        warning = True
                    AutovalUtils.validate_condition(
                        False,
                        f"Drive {drive.block_name} is locked to change ownership",
                        warning=warning,
                    )
                    return
            cmd = f"sedutil-cli -v -n --reverttper {password} /dev/{drive.block_name}"
            out = host.run(cmd=cmd, ignore_status=True)
            if "NOT_AUTHORIZED" in out:
                boot_drive = DiskUtils.get_boot_drive(host)
                warning = False
                if str(drive) == str(boot_drive):
                    AutovalLog.log_info(f"Drive {drive.block_name} is BOOT drive")
                    warning = True
                # Too many attempts happened
                AutovalUtils.validate_condition(
                    False,
                    f"Drive {drive.block_name} is not authorized to change ownership",
                    warning=warning,
                )
                return
            AutovalLog.log_info(out)
            AutovalUtils.validate_equal(
                str(drive.get_tcg_ownership_status()),
                str(OwnershipStatus.NOT_SET),
                "Validating if Ownership is revereted.",
            )
        else:
            raise TestError(
                f"Ownership cannot be reverted, because TCG Ownership is {status.name}"
            )

    @staticmethod
    def opal_support_scan(host: Host) -> Tuple[List[str], List[str]]:
        """
        Scans for the Opal supported drives.

        This method will Scans for the Opal supported drives and returns the list
        of Opal supported and unsupported drives.

        Args:
            host: The host server to scan for Opal 2 supported drives.

        Returns:
            Tuple: A tuple containing two lists. The first list contains the block names
            of the drives which are Opal 2 supported. The second list contains the block names of the drives
            which are not Opal 2 supported.

        Raises:
            TestError: If no devices are scanned with sedutil.
        """
        AutovalLog.log_info("Checking for the Opal2 supported drives")
        cmd = "sedutil-cli --scan"
        # opal 2.0 supported drives
        opal_list = []
        non_opal_list = []
        out = host.run(cmd)
        if not out:
            raise TestError("No devices scanned with sedutil")
        pattern = r"^/dev/(\w+)\s+(\w+)"
        for line in out.splitlines():
            match = re.search(pattern, line)
            if match:
                block_name = match.group(1)
                opal_value = match.group(2)
                if opal_value == "2":
                    opal_list.append(block_name)
                else:
                    non_opal_list.append(block_name)
        return opal_list, non_opal_list

    @classmethod
    def get_sed_support_status(cls, host: Host, block_name: str) -> bool:
        """
        This method will Checks if the Self-Encrypting Drive (SED) supports the OPAL 2.0 specification.

        Args:
            host: The host server to scan for Opal 2 supported drives.

            block_name: The name of the drive.

        Returns:
            Returns True if the SED supports the OPAL 2.0 specification, otherwise returns False.
        """
        cmd = f"sedutil-cli --isValidSED /dev/{block_name}"
        out = host.run(cmd)
        pattern = rf"/dev/{block_name}\s+SED\s+-(\d+)-"
        match = re.search(pattern, out)
        if match:
            opal_check = match.group(1)
            if opal_check == "2":
                return True
        return False

    @staticmethod
    def get_query_output(host: Host, block_name: str) -> str:
        """
        Retrieves the sed-util query output for a specific drive on a host server.

        This function runs a command using the `sedutil-cli` utility to query a specific
        drive on a host server. The output of this command is then returned.

        Args:
            host: The host server where the command will be run.

            block_name: The name of the drive to be queried.

        Returns:
            The output of the sed-util query command.
        """
        cmd = f"sedutil-cli --query /dev/{block_name}"
        return host.run(cmd)

    @classmethod
    def check_locked_status(cls, host: Host, block_name: str) -> bool:
        """
        Checks if a drive is locked.

        This method scans the host servers for opal 2 supported drives and checks
        if the specified drive is locked.

         Args:
            host: The host servers to scan for opal 2 supported drives.

            block_name: The name of the drive.

        Returns:
            True if the drive is locked, False otherwise.

        Raises:
            TestError: If the drive's locked status cannot be obtained.
        """
        query_out = cls.get_query_output(host, block_name)
        pattern = r"\s+Locked\s+=\s+([A-Z])"
        match = re.search(pattern, query_out)
        if match:
            return False if match.group(1) == "N" else True
        else:
            raise TestError("Not able to obtain the drive Locked status.")

    @staticmethod
    def get_msid(host: Host, block_name: str) -> str:
        """
        Retrieves the MSID(Master Security ID) of a drive.

        This method scans the host servers for opal 2 supported drives and retrieves
        the MSID of the specified drive.

        Args:
            host: The host servers to scan for opal 2 supported drives.

            block_name: The name of the drive.

        Returns:
            The MSID of the drive.

        Raises:
            TestError: If the MSID of the drive cannot be found.
        """
        cmd = f"sedutil-cli --printDefaultPassword /dev/{block_name}"
        out = host.run(cmd)
        pattern = r"MSID:\s+(\w+)"
        match = re.search(pattern, out)
        if match:
            return match.group(1)
        else:
            raise TestError("MSID not found.")
