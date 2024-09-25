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

        mock_get_flag.assert_called()
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
