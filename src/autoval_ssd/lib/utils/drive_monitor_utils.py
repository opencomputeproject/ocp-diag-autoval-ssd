# pyre-strict

from threading import Event
from time import sleep
from typing import List, Optional

from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_exceptions import CmdError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval_ssd.lib.utils.sed_util import SedUtils
from autoval_ssd.lib.utils.storage.drive import Drive
from autoval_ssd.lib.utils.storage.nvme.nvme_drive import NVMeDrive


class DriveMonitorUtils:
    """
    This class is used for perodic drive monitoring.
    """

    DRIVE_STATUS_METHODS = {
        "DRIVE_STATUS": "enclosure_util_drive_status",
        "E1S_STATUS": "enclosure_util_e1s_status",
    }

    @staticmethod
    def _get_drive_status_method(host: Host) -> str:
        """
        Determines the appropriate drive status method to use.
        Args:
            host: The host from which to retrieve the drive status.
        Returns:
            str: The name of the drive status method.
        """
        for name, method_name in DriveMonitorUtils.DRIVE_STATUS_METHODS.items():
            try:
                AutovalLog.log_info(f"Trying '{name}' method to log drive stats.")
                method = getattr(DriveMonitorUtils, method_name)
                method(host)
                AutovalLog.log_info(f"'{name}' method succeeded.")
                return name
            except CmdError as e:
                AutovalLog.log_debug(f"'{name}' method failed with '{e}'.")

        AutovalLog.log_info("No valid enclosure-util drive status method is available.")
        return "NO_STATUS"

    @staticmethod
    def log_drive_status(host: Host, drive_status_method: Optional[str] = None) -> None:
        """
        Logs the drive status using the specified method or determines the method if not provided.

        Args:
            host: The host from which to log drive status.
            drive_status_method: Optional; the method to use for logging drive status.
        """
        if drive_status_method is None:
            drive_status_method = DriveMonitorUtils._get_drive_status_method(host)

        if drive_status_method == "NO_STATUS":
            return

        if drive_status_method in DriveMonitorUtils.DRIVE_STATUS_METHODS:
            method_name = DriveMonitorUtils.DRIVE_STATUS_METHODS[drive_status_method]
            method = getattr(DriveMonitorUtils, method_name)
            method(host)

    @staticmethod
    def enclosure_util_drive_status(host: Host) -> None:
        """
        Output drive status in command log using --drive-status.

        Args:
            host: The host to get the drive status of.
        Raises:
            CmdError: If there is an unexpected error running the command.
        """
        slot_info = host.oob.get_slot_info()
        cmd = f"enclosure-util {slot_info} --drive-status all"
        host.oob.bmc_host.run(cmd)

    @staticmethod
    def enclosure_util_e1s_status(host: Host) -> None:
        """
        Output drive status in command log using --e1s-status.

        Args:
            host: The host to get the drive status of.
        Raises:
            CmdError: If there is an unexpected error running the command.
        """
        cmd = "enclosure-util --e1s-status"
        host.oob.bmc_host.run(cmd)

    @staticmethod
    def start_periodic_drive_monitor(
        host: Host,
        test_drives: List[Drive],
        end_of_test: Event,
        periodic_drive_monitor_interval: Optional[int],
        only_sideband_cmds: bool = False,
        only_inband_cmds: bool = False,
    ) -> None:
        """
        Start periodic drive monitoring

        Args:
            host: The host for drive monitoring.
            test_drives: The drives to monitor.
            end_of_test: An event to stop monitoring when set.
            periodic_drive_monitor_interval: The interval between drive status checks.
            only_sideband_cmds: If True, only run sideband commands.
            only_inband_cmds: If True, only run inband commands.
        """
        MAX_PERIODIC_DRIVE_MONITOR_DURATION = 10 * 3600
        DEFAULT_INTERVAL_SECONDS = 15 * 60
        remaining_duration = MAX_PERIODIC_DRIVE_MONITOR_DURATION
        interval = periodic_drive_monitor_interval or DEFAULT_INTERVAL_SECONDS

        AutovalLog.log_info(
            f"Starting periodic drive monitoring with {interval}s interval"
        )

        opal2_0_drives, _ = SedUtils.opal_support_scan(host)
        AutovalLog.log_info(f"Opal2 supported drives: {opal2_0_drives}")

        drive_status_method = DriveMonitorUtils._get_drive_status_method(host)

        while remaining_duration > 0 and not end_of_test.is_set():
            if not only_inband_cmds:
                DriveMonitorUtils.log_drive_status(host, drive_status_method)
                AutovalUtils.validate_no_exception(
                    host.oob.bmc_host.run,
                    [f"sensor-util {host.oob.get_slot_info()}"],
                    f"[Periodic Drive Monitoring][{host.oob.get_slot_info()}] Assert no sensor-util cmd exception",
                    raise_on_fail=False,
                    log_on_pass=False,
                )
            if not only_sideband_cmds:
                for drive in test_drives:
                    if isinstance(drive, NVMeDrive):
                        AutovalUtils.validate_no_exception(
                            drive.get_smart_log,
                            [],
                            f"[Periodic Drive Monitoring][{drive.block_name}] Assert no nvme smart-log cmd exception",
                            raise_on_fail=False,
                            log_on_pass=False,
                        )

                        if drive.block_name in opal2_0_drives:
                            AutovalUtils.validate_no_exception(
                                host.run,
                                [
                                    f"nvme security-recv -p 0x1 -s 0x1 -t 256 -x 256 /dev/{drive.block_name}"
                                ],
                                f"[Periodic Drive Monitoring][{drive.block_name}] Assert no nvme security-recv cmd exception",
                                raise_on_fail=False,
                                log_on_pass=False,
                            )

            for _ in range(interval):
                if end_of_test.is_set():
                    break
                sleep(1)
                remaining_duration -= 1

        AutovalLog.log_info("End of periodic drive monitoring")
