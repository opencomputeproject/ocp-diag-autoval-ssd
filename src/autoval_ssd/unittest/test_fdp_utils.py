#!/usr/bin/env python3

# pyre-unsafe
import unittest

from unittest import mock

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval_ssd.lib.utils.storage.nvme.fdp_utils import FDPUtils
from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil

from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.unittest.mock.lib.mock_host import MockHost


class FDPUtilsUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.host = MockHost(cmd_map=[])
        self.fdp_config = {
            "reclaim_groups": {"value": 1},
            "reclaim_unit_handles": {"value": 8},
            "namespaces_supported": {"value": 2},
        }

    @mock.patch.object(AutovalUtils, "validate_condition")
    @mock.patch.object(AutovalUtils, "validate_empty_list")
    @mock.patch.object(AutovalUtils, "validate_not_equal")
    @mock.patch.object(NVMeUtils, "get_nvme_version", return_value="2.9.0")
    @mock.patch.object(FDPUtils, "get_fdp_config")
    def test_validate_fdp_support_successful(
        self,
        mock_get_fdp_config,
        mock_get_nvme_version,
        mock_validate_not_equal,
        mock_validate_empty_list,
        mock_validate_condition,
    ):
        """
        Test case: FDP supported and config validation passed
        """
        nvme_id_ctrls = {
            "nvme1": {"ctratt": 0x80290},  # 19th bit set to 1
        }

        mock_get_fdp_config.return_value = {
            "reclaim_groups": 1,
            "reclaim_unit_handles": 8,
            "namespaces_supported": 3,
            "reclaim_unit_handle_list": [
                "[0]: Initially Isolated",
                "[1]: Initially Isolated",
                "[2]: Initially Isolated",
                "[3]: Initially Isolated",
                "[4]: Initially Isolated",
                "[5]: Initially Isolated",
                "[6]: Initially Isolated",
                "[7]: Initially Isolated",
            ],
        }

        FDPUtils.validate_fdp_support(self.host, nvme_id_ctrls)
        mock_validate_not_equal.assert_any_call(
            0x80290 & (1 << 19),
            0,
            "nvme1: Supports FDP",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
            log_on_pass=True,
        )

        mock_validate_empty_list.assert_any_call(
            [],
            "nvme1: FDP Config Validation Errors",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )

    @mock.patch.object(AutovalUtils, "validate_condition")
    @mock.patch.object(AutovalUtils, "validate_empty_list")
    @mock.patch.object(AutovalUtils, "validate_not_equal")
    @mock.patch.object(NVMeUtils, "get_nvme_version", return_value="2.9.0")
    @mock.patch.object(FDPUtils, "get_fdp_config")
    def test_validate_fdp_support_config_validation_failed(
        self,
        mock_get_fdp_config,
        mock_get_nvme_version,
        mock_validate_not_equal,
        mock_validate_empty_list,
        mock_validate_condition,
    ):
        """
        Test case: FDP supported but config validation failed
        """
        nvme_id_ctrls = {
            "nvme1": {"ctratt": 0x80290},  # 19th bit set to 1
        }

        mock_get_fdp_config.return_value = {
            "reclaim_groups": 1,
            "reclaim_unit_handles": 8,
            "namespaces_supported": 1,
            "reclaim_unit_handle_list": [
                "[0]: Initially Isolated",
                "[1]: Initially Isolated",
                "[2]: Initially Isolated",
                "[3]: Initially Isolated",
                "[4]: Initially Isolated",
                "[5]: Initially Isolated",
                "[6]: Initially Isolated",
                "[7]: Initially Isolated",
            ],
        }

        FDPUtils.validate_fdp_support(self.host, nvme_id_ctrls)
        mock_validate_empty_list.assert_any_call(
            [
                "namespaces_supported mismatch: Actual value: 1 is less than Expected minimum: 2",
            ],
            "nvme1: FDP Config Validation Errors",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )

    @mock.patch.object(AutovalUtils, "validate_condition")
    @mock.patch.object(AutovalUtils, "validate_empty_list")
    @mock.patch.object(AutovalUtils, "validate_not_equal")
    @mock.patch.object(FDPUtils, "validate_fdp_config")
    @mock.patch.object(NVMeUtils, "get_nvme_version", return_value="1.11.2")
    def test_validate_fdp_support_low_version(
        self,
        mock_get_nvme_version,
        mock_validate_fdp_config,
        mock_validate_not_equal,
        mock_validate_empty_list,
        mock_validate_condition,
    ):
        """
        Test case: NVMe version is lower than required (2.9)
        """
        nvme_id_ctrls = {
            "nvme2": {"ctratt": 0x290},  # 19th bit set to 0
        }
        FDPUtils.validate_fdp_support(self.host, nvme_id_ctrls)
        mock_validate_condition.assert_called_once_with(
            False,
            "NVMe version 2.10 or higher required for FDP validation",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
            log_on_pass=True,
        )

    def test_get_fdp_config(self):
        """
        Test case: Verify that get_fdp_config correctly parses valid FDP output.
        """
        output = """
            Number of Reclaim Groups: 1
            Number of Reclaim Unit Handles: 8
            Number of Namespaces Supported: 2
            Reclaim Unit Handle List:
            [0]: Initially Isolated
            [1]: Initially Isolated
            [2]: Initially Isolated
            [3]: Initially Isolated
            [4]: Initially Isolated
            [5]: Initially Isolated
            [6]: Initially Isolated
            [7]: Initially Isolated
        """
        device = "nvme1"
        self.host.update_cmd_map(f"nvme fdp configs /dev/{device} -e 1", output)

        expected_result = {
            "reclaim_groups": 1,
            "reclaim_unit_handles": 8,
            "namespaces_supported": 2,
            "reclaim_unit_handle_list": [
                "[0]: Initially Isolated",
                "[1]: Initially Isolated",
                "[2]: Initially Isolated",
                "[3]: Initially Isolated",
                "[4]: Initially Isolated",
                "[5]: Initially Isolated",
                "[6]: Initially Isolated",
                "[7]: Initially Isolated",
            ],
        }

        result = FDPUtils.get_fdp_config(self.host, device)
        self.assertEqual(result, expected_result)

    def test_validate_fdp_config_positive(self):
        """
        Unittest for validate_fdp_config
        """
        output = {
            "reclaim_groups": 1,
            "reclaim_unit_handles": 8,
            "namespaces_supported": 2,
            "reclaim_unit_handle_list": [
                "[0]: Initially Isolated",
                "[1]: Initially Isolated",
                "[2]: Initially Isolated",
                "[3]: Initially Isolated",
                "[4]: Initially Isolated",
                "[5]: Initially Isolated",
                "[6]: Initially Isolated",
                "[7]: Initially Isolated",
            ],
        }
        errors = FDPUtils.validate_fdp_config(output, self.fdp_config)
        self.assertEqual(errors, [])

    def test_validate_fdp_config_negative(self):
        """
        Unittest for validate_fdp_config negative case
        """
        mismatched_output = {
            "reclaim_groups": 2,
            "reclaim_unit_handles": 8,
            "namespaces_supported": 1,
            "reclaim_unit_handle_list": [
                "[0]: Initially Isolated",
                "[1]: Not Isolated",
                "[2]: Initially Isolated",
                "[3]: Initially Isolated",
                "[4]: Initially Isolated",
                "[5]: Not Isolated",
                "[6]: Initially Isolated",
                "[7]: Initially Isolated",
            ],
        }

        expected_errors = [
            "reclaim_groups mismatch: Actual value: 2, Expected value: 1",
            "namespaces_supported mismatch: Actual value: 1 is less than Expected minimum: 2",
            "Reclaim unit handle [1] is not 'Initially Isolated': [1]: Not Isolated",
            "Reclaim unit handle [5] is not 'Initially Isolated': [5]: Not Isolated",
        ]
        errors = FDPUtils.validate_fdp_config(mismatched_output, self.fdp_config)
        self.assertEqual(errors, expected_errors)

    @mock.patch.object(NvmeResizeUtil, "create_attach_ns")
    @mock.patch.object(NvmeResizeUtil, "get_lbaf_details")
    @mock.patch.object(NvmeResizeUtil, "detach_delete_ns")
    @mock.patch.object(NvmeResizeUtil, "get_nsid_list")
    @mock.patch.object(NvmeResizeUtil, "get_lbaf_to_flbas_map")
    @mock.patch.object(AutovalUtils, "validate_no_exception")
    @mock.patch.object(NVMeUtils, "get_fdp_status")
    @mock.patch.object(NVMeUtils, "set_fdp")
    def test_fdp_setup(
        self,
        mock_set_fdp,
        mock_get_fdp_status,
        mock_validate_no_exception,
        mock_get_lbaf_to_flbas_map,
        mock_get_nsid_list,
        mock_detach_delete_ns,
        mock_get_lbaf_details,
        mock_create_attach_ns,
    ):
        """
        Test the successful setup of FDP for one NVMe drive.
        """
        nvme_id_ctrls = {
            "/dev/nvme0": {"cntlid": 1, "tnvmcap": 4096000},
        }

        mock_get_nsid_list.return_value = ["1"]
        mock_set_fdp.return_value = True
        mock_get_fdp_status.return_value = True
        mock_get_lbaf_details.return_value = {"lbaf": 0}
        mock_get_lbaf_to_flbas_map.return_value = {"512": 2, "4096": 0, "4096+64": 1}

        FDPUtils.fdp_setup(self.host, nvme_id_ctrls)

        mock_detach_delete_ns.assert_called_once_with(self.host, "/dev/nvme0", 1, ["1"])

        mock_set_fdp.assert_called_once_with(self.host, "/dev/nvme0", enable=True)
        mock_get_fdp_status.assert_called_once_with(self.host, "/dev/nvme0")

        mock_create_attach_ns.assert_called_once_with(
            self.host,
            "/dev/nvme0",
            nsize=1000,
            ncap=1000,
            block_size=4096,
            flbas_flag=0,
            nsid="1",
            cntlid=1,
        )

        mock_validate_no_exception.assert_any_call(
            NVMeUtils.format_nvme,
            [self.host, "/dev/nvme0n1", 0, None, " -l 0"],
            "/dev/nvme0n1: Format with LBA 4096",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )

    @mock.patch.object(NvmeResizeUtil, "create_attach_ns")
    @mock.patch.object(AutovalUtils, "validate_condition")
    @mock.patch.object(NvmeResizeUtil, "detach_delete_ns")
    @mock.patch.object(NvmeResizeUtil, "get_nsid_list")
    @mock.patch.object(NVMeUtils, "get_fdp_status")
    @mock.patch.object(NVMeUtils, "set_fdp")
    def test_fdp_cleanup(
        self,
        mock_set_fdp,
        mock_get_fdp_status,
        mock_get_nsid_list,
        mock_detach_delete_ns,
        mock_validate_condition,
        mock_create_attach_ns,
    ):
        """
        Test the cleanup process of FDP for one NVMe drive.
        """

        nvme_id_ctrls = {
            "/dev/nvme0": {
                "cntlid": 1,
                "tnvmcap": 4096000,
                "original_lbaf_details": {"lbaf": 0},
            },
        }

        mock_get_nsid_list.return_value = ["1"]
        mock_set_fdp.return_value = True
        mock_get_fdp_status.return_value = False

        FDPUtils.fdp_cleanup(self.host, nvme_id_ctrls)

        mock_detach_delete_ns.assert_called_once_with(self.host, "/dev/nvme0", 1, ["1"])
        mock_set_fdp.assert_called_once_with(self.host, "/dev/nvme0", enable=False)
        mock_get_fdp_status.assert_called_once_with(self.host, "/dev/nvme0")
        mock_validate_condition.assert_any_call(
            True,
            "/dev/nvme0: Disable FDP",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        mock_validate_condition.assert_any_call(
            True,
            "/dev/nvme0: Confirm FDP is Disabled",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        mock_create_attach_ns.assert_called_once_with(
            self.host,
            "/dev/nvme0",
            nsize=1000,
            ncap=1000,
            flbas_flag=0,
            nsid="1",
            cntlid=1,
        )
