#!/usr/bin/env python3

# pyre-unsafe
"""Test to validate NVME cli commands"""
import datetime
import json
import re

from autoval.lib.host.component.component import COMPONENT

from autoval.lib.utils.async_utils import AsyncJob, AsyncUtils
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval_ssd.lib.utils.storage.nvme.nvme_drive import NVMeDrive
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase


class NvmeCli(StorageTestBase):
    """
    Test to validate if NVME 1.2.1 spec commands are supported
    Validations done on all the NVME drives:
        Get the controller properties,
        Get the Firmware Log,
        Check Crypto Erase Support,
        Get Error Log Entries,
        Log the properties of the specified namespace,
        Get the operating parameters of the specified controller,
        identified by the Feature Identifier,
        Get Vendor Specific Internal Logs,
        Retrieve Command Effects Log.
        Get Vendor Specific drive up time,
        Get Smart log,
        Get/Set Power mode.
        validate capacity
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.drive_type = self.test_control.get("drive_type", None)
        self.drive_interface = self.test_control.get("drive_interface", None)
        self.crypto_erase = self.test_control.get("check_crypto_erase", True)
        self.arbitration_mechanism = self.test_control.get(
            "arbitration_mechanism", True
        )

    def execute(self) -> None:
        self.log_info("Test to run NVME Cli commands")
        version = NVMeUtils.get_nvme_version(self.host)
        self.log_info(f"Running NVME version {version}")
        AsyncUtils.run_async_jobs(
            [
                AsyncJob(func=self.validate_nvme_drives, args=[drive])
                for drive in self.test_drives
            ]
        )

    def validate_nvme_drives(self, drive) -> None:
        """Check drive nvme is write mode enabled"""
        AutovalUtils.validate_condition(
            (not drive.check_readonly_mode()),
            "Check drive nvme is write mode enabled %s" % drive.block_name,
            raise_on_fail=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        self._get_fw_log(drive)
        self._get_smart_log(drive)
        self._get_error_log(drive)
        self._get_nvme_ns_map(drive)
        self._get_id_ns(drive)
        self._get_feature(drive)
        self._get_internal_log(drive)
        self._get_effects_log(drive)
        self._get_vs_timestamp(drive)
        self._validate_power_mode(drive)
        self._validate_capacity(drive)
        self._check_oacs_device_self_test(drive)
        if self.crypto_erase:
            self._validate_crypto_erase_support(drive)
        if self.arbitration_mechanism:
            self._validate_arbitration_mechanism(drive)

    def _validate_arbitration_mechanism(self, drive) -> None:
        # Check arbitration_mechanism
        out = drive.get_arbitration_mechanism_status()
        if out:
            match = re.search(r"Arbitration Mechanism Selected\s+\(AMS\):\s+(.*)", out)
            if match:
                arbitration_mechanism = match.group(1)
                AutovalUtils.validate_condition(
                    "Round Robin" in arbitration_mechanism,
                    "%s: Arbitration Mechanism is %s"
                    % (drive.block_name, arbitration_mechanism),
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )
            else:
                AutovalUtils.validate_condition(
                    False,
                    "Arbitration Mechanism not found",
                    raise_on_fail=False,
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )
            # Check csts
            csts_match = re.search(r"csts\s+:\s+(\d+)", out)
            if csts_match:
                csts = int(csts_match.group(1))
                AutovalUtils.validate_equal(
                    csts,
                    1,
                    "%s: csts is %s" % (drive.block_name, csts),
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )
            else:
                AutovalUtils.validate_condition(
                    False,
                    "csts not found",
                    raise_on_fail=False,
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                )

    def _validate_crypto_erase_support(self, drive) -> None:
        out = drive.get_crypto_erase_support_status()
        if out is False:
            self.log_info(
                "Skip Crypto Erase validation on boot drive and drives "
                "which dont support it"
            )
        else:
            AutovalUtils.validate_condition(
                out,
                "%s: Crypto Erase Supported" % drive,
                raise_on_fail=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )

    def _get_fw_log(self, drive) -> None:
        out = drive.get_fw_log()
        out_json = json.loads(out)
        self.validate_greater(
            len(out_json),
            0,
            str(out_json),
            raise_on_fail=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def _get_smart_log(self, drive: NVMeDrive) -> None:
        out_json = drive.get_smart_log()
        smart_log = out_json["smart-log"]
        self.validate_greater(
            len(smart_log),
            0,
            msg=f"smart-log from drive {str(drive)} has at least one entry.",
            raise_on_fail=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def _get_error_log(self, drive: NVMeDrive) -> None:
        """
        This function retrieves the error log from the given drive.

        Args:
            drive (NVMeDrive): The drive to get the error log from.


        Returns:
            None
        """
        out = drive.get_error_log()
        out_json = json.loads(out)
        error_log = out_json["errors"]
        self.validate_greater(
            len(error_log),
            0,
            msg=f"error-log from drive {str(drive)} has at least one entry.",
            raise_on_fail=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def _get_id_ns(self, drive: NVMeDrive) -> None:
        """
        This function retrieves identity namespace results for the given drive.

        Args:
            drive (NVMeDrive): The drive to get namespace results from.

        Returns:
            None
        """
        out = drive.get_id_ns()
        out_json = json.loads(out)
        self.validate_greater(
            len(out_json),
            0,
            msg=f"ID Namespace log from drive {str(drive)} has at least one entry.",
            raise_on_fail=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def _get_nvme_ns_map(self, drive) -> None:
        n_s = NVMeUtils.get_nvme_ns_map(
            self.host, drive.block_name, drive.serial_number
        )
        for _, value in n_s.items():
            self.validate_greater_equal(
                len(value),
                1,
                "namespace is %s" % value,
                raise_on_fail=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

    def _get_feature(self, drive) -> None:
        feature_info = drive.get_feature()
        self.validate_greater(
            len(feature_info),
            0,
            "Features have been taken",
            raise_on_fail=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )

    def _get_internal_log(self, drive: NVMeDrive) -> None:
        """Gets Vendor Specific Log.

        This method gets the internal log in binary format for different
        vendors based on the drive.

        Parameters
        ----------
        drive : :obj: 'Class'
            Object of vendor class.
        """
        try:
            status = drive.get_internal_log()
            self.log_info(f"Internal log has {'' if status else 'not'} been taken")
        except NotImplementedError as exc:
            self.log_info(exc)

    def _get_effects_log(self, drive) -> None:
        """Gets Effects Log.

        This method retrieves the ACS(Admin Command Set) and
        IOCS(I/O Command Set) logs of the drive.

        Args:
            drive (NVMeDrive): The drive from which to retrieve effects logs.

        Returns:
            None
        """
        try:
            out = drive.get_effects_log()
            self.validate_greater(
                len(out),
                0,
                msg=f"effects-log from drive {str(drive)} has at least one entry.",
                raise_on_fail=False,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
        except NotImplementedError as exc:
            self.log_info(exc)

    def get_test_params(self) -> str:
        params = "Drive type: {}, Drive interface: {}, Check crypto erase: {}".format(
            self.drive_type, self.drive_interface, self.crypto_erase
        )
        return params

    def _get_vs_timestamp(self, drive) -> None:
        """Gets Vendor Specific Drive Timestamp.

        This method gets the drive up time for different
        vendors based on the drive.

        Parameters
        ----------
        drive : :obj: 'Class'
            Object of vendor class.
        """
        try:
            out = drive.get_vs_timestamp()
            # Continue if NotImplementedError not raised
            seconds = float(out)
            years = seconds / (3600 * 24 * 365.0)
            try:
                time = str(datetime.timedelta(seconds=seconds))
            except Exception:
                time = "%s years" % years
            self.log_info("Drive up time %s: %s" % (drive, time))
        except NotImplementedError as exc:
            self.log_info(exc)
        except Exception as exc:
            raise TestError(
                "get_vs_timestamp failed for drive %s: %s" % (drive, str(exc)),
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

    def _validate_power_mode(self, drive) -> None:
        """Validate Power Mode.

        This method checks for the npss (Number of Power State Support)
        of the data drive. Current M.2 data SSD's have npss 0 or 1. For
        npss more than 1 and for the data drive capacity 2TB or 4TB the
        required power mode is set to reduce the power consumption by
        nvme and validates by get power mode.

        Parameters
        ----------
        drive : :obj: 'Class'
            Object of nvme drive class.
        """
        npss = NVMeUtils.get_id_ctrl(self.host, drive.block_name)["npss"]
        if npss > 1:
            power_modes = drive.get_drive_supported_power_modes()
            for power_mode in power_modes:
                set_state = drive.set_power_mode(power_mode)
                get_state = drive.get_power_mode()
                AutovalUtils.validate_equal(
                    get_state,
                    set_state,
                    f"Correct power-mode set on /dev/{drive}",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.DRIVE_ERR,
                    raise_on_fail=False,
                )
            # Reverting the power state to 0
            set_state = drive.set_power_mode(0)
            get_state = drive.get_power_mode()
            AutovalUtils.validate_equal(
                set_state, get_state, f"Resetting power-mode PS0 on /dev/{drive} "
            )
        else:
            AutovalLog.log_info(f"/dev/{drive} supported only one power-mode")

    def _check_oacs_device_self_test(self, drive) -> None:
        """Validate Device self-test command support
        Method checks for  OACS field from id-ctrl and validates Device self-test command support

        Parameters
        ----------
        drive : :obj: 'Class'
            Object of nvme drive class.
        """
        oacs = NVMeUtils.get_id_ctrl(self.host, drive.block_name)["oacs"]
        self.log_info(f"Test to Check dev_self_test management {oacs} {hex(oacs)}")
        support_dev_self_test_management = oacs & 0x8
        AutovalUtils.validate_condition(
            support_dev_self_test_management == 0x8,
            f"Check dev_self_test management support SELF_TEST supported on /dev/{drive}",
            warning=True,
            log_on_pass=True,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        if support_dev_self_test_management == 0x0:
            AutovalLog.log_info(f"/dev/{drive} does not support self-test")
            return

    def _validate_capacity(self, drive) -> None:
        """Validate drive capacity
        Method checks for unvmcap and tnvmcap from id-ctrl and validates drive capacity

        Parameters
        ----------
        drive : :obj: 'Class'
            Object of nvme drive class.
        """
        if str(drive) == self.boot_drive:
            # namespace_management not supported on boot drive`
            return
        oacs = NVMeUtils.get_id_ctrl(self.host, drive.block_name)["oacs"]
        support_namespace_management = oacs & 0x8
        AutovalUtils.validate_condition(
            support_namespace_management and 0x8,
            f"Check namespace management support on /dev/{drive}",
            warning=True,
            log_on_pass=True,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        if support_namespace_management == 0x0:
            return
        tnvmcap = NVMeUtils.get_id_ctrl(self.host, drive.block_name)["tnvmcap"]
        nsze = NVMeUtils.get_id_ns(self.host, drive.block_name)["nsze"]
        # Compare size
        AutovalUtils.validate_greater_equal(
            tnvmcap,
            nsze,
            f"Compare Total capacity tnvmcap and nsze on /dev/{drive}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
