#!/usr/bin/env python3

# pyre-strict
"""Library to manage scrtnycli util"""

import re
import time
from typing import Union

from autoval.lib.host.component.component import COMPONENT

from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.decorators import retry


class ScrtnyCli:
    @staticmethod
    def deploy_scrtnycli(host: Host) -> str:
        """
        This function will check if scrtnycli is installed on the host and deploy the tool if not.
        lsiutil is currently used to upgrade to HDD, but now scrtnycli will be used
        for upgrading the HDD firmware.
        This tool is present in the tools folder.
        """
        cmd = "which scrtnycli"
        out = host.run_get_result(cmd=cmd, ignore_status=True)
        if out and out.return_code == 0:
            return "scrtnycli"
        tool_path = host.deploy_tool("scrtnycli.x86_64")
        return tool_path

    @staticmethod
    @retry(tries=3, sleep_seconds=15)
    def scan_drive_scrtnycli(host: Host, tool_path: str) -> str:
        """
        Get `Disk` info from `scrtnycli` tool for IOC 1

        Args:
            host: The host object to run commands on.

            tool_path: The path to the scrtnycli tool.

        Returns:
            `Disk` info from `scrtnycli` tool for IOC 1

            Example output:
                    0   19  0   3   Disk       ATA      VendorX ModelY   CB58 5000039A98C832DE
                    0   20  0   4   Disk       ATA      VendorX ModelY   CB58 5000039A98C83286
        """
        cmd = f"{tool_path} -i 1 scan | grep Disk"
        out = host.run(cmd=cmd)
        return out

    @staticmethod
    @retry(tries=3, sleep_seconds=15)
    def scan_drive_scrtnycli_ioc2(host: Host, tool_path: str) -> str:
        """
                Get `Disk` info from `scrtnycli` tool for IOC 2

                Args:
                    host: The host object to run commands on.

                    tool_path: The path to the scrtnycli tool.
                Returns:
                    `Disk` info from `scrtnycli` tool for IOC 2

                Example output:
        +                0   19  0   3   Disk       ATA      VendorX ModelY   CB58 5000039A98C832DE
        +                0   20  0   4   Disk       ATA      VendorX ModelY   CB58 5000039A98C83286
        """
        cmd = f"{tool_path} -i 2 scan | grep Disk"
        out = host.run(cmd=cmd)
        return out

    @staticmethod
    def update_firmware_scrtnycli(
        host: Host,
        fw_bin_loc: str,
        disk_no: str,
        tool_path: str,
        ioc_no: Union[int, str],
    ) -> None:
        """
        This function will actully download the HDD f/w bin on to the drive

        Args:
            host: The host object to run commands on.

            fw_bin_loc: The local path of the HDD binary to upgrade.

            disk_no: The corresponding disk header of the drive extracted using the scrtnycli tool.

            tool_path: The path to the scrtnycli tool.

            ioc_no: The I/O controller number.
        """
        cmd = f"{tool_path} -i {ioc_no} dl -pdfw {fw_bin_loc} -dh 0x{disk_no} -m 7"
        host.run(cmd=cmd)

    @staticmethod
    def list_devices(host: Host) -> str:
        """
        This method deploys the scrtnycli tool on the given host and runs
        the command "scrtnycli --list" to get a list of devices.

        Args:
            host: The host object on which the command is executed.

        Returns:
            The output of the "scrtnycli --list" command.
        """
        tool_path = ScrtnyCli.deploy_scrtnycli(host)
        cmd = f"{tool_path} --list"
        output = host.run(cmd=cmd)
        return output

    @staticmethod
    def count_hbas(host: Host) -> int:
        """
        This method counts the number of HBAs present on the server.

        Args:
            host: The host object on which the command is executed.

        Returns:
            The number of HBAs found on the server.
        """
        output = ScrtnyCli.list_devices(host)
        regex = "eHBA|FeatureIT"
        match = re.findall(regex, output)
        AutovalLog.log_info(f"{len(match)} HBAs on the server")
        return len(match)

    @staticmethod
    def count_expanders(host: Host) -> int:
        """
        This method counts the number of expanders present on the server.

        Args:
            host: The host object on which the command is executed.

        Returns:
            The number of expanders found on the server.
        """
        output = ScrtnyCli.list_devices(host)
        regex = "Expander"
        match = re.findall(regex, output)
        AutovalLog.log_info(f"{len(match)} expanders on the server")
        return len(match)

    @staticmethod
    def expander_soft_reset(host: Host) -> None:
        """
        This method performs a soft reset on the expander connected to the specified host.

        Args:
            host: The host on which the command is executed.

        Raises:
            ValidationException: If any exception occurs while executing the command or if the command
             fails to perform the soft reset.
        """
        cmd = "scrtnycli -i 2 reset -e"
        AutovalUtils.validate_no_exception(
            host.run,
            [cmd],
            "Soft resetting all expanders",
            component=COMPONENT.HDD,
            error_type=ErrorType.EXPANDER_ERR,
        )
        time.sleep(120)

    @staticmethod
    def phy_link_reset(host: Host, phy_addr: int) -> None:
        """
        This method performs a PHY link reset on the drive for the given PHY addr.

        Args:
            host: The system on which the command will be executed.

            phy_value: The PHY value of the drive to perform the reset on.

        Raises:
            ValidationException: If any exception occurs while executing the command or
            if the command fails to perform the reset.
        """
        cmd = f"scrtnycli -i 2 reset -pl {phy_addr}"
        AutovalUtils.validate_no_exception(
            host.run,
            [cmd, True],
            f"PHY reset of drive with PHY value {phy_addr}",
            component=COMPONENT.HDD,
            error_type=ErrorType.EXPANDER_ERR,
        )
        time.sleep(30)

    @staticmethod
    def phy_link_reset_all(host: Host) -> None:
        """
        This method performs a PHY link reset on all drives.

        Args:
            host: The system on which the command will be executed.

        Raises:
            ValidationException: If any exception occurs while executing the command or
            if the command fails to perform the reset.

        """
        cmd = "scrtnycli -i 2 reset -pla"
        AutovalUtils.validate_no_exception(
            host.run,
            [cmd, True],
            "PHY reset of all drives",
            component=COMPONENT.HDD,
            error_type=ErrorType.EXPANDER_ERR,
        )
        time.sleep(30)

    @staticmethod
    def phy_hard_reset(host: Host, phy_addr: int) -> None:
        """
        This method performs a PHY hard reset on the drive for the given PHY addr.

        Args:
            host: The system on which the command will be executed.

            phy_addr: The PHY address of the drive to perform the hard reset on.

        Raises:
            ValidationException: If any exception occurs while executing the command or if the command
            fails to perform the PHY hard reset.
        """
        cmd = f"scrtnycli -i 2 reset -ph {phy_addr}"
        AutovalUtils.validate_no_exception(
            host.run,
            [cmd, True],
            f"PHY hard resetting on drive with PHY address {phy_addr}",
            component=COMPONENT.HDD,
            error_type=ErrorType.EXPANDER_ERR,
        )
        time.sleep(30)

    @staticmethod
    def phy_hard_reset_all(host: Host) -> None:
        """
        This method performs a PHY hard reset on all drives.

        Args:
            host: The Host object representing the system on which the command will be executed.

        Raises:
            ValidationException: If any exception occurs while executing the command or if the command
            fails to perform the PHY hard reset.
        """
        cmd = "scrtnycli -i 2 reset -pha"
        AutovalUtils.validate_no_exception(
            host.run,
            [cmd, True],
            "PHY hard resetting on all drives",
            component=COMPONENT.HDD,
            error_type=ErrorType.EXPANDER_ERR,
        )
        time.sleep(30)

    @staticmethod
    def turn_phy_on(host: Host, phy_addr: int) -> None:
        """
        This method turns ON the PHY of the drive for the given PHY address.

        Args:
            host: The Host object representing the system on which the command will be executed.

            phy_addr: The PHY address of the drive to turn ON.

        Raises:
            ValidationException: If any exception occurs while executing the command or if the command fails
            to turn ON the PHY.
        """
        cmd = f"scrtnycli -i 2 phy -on {phy_addr}"
        AutovalUtils.validate_no_exception(
            host.run,
            [cmd, True],
            f"Turning ON PHY with PHY value {phy_addr}",
            component=COMPONENT.HDD,
            error_type=ErrorType.EXPANDER_ERR,
        )
        time.sleep(30)

    @staticmethod
    def turn_phy_off(host: Host, phy_addr: int) -> None:
        """
        This method turns OFF the PHY of the drive for the given PHY address.

        Args:
            host: The Host object representing the system on which the command will be executed.

            phy_addr: The PHY address of the drive to turn ON.

        Raises:
            ValidationException: If any exception occurs while executing the command or if the command fails
            to turn OFF the PHY.
        """
        cmd = f"scrtnycli -i 2 phy -off {phy_addr}"
        AutovalUtils.validate_no_exception(
            host.run,
            [cmd, True],
            f"Turning OFF PHY with PHY value {phy_addr}",
            component=COMPONENT.HDD,
            error_type=ErrorType.EXPANDER_ERR,
        )
        time.sleep(30)
