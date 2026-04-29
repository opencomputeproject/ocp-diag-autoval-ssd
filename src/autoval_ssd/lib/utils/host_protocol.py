#!/usr/bin/env python3

# pyre-strict

"""
Protocol defining the interface for Host-like objects used across test utilities.

Use `HostProtocol` as the type annotation for `host` parameters in test utility
modules (e.g., nvme_utils.py) instead of importing the concrete `Host` class.
This decouples test utilities from the full Host implementation and enables
structural typing.
"""

from typing import Any, Optional, Protocol

from autoval.lib.connection.connection_utils import CmdResult


class InbandProtocol(Protocol):
    """Protocol for the inband interface accessed via host.inband."""

    def reboot(self, shutdown_cmd: bool = False) -> None: ...


class DevicesProtocol(Protocol):
    """Protocol for the devices interface accessed via host.devices."""

    def device_ready(self) -> list[Any]: ...

    def set_directory(self) -> Optional[str]: ...

    def _check_asic_cmd(self, host: Any, module: str) -> None: ...


class LocalhostProtocol(Protocol):
    """Protocol for the localhost connection accessed via host.localhost."""

    def run(
        self,
        cmd: str,
        ignore_status: bool = False,
        timeout: int = 600,
        working_directory: Optional[str] = None,
        custom_logfile: Optional[str] = None,
        get_pty: bool = False,
        sudo: bool = False,
        sudo_options: Optional[list[str]] = None,
        connection_timeout: int = 60,
        background: bool = False,
        keepalive: int = 0,
        forward_ssh_agent: bool = False,
        path_env: Optional[list[str]] = None,
    ) -> str: ...


class HostProtocol(Protocol):
    """
    Protocol defining the interface that Host-like objects expose to test
    utilities.

    This captures the subset of the Host API commonly used by test_utils
    modules such as NVMeUtils, DiskUtils, and others. The concrete
    `Host` class satisfies this protocol via structural subtyping.
    """

    hostname: str

    @property
    def inband(self) -> InbandProtocol: ...

    @property
    def devices(self) -> DevicesProtocol: ...

    @property
    def localhost(self) -> LocalhostProtocol: ...

    def run(
        self,
        cmd: str,
        ignore_status: bool = False,
        timeout: int = 600,
        working_directory: Optional[str] = None,
        custom_logfile: Optional[str] = None,
        get_pty: bool = False,
        sudo: bool = False,
        sudo_options: Optional[list[str]] = None,
        connection_timeout: int = 60,
        background: bool = False,
        keepalive: int = 0,
        forward_ssh_agent: bool = False,
        path_env: Optional[list[str]] = None,
    ) -> str: ...

    def run_get_result(
        self,
        cmd: str,
        ignore_status: bool = False,
        timeout: int = 600,
        working_directory: Optional[str] = None,
        custom_logfile: Optional[str] = None,
        get_pty: bool = False,
        sudo: bool = False,
        sudo_options: Optional[list[str]] = None,
        connection_timeout: int = 60,
        background: bool = False,
        keepalive: int = 0,
        forward_ssh_agent: bool = False,
        path_env: Optional[list[str]] = None,
    ) -> CmdResult: ...

    def get_os(self) -> Optional[str]: ...

    def get_os_version(self) -> str: ...

    def is_metalos(self) -> bool: ...

    def system_health_check(
        self,
        dut_last_reboot: bool | str = False,
        dut_connect_timeout: int = 600,
        bmc_last_reboot: Any = None,
        bmc_reconnect_timeout: int = 180,
    ) -> None: ...
