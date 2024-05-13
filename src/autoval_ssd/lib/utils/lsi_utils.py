#!/usr/bin/env python3

# pyre-strict

import re
from typing import Dict

from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_exceptions import CmdError, TestError


class LsiUtils:
    @staticmethod
    def get_phy_counters(host: Host) -> Dict[int, Dict[str, Dict[int, Dict[str, int]]]]:
        """
        This method retrieves the physical counters for a given host.

        Args:
            host: The host for which to retrieve the physical counters.

        Returns:
            A dictionary containing the physical counters for each port on the host.
        """
        phy_errors = {}
        if LsiUtils.check_lsiutil_support(host):
            port_count = LsiUtils.get_lsi_port_count(host)
            for port in range(1, port_count + 1):
                phy_errors[port] = LsiUtils.parse_phy_errors(host, port=port)
        return phy_errors

    @staticmethod
    def get_drives(host: Host) -> str:
        """
        Retrieves drive information from a host using the Lsiutil command.

         Args:
            host: The host from which to retrieve drive information.

        Returns:
            The output of the 'Lsiutil' command, which displays drive information.

        Raises:
            TestError: If there is an error running the 'lsiutil' command or retrieving the drive information.
        """
        try:
            return host.run("lsiutil -s display /scan")
        except Exception:
            raise TestError("Failed getting drive info from Lsiutil")

    @staticmethod
    def parse_phy_errors(host: Host, port: int) -> Dict[str, Dict[int, Dict[str, int]]]:
        """
        Parses the physical errors for a given host and port.

        This method runs a command on the host to retrieve physical error information,
        then parses the output to create a dictionary of error details.

        Args:
            host: The host for which to parse the physical errors.

            port: The port for which to parse the physical errors.

        Returns:
            A dictionary containing the parsed physical errors.
                Example:
                    {'adapter':
                        {0:
                            {'invalid_word': 0,
                             'running_disparity': 0,
                             'loss_of_dword_sync': 0,
                             'phy_reset_problem': 0}
                        }
                    }
        """
        phy_errors = {}
        output = host.run(f"lsiutil -a 12,0,0,0, 20 -p {port}")
        lines = output.splitlines()
        handle = None
        this_phy = 0
        for line in lines:
            no_errors_phy = re.match(
                r"(Expander|Adapter)\s+(\(Handle\s+(\w+)\))?\s*Phy\s+"
                r"(\d+):\s+Link\s+(Down|Up),\s+No\s+Errors",
                line,
            )
            if no_errors_phy:
                if no_errors_phy.group(1) == "Adapter":
                    handle = "adapter"
                else:
                    handle = no_errors_phy.group(3)
                this_phy = int(no_errors_phy.group(4))
                if handle not in phy_errors:
                    phy_errors[handle] = {}
                phy_errors[handle][this_phy] = {}
                phy_errors[handle][this_phy]["invalid_word"] = 0
                phy_errors[handle][this_phy]["running_disparity"] = 0
                phy_errors[handle][this_phy]["loss_of_dword_sync"] = 0
                phy_errors[handle][this_phy]["phy_reset_problem"] = 0
                continue
            adapter_with_errors = re.match(r"Adapter\s+Phy\s+(\d+):\s+Link\s+\w+", line)
            if adapter_with_errors:
                handle = "adapter"
                this_phy = adapter_with_errors.group(1)
                if handle not in phy_errors:
                    phy_errors[handle] = {}
                phy_errors[handle][int(this_phy)] = {}
            phy_with_errors = re.match(
                r"Expander\s+\(Handle\s+(\w+)\)\s+Phy\s+(\d+):\s+Link\s+" "(Down|Up)",
                line,
            )
            if phy_with_errors:
                handle = phy_with_errors.group(1)
                this_phy = phy_with_errors.group(2)
                if handle not in phy_errors:
                    phy_errors[handle] = {}
                phy_errors[handle][int(this_phy)] = {}
            invalid_dword_count = re.match(r"\s*Invalid\s*DWord\s*Count\s+(\d+)", line)
            if invalid_dword_count:
                phy_errors[handle][int(this_phy)]["invalid_word"] = int(
                    invalid_dword_count.group(1)
                )
            running_disparity = re.match(
                r"\s*Running Disparity Error Count\s+(\d+)", line
            )
            if running_disparity:
                phy_errors[handle][int(this_phy)]["running_disparity"] = int(
                    running_disparity.group(1)
                )
            loss_of_dword = re.match(r"\s*Loss of DWord Synch Count\s+(\d+)", line)
            if loss_of_dword:
                phy_errors[handle][int(this_phy)]["loss_of_dword_sync"] = int(
                    loss_of_dword.group(1)
                )
            phy_reset_count = re.match(r"\s*Phy Reset Problem Count\s+(\d+)", line)
            if phy_reset_count:
                phy_errors[handle][int(this_phy)]["phy_reset_problem"] = int(
                    phy_reset_count.group(1)
                )
        return phy_errors

    @staticmethod
    def get_lsi_port_count(host: Host) -> int:
        """
        This method retrieves the number of LSI ports on a given host.

        Args:
            host: The host for which to retrieve the LSI port count.

        Returns:
            The number of LSI ports on the host.
        """
        output = host.run("lsiutil 0")
        pattern = re.compile(r"(\d)\sMPT (Port|Ports) found", re.MULTILINE | re.DOTALL)
        match = re.search(pattern, output)
        if match:
            return int(match.group(1))
        raise TestError("Failed to get lsi port count.")

    @staticmethod
    def clear_phy_errors(host: Host, port: int) -> None:
        """
        This method clears the physical errors for a given host and port.

        Args:
            host: The host for which to clear the physical errors.

            port: The port for which to clear the physical errors.
        """
        host.run(f"lsiutil -p {port} -a 13,0,0,0 20")

    @staticmethod
    def clear_all_ports_phy_errors(host: Host) -> None:
        """
        This method clears all physical errors for all ports on a given host.

        Args:
            host: The host for which to clear all physical errors.
        """
        if LsiUtils.check_lsiutil_support(host):
            count = LsiUtils.get_lsi_port_count(host)
            for hba in range(count):
                LsiUtils.clear_phy_errors(host, hba + 1)

    @staticmethod
    def check_lsiutil_support(host: Host) -> bool:
        """
        This method checks if the `lsiutil` command is supported on a given host.

        Args:
            host: The host to check for `lsiutil` support

        Returns:
            True if `lsiutil` is supported, otherwise False.
        """
        try:
            host.run("lsiutil")
            return True
        except CmdError:
            return False
