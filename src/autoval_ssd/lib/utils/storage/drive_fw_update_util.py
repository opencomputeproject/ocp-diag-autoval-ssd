# pyre-strict

import os
import re
from enum import Enum
from typing import Any, Dict, List

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import AutovalFileError, TestError

from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils

from autoval.lib.utils.decorators import retry
from autoval.lib.utils.file_actions import FileActions
from autoval.lib.utils.site_utils import SiteUtils

from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.storage.drive import Drive, DriveType

RETRY_COUNT = 5
RETRY_SLEEP_TIME = 30


class UpdateType(Enum):
    """Drive update types."""

    UPGRADE = "UPGRADE"
    DOWNGRADE = "DOWNGRADE"


class DriveFwUpdateUtil:
    """
    Drive Firmware Update Util.
    This util installs/updates and validates drive firmware.
    Test control params:
        host: The host object.
        revert_to_stable: Whether to revert to stable firmware.
        fw_versions: A list of firmware versions to update to.
        iteration: The number of times to update the firmware.
        reboot_required: Whether a reboot is required after updating the firmware.
        nvme_update_actions: A list of NVMe update actions.
        nvme_admin_io: Whether to use NVMe admin I/O.
        fw_slots: A list of firmware slots.
        force_update: Whether to force an update even if the firmware is already up to date.
        nvme_update_action (int): The NVMe update action to perform.
    """

    def __init__(self, host: Host, args: Dict[str, Any]) -> None:
        self.host = host
        self.revert_to_stable: bool = args.get("revert_to_stable", False)
        self.fw_versions: List[str] = args.get("versions", ["latest", "stable"])
        self.iteration: int = args.get("cycle", 1)
        self.reboot_required: bool = False
        self.nvme_update_actions: List[int] = args.get("nvme_update_actions", [1, 3])
        self.nvme_admin_io: bool = args.get("nvme_admin_io", False)
        self.fw_slots: list[int] = args.get("fw_slots", [])
        self.force_update: bool = args.get("force_update", False)
        self.reset_drive: bool = args.get("reset_drive", False)
        self.mode_7: bool = args.get("mode_7", False)

    def _record_failed_firmware_update(
        self,
        failed_firmware_update_data: List[Dict[str, Any]],
        drive: Drive,
        version_name: str,
        ver: str,
        exc: str,
        iteration: int,
        drive_version_info: Dict[str, Any],
    ) -> None:
        """
        Records failed firmware update data to the failed_firmware_update_data.
        Args:
            failed_firmware_update_data: List of failed firmware update data.
            drive: Drive object containing information about the drive.
            version_name: Version name of the firmware update.
            ver: Type of firmware update (e.g., "stable", "previous").
            exc: Exception message for the failed firmware update.
            iteration: Iteration number of the firmware update attempt.
            drive_version_info: Dictionary containing drive version information.
        Returns:
            None
        """
        failed_firmware_update_data_obj = {
            "host": self.host.hostname,
            "drive": drive.block_name,
            "drive_type": drive.type.name,
            "to_version": version_name,
            "update_type": (
                UpdateType.DOWNGRADE.name
                if ver == "stable" or ver == "previous"
                else UpdateType.UPGRADE.name
            ),
            "update_error": f"{exc}",
            "iteration": iteration,
        }
        if drive_version_info is not None and drive.block_name in drive_version_info:
            failed_firmware_update_data_obj["from_version"] = drive_version_info[
                drive.block_name
            ]
        AutovalLog.log_info(
            f"Failed firmware update data: {failed_firmware_update_data_obj}"
        )
        failed_firmware_update_data.append(failed_firmware_update_data_obj)

    @retry(RETRY_COUNT, RETRY_SLEEP_TIME, exceptions=AutovalFileError, exponential=True)
    def test_firmware_update(
        self,
        drive: Drive,
        ver: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        This function performs the following steps:
        1. Gets the firmware version and binary file path.
        2. Validates the firmware version and md5sum of the binary file.
        3. Updates the firmware using the binary file path.

        Args:
            drive: The drive's name present in the host for the specific drive type.
            ver: The firmware version to install on the DUT.
            kwargs: Additional keyword arguments for flash firmware update test.
                - failed_firmware_update_data: A list of dictionaries containing data about failed firmware updates.
                - iteration: The current iteration of the test.
                - drive_version_info: A dictionary containing the current firmware version of each drive.
        Raises:
            TestStepError: When comparison fails between expected and actual values of MD5 checksum and firmware version values.
        Returns:
            firmware_update_data_obj: A dictionary containing data about the firmware update.
        """
        fw_info = self._get_firmware_info(ver, drive)
        failed_firmware_update_data = kwargs.get("failed_firmware_update_data", [])
        iteration = kwargs.get("iteration", 1)
        drive_version_info = kwargs.get("drive_version_info", {})
        AutovalUtils.validate_in(
            "name",
            fw_info,
            "fw_info should have a 'name' attribute.",
            log_on_pass=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.FIRMWARE_UPGRADE_ERR,
        )
        AutovalUtils.validate_in(
            "bin",
            fw_info,
            "fw_info should have a 'bin' attribute.",
            log_on_pass=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.FIRMWARE_UPGRADE_ERR,
        )
        version_name = fw_info["name"]
        bin_path = self._get_bin_path(fw_info["bin"], drive)
        md5 = fw_info.get("md5", None)
        if md5:
            local_bin_path = FileActions.get_local_path(self.host, bin_path)
            AutovalUtils.validate_equal(
                md5,
                DiskUtils.get_md5_sum(self.host, local_bin_path),
                "md5 sums matched",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.FIRMWARE_UPGRADE_ERR,
            )
        AutovalLog.log_info(
            "Installing firmware %s to /dev/%s." % (version_name, drive.block_name)
        )
        try:
            self.update_drive_firmware(drive, version_name, bin_path)
        except Exception as exc:
            self._record_failed_firmware_update(
                failed_firmware_update_data,
                drive,
                version_name,
                ver,
                str(exc),
                iteration,
                drive_version_info,
            )
            if "No such file or directory" in str(exc):
                raise AutovalFileError(str(exc))
            raise
        firmware_update_data_obj = {
            "host": self.host.hostname,
            "drive": drive.block_name,
            "drive_type": drive.type.name,
            "to_version": version_name,
            "update_type": (
                UpdateType.DOWNGRADE.name
                if ver == "stable" or ver == "previous"
                else UpdateType.UPGRADE.name
            ),
            "iteation": iteration,
        }
        if drive_version_info is not None and drive.block_name in drive_version_info:
            firmware_update_data_obj["from_version"] = drive_version_info[
                drive.block_name
            ]
        return firmware_update_data_obj

    def update_drive_firmware(
        self,
        drive: Drive,
        version_name: str,
        bin_path: str,
    ) -> None:
        """
        This method updates the drive firmware using the given binary file path.
        Args:
            drive: The Drive drive object.
            version_name: The firmware version to find and install on drives.
            bin_path: The firmware's binary path.

        Raises:
            TestError: When fails to update the firmware for the drive.
        """
        if drive.type == DriveType.SSD:
            for action in self.nvme_update_actions:
                drive.update_firmware(
                    version_name,
                    bin_path,
                    fw_slots=self.fw_slots,
                    action=action,
                    force=self.force_update,
                    nvme_admin_io=self.nvme_admin_io,
                )
        elif drive.type == DriveType.HDD:
            drive.update_firmware(
                version_name, bin_path, mode_7=self.mode_7, force=self.force_update
            )
            if self.reset_drive:
                AutovalLog.log_info("Resetting drive")
                drive.reset()

    def _get_firmware_path(self, drive: Drive) -> str:
        """
        This method uses drive data to construct its firmware directory and returns the constructed path.
        Args:
            drive: The drive's name present in the host for the specific drive type.
        Returns:
            bin_file_path: Constructed binary file path with vendor and model details.
        Raises:
            TestError: When unsupported drive type is mentioned.
        """
        vendor = drive.manufacturer.lower()
        # There is a distinction between "generic"
        # drive and drives with some specific attributes
        # supported by Facebook. Those generic drives have
        # a '_generic' suffix. Since firmware binaries are organized
        # in directories named after the vendors, removing
        # '_generic' from vendor name here.
        vendor = re.sub("_generic$", "", vendor)
        model = drive.model.upper()
        result = bool(re.search(r"\s+", model))
        if result:
            model = re.sub(r"\s+", "_", model)
        root_path = SiteUtils.get_firmware_path()

        if drive.type == DriveType.SSD:
            root_path += "/flash"
        elif drive.type == DriveType.HDD:
            root_path += "/hdd"
        else:
            _msg = "Unsupported type: {}".format(drive.type)
            raise TestError(
                _msg,
                error_type=ErrorType.INPUT_ERR,
            )
        fw_path = os.path.join(root_path, vendor, model)
        if not os.path.isdir(fw_path):
            _msg = f"Firmware path {fw_path} does not exist. Please add your fw_version_map.json and fw bin files to {fw_path}"
            raise TestError(
                _msg,
                component=COMPONENT.SYSTEM,
                error_type=ErrorType.SYSTEM_ERR,
            )
        return fw_path

    def _get_firmware_map(self, drive: Drive) -> Dict[str, Any]:
        """
        This method pulls firmware information from a JSON file present in the firmware path.
        Args:
            drive: The drive's name present in the host for the specific drive type.
        Returns:
            fw_info: Content of drive model's fw_version_map.json.
        Raises:
            TestError: When fails to load the json file.
        """
        mapping_file = os.path.join(
            self._get_firmware_path(drive), "fw_version_map.json"
        )
        fw_info = {}
        try:
            fw_info = FileActions.read_data(mapping_file, json_file=True)
        except Exception as exc:
            raise TestError(
                "Fail to load %s: %s" % (mapping_file, exc),
                exception=exc,
            )
        return fw_info

    def _get_firmware_info(self, version: str, drive: Drive) -> Dict[str, Any]:
        """
        This method gets the drives firmware information based on version from firmware mapping file.
        Args:
            version: Drive's firmware version value.
            drive: The drive's name present in the host for the specific drive type.
        Returns:
            fw_info: Drive's Firmware information related to the version.
        Raises:
            TestError: When the specified version is not supported.
        """
        fw_map = self._get_firmware_map(drive)
        if version in fw_map:
            if fw_map[version]:
                return fw_map[version]
        raise TestError(
            f"{version} is not supported",
            error_type=ErrorType.INPUT_ERR,
        )

    def _get_bin_path(self, bin_name: str, drive: Drive) -> str:
        """
        This method gets binary file path for a firmware from a common location.
        Firmware binary path follows this format:
            <siteutils_firmware_path>/<drive_type>/<vendor>/<MODEL>/fw_binary/<bin_name>
        Args:
            bin_name: Binary file name for the corresponding firmware.
            drive: The drive's name present in the host for the specific drive type.
        Returns:
            bin_path: Binary file path for the given firmware.
        """
        bin_path = os.path.join(self._get_firmware_path(drive), "fw_binary", bin_name)
        # Model names might have spaces in them, if that is the case
        # the path to firmware binary will have spaces as well.
        # Escape spaces in returned binary path here.
        return r"\ ".join(bin_path.split(" "))
