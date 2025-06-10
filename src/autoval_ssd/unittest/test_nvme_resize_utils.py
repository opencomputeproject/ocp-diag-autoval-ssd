# pyre-unsafe
import unittest
from unittest import mock

from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_utils import AutovalUtils

from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils

from autoval_ssd.unittest.mock.lib.mock_host import MockHost

CMD_MAP = []
BYTES_PER_TB = 1000**4


class NvmeResizeUtilUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_host = MockHost(cmd_map=CMD_MAP)

    def test_get_flag(self):
        """
        Unittest for get_flag
        """
        cmd = "nvme id-ns -n 1 /dev/nvme0n1 | grep 'in use'"
        mock_output_valid = "lbads:12"
        self.mock_host.update_cmd_map(cmd, mock_output_valid)
        out = NvmeResizeUtil.get_flag(
            self.mock_host, "nvme0n1", "lbads", r"lbads:(\d+)"
        )
        self.assertEqual(out, 12)
        mock_output_invalid = "invalid"
        self.mock_host.update_cmd_map(cmd, mock_output_invalid)
        with self.assertRaises(TestError) as exp:
            out = NvmeResizeUtil.get_flag(self.mock_host, "nvme0n1", "lbads", r"(\d+)")
        self.assertEqual(
            "[AUTOVAL TEST ERROR] Failed to find lbads flag for drive in nvme0n1",
            str(exp.exception),
        )

    @mock.patch.object(NvmeResizeUtil, "get_nvme_with_namespace")
    @mock.patch.object(NVMeUtils, "get_id_ns")
    def test_get_nvmcap(self, mock_get_id_ns, mock_get_nvme):
        """
        Unittest for get_nvmcap
        """
        mock_get_id_ns.return_value = {"nvmcap": 7675106557952}
        mock_get_nvme.return_value = ["nvme0n1"]
        out = NvmeResizeUtil.get_nvmcap(self.mock_host, ["nvme0n1"])
        self.assertEqual(out, [7675106557952])

    def test_validate_num_bytes_less_equal_max_bytes(self):
        """
        Unittest for validate_num_bytes_less_equal_max_bytes
        """
        max_bytes = int(1.8 * (BYTES_PER_TB))
        num_bytes = int((1.8 * (BYTES_PER_TB)) - 1)
        NvmeResizeUtil.validate_num_bytes_less_equal_max_bytes(num_bytes, max_bytes)

    @mock.patch.object(NvmeResizeUtil, "get_nsid_list")
    @mock.patch.object(NvmeResizeUtil, "get_lbaf_details")
    @mock.patch.object(NvmeResizeUtil, "get_flag")
    @mock.patch.object(NVMeUtils, "detach_ns")
    @mock.patch.object(NVMeUtils, "delete_ns")
    @mock.patch.object(NVMeUtils, "create_ns")
    @mock.patch.object(NVMeUtils, "attach_ns")
    @mock.patch.object(NVMeUtils, "reset")
    @mock.patch.object(NVMeUtils, "get_id_ns")
    @mock.patch.object(AutovalUtils, "validate_equal")
    @mock.patch.object(MockHost, "run")
    def test_ns_resize(
        self,
        mock_run,
        mock_validate_equal,
        mock_get_id_ns,
        mock_reset,
        mock_attach_ns,
        mock_create_ns,
        mock_delete_ns,
        mock_detach_ns,
        mock_get_flag,
        mock_get_lbaf_details,
        mock_get_nsid_list,
    ) -> None:
        # Postive Case

        mock_nvme_id_ctrls = {
            "nvme1": {
                "vid": 5197,
                "ssvid": 5197,
                "sn": "S7BFNG0W600310      ",
                "cntlid": 7,
                "ver": 131072,
                "rtd3r": 8000000,
                "rtd3e": 8000000,
                "oaes": 25344,
                "tnvmcap": 7521470078976,
                "unvmcap": 1711553679360,
                "psds": [
                    {
                        "max_power": 3500,
                        "flags": 0,
                    }
                ],
                "orig_ncap": 918329013,
                "orig_nsze": 918329013,
            }
        }
        mock_sweep_param_unit = NvmeResizeUtil.SweepParamUnitEnum.percent
        mock_sweep_param_key = NvmeResizeUtil.SweepParamKeyEnum.overprovisioning
        mock_get_lbaf_details.return_value = {"lbaf": 0, "lbads": 12, "ms": 0}
        mock_get_nsid_list.return_value = [1, 2]
        mock_get_flag.return_value = 12
        mock_device = "nvme1"
        mock_sweep_param_value = 50

        NvmeResizeUtil.ns_resize(
            self.mock_host,  # type: ignore
            mock_nvme_id_ctrls,
            mock_sweep_param_unit,
            mock_sweep_param_key,
            mock_device,
            mock_sweep_param_value,
        )

        mock_detach_ns.assert_called()
        mock_delete_ns.assert_called()
        mock_create_ns.assert_called()
        mock_attach_ns.assert_called()
        mock_reset.assert_called()
        mock_get_id_ns.assert_called()
        mock_validate_equal.assert_called()

        # Negative Case

        mock_nvme_id_ctrls = {
            "nvme1": {
                "vid": 5197,
                "ssvid": 5197,
                "sn": "S7BFNG0W600310      ",
                "ver": 131072,
                "rtd3r": 8000000,
                "rtd3e": 8000000,
                "oaes": 25344,
                "ctratt": 524944,
                "tnvmcap": 7521470078976,
                "unvmcap": 1711553679360,
                "psds": [
                    {
                        "max_power": 3500,
                        "flags": 0,
                    }
                ],
                "orig_ncap": 918329013,
                "orig_nsze": 918329013,
            }
        }
        mock_run.return_value = """Node SN Model Namespace Usage Format FW Rev
        /dev/nvme0n1 S761NC0W701008  MZUL21T0HCLR-00AFB 1 35.57  GB / 819.37  GB    512   B +  0 B   GDAD2F1Q
        /dev/nvme2n1    S7BFNG0W600105  MZOL67T6HDLA-00AFB  1  3.35  TB /   3.76  TB  4 KiB +  0 B  LDA64F2Q
        /dev/nvme11n1   S7BFNG0W600350  MZOL67T6HDLA-00AFB 1 3.35  TB /   3.76  TB  4 KiB +  0 B   LDA64F2Q"""

        with self.assertRaises(TestError) as exp:
            NvmeResizeUtil.ns_resize(
                self.mock_host,  # type: ignore
                mock_nvme_id_ctrls,
                mock_sweep_param_unit,
                mock_sweep_param_key,
                mock_device,
                mock_sweep_param_value,
            )

        self.assertEqual(
            "[AUTOVAL TEST ERROR] nvme1: cannot parse id-ctrl attr: 'cntlid'",
            str(exp.exception),
        )
        expected_device_was_deleted = mock_device + "n1" not in mock_run.return_value
        # Assert that device_was_deleted is True
        self.assertTrue(expected_device_was_deleted)

    def test_get_lbaf_details(self):
        """
        Unittest for get_lbaf_details
        """
        cmd = "nvme id-ns -n 1 /dev/nvme1 | grep 'in use'"
        mock_output_valid = "lbaf  0 : ms:0   lbads:12  rp:0x2 (in use)"
        self.mock_host.update_cmd_map(cmd, mock_output_valid)
        out = NvmeResizeUtil.get_lbaf_details(self.mock_host, "nvme1")
        self.assertEqual(out, {"lbaf": 0, "ms": 0, "lbads": 12})

        mock_output_invalid = ""
        self.mock_host.update_cmd_map(cmd, mock_output_invalid)
        with self.assertRaises(TestError) as exp:
            out = NvmeResizeUtil.get_lbaf_details(self.mock_host, "nvme1")
        self.assertEqual(
            "[AUTOVAL TEST ERROR] Failed to find an 'in use' lbaf for drive nvme1n1",
            str(exp.exception),
        )

    def test_get_reported_capacity(self):
        """
        Unittest for get_index_of_closest_capacity
        """
        _, index = NvmeResizeUtil.get_reported_capacity(int(1 * (BYTES_PER_TB)))
        self.assertEqual(index, 1)

        _, index = NvmeResizeUtil.get_reported_capacity(
            int((2 * (BYTES_PER_TB)) + 1000)
        )
        self.assertEqual(index, 3)

        _, index = NvmeResizeUtil.get_reported_capacity(
            int((3 * (BYTES_PER_TB)) - 1000)
        )
        self.assertEqual(index, 3)

        _, index = NvmeResizeUtil.get_reported_capacity(int(4 * (BYTES_PER_TB)))
        self.assertEqual(index, 4)

    @mock.patch.object(MockHost, "run")
    def test_get_lbaf_to_flbas_map(self, mock_run):
        """
        Unittest for get_lbaf_to_flbas_map
        """
        mock_run.return_value = """ [3:0] : 0     Current LBA Format Selected
        LBA Format  0 : Metadata Size: 0   bytes - Data Size: 4096 bytes - Relative Performance: 0 Best (in use)
        LBA Format  1 : Metadata Size: 64  bytes - Data Size: 4096 bytes - Relative Performance: 0 Best
        LBA Format  2 : Metadata Size: 0   bytes - Data Size: 512 bytes - Relative Performance: 0 Best """

        out = NvmeResizeUtil.get_lbaf_to_flbas_map(self.mock_host, "nvme0n1")
        self.assertEqual(out, {"512": 2, "4096": 0, "4096+64": 1})

    def test_get_nsid_list(self):
        """
        Unittest for get_nsid_list
        """
        cmd = "nvme list-ns /dev/nvme1n1"
        mock_output_valid = """[ 0]:0x1
                               [ 1]:0x2"""
        self.mock_host.update_cmd_map(cmd, mock_output_valid)
        out = NvmeResizeUtil.get_nsid_list(self.mock_host, "nvme1n1")
        self.assertEqual(out, [1, 2])

    @mock.patch.object(NVMeUtils, "detach_ns")
    @mock.patch.object(NVMeUtils, "delete_ns")
    def test_detach_delete_ns(
        self,
        mock_delete_ns,
        mock_detach_ns,
    ):
        """
        Test the detachment and deletion of namespaces for a given NVMe device.
        """

        nsid_values = [1, 2]
        device = "/dev/nvme0"
        cntlid = 1

        NvmeResizeUtil.detach_delete_ns(self.mock_host, device, cntlid, nsid_values)

        mock_detach_ns.assert_any_call(self.mock_host, device, 1, cntlid)
        mock_detach_ns.assert_any_call(self.mock_host, device, 2, cntlid)

        mock_delete_ns.assert_any_call(self.mock_host, device, 1)
        mock_delete_ns.assert_any_call(self.mock_host, device, 2)

    @mock.patch.object(NVMeUtils, "create_ns")
    @mock.patch.object(NVMeUtils, "attach_ns")
    @mock.patch.object(NVMeUtils, "reset")
    def test_create_attach_ns(self, mock_reset, mock_attach_ns, mock_create_ns):
        """
        Test the creation and attachment of a namespace for a given NVMe device.
        """

        device = "/dev/nvme0"
        nsize = 4096
        ncap = 4096
        block_size = 4096
        flbas_flag = 0
        nsid = 1
        cntlid = 1

        NvmeResizeUtil.create_attach_ns(
            self.mock_host, device, nsize, ncap, flbas_flag, nsid, cntlid, block_size
        )

        mock_create_ns.assert_called_once_with(
            self.mock_host, device, nsize, ncap, block_size, flbas_flag
        )
        mock_attach_ns.assert_called_once_with(self.mock_host, device, nsid, cntlid)
        mock_reset.assert_called_once_with(self.mock_host, device)
