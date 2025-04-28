#!/usr/bin/env python3

# pyre-strict

import json
import os
import re
from typing import Any, Dict, List

from autoval.lib.host.component.component import COMPONENT

from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval_ssd.lib.utils.storage.nvme.nvme_drive import NVMeDrive
from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.system_utils import SystemUtils


class FDPUtils:
    """
    This class provides methods for FDP test cases.
    """

    @staticmethod
    def validate_fdp_support(host: Host, nvme_id_ctrls: Dict[str, Any]) -> None:
        """
        This function checks if the FDP is supported for each test drive and also validates the FDP config.
        Args:
            host: The host object where the FDP support is validated.
            nvme_id_ctrls: A dictionary mapping NVMe device identifiers to their controller information.
        """
        AutovalLog.log_info("Validating FDP support")
        original_nvme_version = NVMeUtils.get_nvme_version(host)
        nvme_installed = FDPUtils.validate_nvme_version(host)

        nvme_ctrls = [*nvme_id_ctrls]  # Device List
        for device in nvme_ctrls:
            ctratt_value = nvme_id_ctrls[device]["ctratt"]
            bit_19 = ctratt_value & (1 << 19)
            AutovalUtils.validate_not_equal(
                bit_19,
                0,
                f"{device}: Supports FDP",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
                log_on_pass=True,
            )

            fdp_config_out = FDPUtils.get_fdp_config(host, device)

            relative_cfg_file_path = os.path.join("/cfg/", "fdp_config.json")
            abs_path = NVMeDrive.get_target_path()
            fdp_cfg_path = abs_path + relative_cfg_file_path

            fdp_threshold_obj_dict = {}
            with open(fdp_cfg_path) as f:
                data = f.read()
                fdp_threshold_obj_dict = json.loads(data)

            errors = FDPUtils.validate_fdp_config(
                fdp_config_out, fdp_threshold_obj_dict
            )

            AutovalUtils.validate_empty_list(
                errors,
                f"{device}: FDP Config Validation Errors",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )
        if nvme_installed:
            SystemUtils.install_rpms(host, [f"nvme-cli-{original_nvme_version}"])

    @staticmethod
    def validate_nvme_version(host: Host) -> bool:
        """
        This function validates the NVMe version on the host.
        If the NVMe version is not 2.10 or higher, it installs the nvme-cli-2.10.2 package and validates again.

        Args:
            host: The host object where the NVMe version is validated.

        Returns:
            A boolean indicating whether the new NVMe version was installed.

        Raises:
            TestError: If the NVMe version is not 2.10 or higher.
        """
        nvme_installed = False
        nvme_version = NVMeUtils.get_nvme_version(host)

        # This install will be removed once we have nvme-cli-2.10.2 or higher as default on all hosts
        if not NVMeUtils.compare_versions("2.10.0", nvme_version):
            AutovalLog.log_info(
                f"Current NVMe version '{nvme_version}' does not support FDP validation. Installing nvme-cli-2.10.2"
            )
            SystemUtils.install_rpms(host, ["nvme-cli-2.10.2", "libnvme-1.10"])
            nvme_version = NVMeUtils.get_nvme_version(host)
            nvme_installed = True

        AutovalUtils.validate_condition(
            NVMeUtils.compare_versions("2.10.0", nvme_version),
            "NVMe version 2.10 or higher required for FDP validation",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
            log_on_pass=True,
        )
        return nvme_installed

    @staticmethod
    def get_fdp_config(host: Host, device: str) -> Dict[str, Any]:
        """
        This function gets the FDP configuration for a given device.

        Args:
            host: The host object where the FDP configuration is retrieved.
            device: The device identifier for which the FDP configuration is retrieved.

        Returns:
            A dictionary containing the FDP configuration for the specified device.
        """
        fdp_config_cmd = f"nvme fdp configs /dev/{device} -e 1"
        fdp_output = host.run(fdp_config_cmd)

        fdp_dict = {}

        patterns = {
            "reclaim_groups": r"Number of Reclaim Groups:\s+(\d+)",
            "reclaim_unit_handles": r"Number of Reclaim Unit Handles:\s+(\d+)",
            "namespaces_supported": r"Number of Namespaces Supported:\s+(\d+)",
            "reclaim_unit_handle_list": r"Reclaim Unit Handle List:\s+(.*?)(?=\n\S|\Z)",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, fdp_output, re.DOTALL)
            if match:
                value = match.group(1)
                if key == "reclaim_unit_handle_list":
                    fdp_dict[key] = [
                        line.strip()
                        for line in value.splitlines()
                        if line.strip().startswith("[")
                    ]
                else:
                    fdp_dict[key] = int(value)

        return fdp_dict

    @staticmethod
    def validate_fdp_config(
        fdp_config_out: Dict[str, Any], expected_fdp_config: Dict[str, Any]
    ) -> List[str]:
        """
        Validates the FDP configuration against expected values.

        Args:
            fdp_config_out: A dictionary containing the FDP configuration output.
            expected_fdp_config: A dictionary containing the expected FDP configuration values.

        Returns:
            A list of error messages indicating any mismatches between the actual and expected FDP configuration values.
        """
        errors = []
        for key, threshold in expected_fdp_config.items():
            actual_value = fdp_config_out.get(key)
            if key == "namespaces_supported":
                if int(actual_value) < int(threshold.get("value")):
                    errors.append(
                        f'{key} mismatch: Actual value: {actual_value} is less than Expected minimum: {threshold.get("value")}'
                    )
            elif actual_value != threshold.get("value"):
                errors.append(
                    f'{key} mismatch: Actual value: {actual_value}, Expected value: {threshold.get("value")}'
                )

        actual_reclaim_list = fdp_config_out.get("reclaim_unit_handle_list")
        if actual_reclaim_list:
            for index, handle in enumerate(actual_reclaim_list):
                if "Initially Isolated" not in handle:
                    errors.append(
                        f"Reclaim unit handle [{index}] is not 'Initially Isolated': {handle}"
                    )
        else:
            errors.append("reclaim_unit_handle_list is missing or empty.")

        return errors

    @staticmethod
    def fdp_setup(host: Host, nvme_id_ctrls: Dict[str, Any]) -> None:
        """
        This function sets up the FDP (Flash Data Path) for NVMe drives.

        Args:
            host: The host object where the FDP setup is performed.
            nvme_id_ctrls: A dictionary mapping NVMe device identifiers to their controller information.
        """
        nvme_ctrls = [*nvme_id_ctrls]  # Device List

        for device in nvme_ctrls:
            AutovalLog.log_info(f"Setting up FDP with 4k LBAF for {device}")
            cntlid = None
            tnvmcap = None
            try:
                cntlid = nvme_id_ctrls[device]["cntlid"]
                tnvmcap = nvme_id_ctrls[device]["tnvmcap"]
            except KeyError as exc:
                raise TestError(
                    f"{device}: cannot parse id-ctrl attr: {str(exc)}",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.NVME_ERR,
                )
            nsid_values = NvmeResizeUtil.get_nsid_list(host, device)
            if nsid_values:
                NvmeResizeUtil.detach_delete_ns(host, device, cntlid, nsid_values)

            AutovalUtils.validate_condition(
                NVMeUtils.set_fdp(host, device, enable=True),
                f"{device}: Enable FDP",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )

            AutovalUtils.validate_condition(
                NVMeUtils.get_fdp_status(host, device),
                f"{device}: Confirm FDP is Enabled",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )

            nvmcap = int(int(tnvmcap) / 4096)
            nsid = nsid_values[0] if nsid_values else 1
            current_lbaf_details = NvmeResizeUtil.get_lbaf_details(host, device)
            flbas_flag = current_lbaf_details["lbaf"]
            block_size = 4096

            NvmeResizeUtil.create_attach_ns(
                host,
                device,
                nsize=nvmcap,
                ncap=nvmcap,
                flbas_flag=flbas_flag,
                nsid=nsid,
                cntlid=cntlid,
                block_size=block_size,
            )

            namespace = f"{device}n{nsid}"
            lbaf_to_flbas_map = NvmeResizeUtil.get_lbaf_to_flbas_map(host, namespace)
            lbaf = lbaf_to_flbas_map["4096"]
            AutovalUtils.validate_no_exception(
                NVMeUtils.format_nvme,
                [host, namespace, 0, None, f" -l {lbaf}"],
                f"{namespace}: Format with LBA 4096",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )

    @staticmethod
    def fdp_cleanup(host: Host, nvme_id_ctrls: Dict[str, Any]) -> None:
        """
        Cleans up the FDP (Flash Data Path) setup for NVMe drives by detaching and deleting namespaces and disabling FDP.

        Args:
            host: The host object where the FDP cleanup is performed.
            nvme_id_ctrls: A dictionary mapping NVMe device identifiers to their controller information.
        """
        nvme_ctrls = [*nvme_id_ctrls]  # Device List

        for device in nvme_ctrls:
            AutovalLog.log_info(f"Disabling FDP for {device}")
            cntlid = None
            try:
                cntlid = nvme_id_ctrls[device]["cntlid"]
            except KeyError as exc:
                raise TestError(
                    f"{device}: cannot parse id-ctrl attr: {str(exc)}",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.NVME_ERR,
                )
            nsid_values = NvmeResizeUtil.get_nsid_list(host, device)
            if nsid_values:
                NvmeResizeUtil.detach_delete_ns(host, device, cntlid, nsid_values)

            AutovalUtils.validate_condition(
                NVMeUtils.set_fdp(host, device, enable=False),
                f"{device}: Disable FDP",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )
            AutovalUtils.validate_condition(
                not NVMeUtils.get_fdp_status(host, device),
                f"{device}: Confirm FDP is Disabled",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )

            try:
                cntlid = nvme_id_ctrls[device]["cntlid"]
                tnvmcap = nvme_id_ctrls[device]["tnvmcap"]
                flbas_flag = nvme_id_ctrls[device]["original_lbaf_details"]["lbaf"]
            except KeyError as exc:
                raise TestError(
                    f"{device}: cannot parse id-ctrl attr: {str(exc)}",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.NVME_ERR,
                )
            nsid_values = NvmeResizeUtil.get_nsid_list(host, device)
            nvmcap = int(int(tnvmcap) / 4096)
            nsid = nsid_values[0] if nsid_values else 1

            NvmeResizeUtil.create_attach_ns(
                host,
                device,
                nsize=nvmcap,
                ncap=nvmcap,
                flbas_flag=flbas_flag,
                nsid=nsid,
                cntlid=cntlid,
            )
