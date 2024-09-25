# pyre-unsafe
import unittest

from autoval.lib.utils.autoval_exceptions import TestError

from autoval_ssd.lib.utils.lsi_utils import LsiUtils
from autoval_ssd.unittest.mock.lib.mock_host import MockHost

mock_lsi_util_result = (
    r"LSI Logic MPT Configuration Utility, Version 1.71, Sep 18, 2013"
    r"1 MPT Port found"
)

CMD_MAP = [
    {"cmd": "lsiutil 0", "result": mock_lsi_util_result},
    {
        "cmd": "lsiutil -p 1 -a 13,0,0,0 20",
        "result": "Adapter Phy 0 counters have been cleared",
    },
]


class LsiUtilsUnittest(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_host = MockHost(cmd_map=CMD_MAP)

    def test_get_phy_counters(self):
        """unit test for get_phy_counters"""
        cmd = "lsiutil 0"
        mock_lsi_util_result = (
            r"LSI Logic MPT Configuration Utility, Version 1.71, Sep 18, 2013"
            r"1 MPT Port found"
        )
        self.mock_host.update_cmd_map(cmd, mock_lsi_util_result)
        cmd = "lsiutil -a 12,0,0,0, 20 -p 1"
        mock_result = (
            "Adapter Phy 0:  Link Up\n"
            "Invalid DWord Count                                           4\n"
            "Running Disparity Error Count                                 0\n"
            "Loss of DWord Synch Count                                     1\n"
            "Phy Reset Problem Count                                       0\n"
            "Expander (Handle 0009) Phy 1:  Link Up\n"
            "Invalid DWord Count                                           4\n"
            "Running Disparity Error Count                                 0\n"
            "Loss of DWord Synch Count                                     1\n"
            "Phy Reset Problem Count                                       0\n"
        )
        self.mock_host.update_cmd_map(cmd, mock_result)
        out = LsiUtils.get_phy_counters(self.mock_host)
        expected_out = {
            1: {
                "adapter": {
                    0: {
                        "invalid_word": 4,
                        "running_disparity": 0,
                        "loss_of_dword_sync": 1,
                        "phy_reset_problem": 0,
                    }
                },
                "0009": {
                    1: {
                        "invalid_word": 4,
                        "running_disparity": 0,
                        "loss_of_dword_sync": 1,
                        "phy_reset_problem": 0,
                    }
                },
            }
        }
        self.assertDictEqual(out, expected_out)

        # Validate empty dict
        mock_lsi_util_result = " "
        self.mock_host.update_cmd_map(cmd, mock_lsi_util_result)
        out = LsiUtils.get_phy_counters(self.mock_host)
        self.assertDictEqual(out[1], {})

    def test_get_parse_phy_errors(self):
        """unit test for get parse phy errors"""
        # Adapter with No Errors
        cmd = "lsiutil -a 12,0,0,0, 20 -p 1"
        mock_result = "Adapter Phy 0:  Link Up, No Errors"
        self.mock_host.update_cmd_map(cmd, mock_result)
        expected_out = {
            "adapter": {
                0: {
                    "invalid_word": 0,
                    "running_disparity": 0,
                    "loss_of_dword_sync": 0,
                    "phy_reset_problem": 0,
                }
            }
        }
        out = LsiUtils.parse_phy_errors(self.mock_host, 1)
        self.assertDictEqual(out, expected_out)

        # Expander with No Errors
        cmd = "lsiutil -a 12,0,0,0, 20 -p 1"
        mock_result = "Expander (Handle 0009) Phy 0:  Link Up, No Errors"
        self.mock_host.update_cmd_map(cmd, mock_result)
        expected_out = {
            "0009": {
                0: {
                    "invalid_word": 0,
                    "running_disparity": 0,
                    "loss_of_dword_sync": 0,
                    "phy_reset_problem": 0,
                }
            }
        }
        out = LsiUtils.parse_phy_errors(self.mock_host, 1)
        self.assertDictEqual(out, expected_out)

        # Adapter with Errors
        cmd = "lsiutil -a 12,0,0,0, 20 -p 1"
        mock_result = (
            "Adapter Phy 0:  Link Up\n"
            "Invalid DWord Count                                           4\n"
            "Running Disparity Error Count                                 0\n"
            "Loss of DWord Synch Count                                     1\n"
            "Phy Reset Problem Count                                       0\n"
        )
        self.mock_host.update_cmd_map(cmd, mock_result)
        expected_out = {
            "adapter": {
                0: {
                    "invalid_word": 4,
                    "running_disparity": 0,
                    "loss_of_dword_sync": 1,
                    "phy_reset_problem": 0,
                }
            }
        }
        out = LsiUtils.parse_phy_errors(self.mock_host, 1)
        self.assertDictEqual(out, expected_out)

        # Expander with Errors
        cmd = "lsiutil -a 12,0,0,0, 20 -p 1"
        mock_result = (
            "Expander (Handle 0009) Phy 1:  Link Up\n"
            "Invalid DWord Count                                           4\n"
            "Running Disparity Error Count                                 0\n"
            "Loss of DWord Synch Count                                     1\n"
            "Phy Reset Problem Count                                       0\n"
        )
        self.mock_host.update_cmd_map(cmd, mock_result)
        expected_out = {
            "0009": {
                1: {
                    "invalid_word": 4,
                    "running_disparity": 0,
                    "loss_of_dword_sync": 1,
                    "phy_reset_problem": 0,
                }
            }
        }
        out = LsiUtils.parse_phy_errors(self.mock_host, 1)
        self.assertDictEqual(out, expected_out)

        # Adapter and Expander with Errors
        cmd = "lsiutil -a 12,0,0,0, 20 -p 1"
        mock_result = (
            "Adapter Phy 0:  Link Up\n"
            "Invalid DWord Count                                           4\n"
            "Running Disparity Error Count                                 0\n"
            "Loss of DWord Synch Count                                     1\n"
            "Phy Reset Problem Count                                       0\n"
            "Expander (Handle 0009) Phy 1:  Link Up\n"
            "Invalid DWord Count                                           4\n"
            "Running Disparity Error Count                                 0\n"
            "Loss of DWord Synch Count                                     1\n"
            "Phy Reset Problem Count                                       0\n"
        )
        self.mock_host.update_cmd_map(cmd, mock_result)
        out = LsiUtils.parse_phy_errors(self.mock_host, 1)
        expected_out = {
            "adapter": {
                0: {
                    "invalid_word": 4,
                    "running_disparity": 0,
                    "loss_of_dword_sync": 1,
                    "phy_reset_problem": 0,
                }
            },
            "0009": {
                1: {
                    "invalid_word": 4,
                    "running_disparity": 0,
                    "loss_of_dword_sync": 1,
                    "phy_reset_problem": 0,
                }
            },
        }
        self.assertDictEqual(out, expected_out)

    def test_get_lsi_port_count(self):
        """unit test for get lsi port count"""
        out = LsiUtils.get_lsi_port_count(self.mock_host)
        # valid output
        self.assertEqual(out, 1)
        cmd = "lsiutil 0"
        mock_lsi_util_result = (
            r"LSI Logic MPT Configuration Utility, Version 1.71, Sep 18, 2013"
            r"1 MPT Ports found"
        )
        self.mock_host.update_cmd_map(cmd, mock_lsi_util_result)
        self.assertEqual(out, 1)
        # invalid case
        cmd = "lsiutil 0"
        mock_lsi_util_result = (
            r"LSI Logic MPT Configuration Utility, Version 1.71, Sep 18, 2013"
            r"MPT Port found"
        )
        self.mock_host.update_cmd_map(cmd, mock_lsi_util_result)
        self.assertRaises(TestError, LsiUtils.get_lsi_port_count, self.mock_host)

    def test_clear_phy_errors(self):
        LsiUtils.clear_phy_errors(self.mock_host, 1)

    def test_clear_all_ports_phy_errors(self):
        LsiUtils.clear_all_ports_phy_errors(self.mock_host)
