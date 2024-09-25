# pyre-unsafe
from unittest import mock, TestCase
from unittest.mock import call

from autoval_ssd.lib.utils.sed_util import SedUtils

from autoval_ssd.unittest.mock.lib.mock_host import MockHost


CMD_MAP = [{"cmd": None, "file": None}]


class SedUtilUnittest(TestCase):
    """unitest for the sedutil-cli library"""

    def setUp(self) -> None:
        """initializing the required variables"""
        self.mock_host = MockHost(CMD_MAP)
        self.block_name = "/dev/mock"

    @mock.patch.object(MockHost, "run")
    def test_get_sed_support_status(self, mock_host):
        """Unittest of get_sed_support_status function"""
        supported_out = f"/dev/{self.block_name} SED -2- WDC CL SN720 SDAQNTW-512G-2000           10103122"
        nonsuported_out = f"/dev/{self.block_name} NO --- KXG50ZNV256G TOSHIBA                     AAGA4102"
        # Supported
        mock_host.return_value = supported_out
        sup_result = SedUtils.get_sed_support_status(self.mock_host, self.block_name)
        self.assertTrue(sup_result)
        mock_host.assert_has_calls(
            calls=[call("sedutil-cli --isValidSED /dev//dev/mock")]
        )
        # Not Supported
        mock_host.reset_mock(return_value=True)
        mock_host.return_value = nonsuported_out
        nonsup_result = SedUtils.get_sed_support_status(self.mock_host, self.block_name)
        self.assertFalse(nonsup_result)
        mock_host.assert_has_calls(
            calls=[call("sedutil-cli --isValidSED /dev//dev/mock")]
        )

    @mock.patch.object(MockHost, "run")
    def test_opal_support_scan(self, mock_host):
        """Unittest of opal_support_scan function"""
        mock_output = (
            "Scanning for Opal compliant disks\n"
            "/dev/nvme0  2  SAMSUNG MZ1LB960HAJQ-000FB               EDA75F2Q\n"
            "The Kernel flag libata.allow_tpm is not set correctly\n"
            "Please see the readme note about setting the libata.allow_tpm\n"
            "/dev/sda   No  SanDisk SD9SN8W256G1020                  X6101020\n"
            "The Kernel flag libata.allow_tpm is not set correctly\n"
            "Please see the readme note about setting the libata.allow_tpm\n"
            "/dev/sdb   No\n"
        )
        opal_complaint = ["nvme0"]
        opal_non_complaint = ["sda", "sdb"]
        mock_host.return_value = mock_output
        opal_list, non_opal_list = SedUtils.opal_support_scan(self.mock_host)
        self.assertListEqual(opal_complaint, opal_list)
        self.assertListEqual(opal_non_complaint, non_opal_list)
        mock_host.assert_has_calls(calls=[call("sedutil-cli --scan")])

    @mock.patch.object(MockHost, "run")
    def test_get_msid(self, mock_host):
        """Unittest for get_msid."""
        mock_out = "MSID: MSIDMSIDMSIDMSIDMSIDMSIDMSIDMSID"
        mock_host.return_value = mock_out
        out = SedUtils.get_msid(self.mock_host, self.block_name)
        self.assertEqual(out, "MSIDMSIDMSIDMSIDMSIDMSIDMSIDMSID")
        mock_host.assert_has_calls(
            calls=[call("sedutil-cli --printDefaultPassword /dev//dev/mock")]
        )

    @mock.patch.object(MockHost, "run")
    def test_check_locked_status(self, mock_host):
        """Unittest for check_locked_status."""
        mock_out = (
            "    Locked = N, LockingEnabled = N, LockingSupported = Y, "
            "MBRDone = N, MBREnabled = N, MediaEncrypt = Y"
        )
        mock_host.return_value = mock_out
        out = SedUtils.check_locked_status(self.mock_host, self.block_name)
        self.assertEqual(out, False)
        mock_host.assert_has_calls(calls=[call("sedutil-cli --query /dev//dev/mock")])
