# pyre-unsafe
import unittest
from unittest.mock import Mock, patch

from autoval_ssd.lib.utils.scrtnycli_utils import ScrtnyCli

from autoval_ssd.unittest.mock.lib.mock_host import MockHost

CMD_MAP = []


class ScrtnyCliTest(unittest.TestCase):
    CMD_MAP = [
        {
            "eHBA|FeatureIT": "eHBA\nFeatureIT\nExpander\nExpander\nExpander\nExpander\nExpander\nExpander",
            "Expander": "Expander\nExpander\nExpander\nExpander\nExpander\nExpander",
        }
    ]

    def setUp(self):
        self.mock_host = MockHost(cmd_map=CMD_MAP)

    @patch.object(MockHost, "run")
    def test_scan_drive_scrtnycli(self, mock):
        ScrtnyCli.scan_drive_scrtnycli(self.mock_host, "/mock/path/scrtnycli.x86_64")
        mock.assert_called_once_with(
            cmd="/mock/path/scrtnycli.x86_64 -i 1 scan | grep Disk"
        )

    @patch.object(MockHost, "run")
    def test_update_firmware_scrtnycli(self, mock):
        ScrtnyCli.update_firmware_scrtnycli(
            self.mock_host, "/bin/CB08.ftd", "a", "/mock/path/scrtnycli.x86_64", "1"
        )
        mock.assert_called_once_with(
            cmd="/mock/path/scrtnycli.x86_64 -i 1 dl -pdfw /bin/CB08.ftd -dh 0xa -m 7"
        )

    @patch.object(ScrtnyCli, "list_devices")
    def test_list_devices(self, mock_list_devices):
        mock_host = Mock()
        mock_output = self.CMD_MAP[0]["eHBA|FeatureIT"]
        mock_list_devices.return_value = mock_output
        result = ScrtnyCli.list_devices(mock_host)
        self.assertIn(mock_output, result)

    @patch.object(ScrtnyCli, "list_devices")
    def test_count_hbas(self, mock_list_devices):
        mock_host = Mock()
        mock_output = self.CMD_MAP[0]["eHBA|FeatureIT"]
        mock_list_devices.return_value = mock_output
        result = ScrtnyCli.count_hbas(mock_host)
        self.assertEqual(result, 2)

    @patch.object(ScrtnyCli, "list_devices")
    def test_count_expanders(self, mock_list_devices):
        mock_host = Mock()
        mock_output = self.CMD_MAP[0]["Expander"]
        mock_list_devices.return_value = mock_output
        result = ScrtnyCli.count_expanders(mock_host)
        self.assertEqual(result, 6)

    @patch("time.sleep")
    @patch.object(MockHost, "run")
    def test_expander_soft_reset(self, m_run, m_sleep) -> None:
        """Unittest for expander soft reset."""
        m_sleep.return_value = True
        ScrtnyCli.expander_soft_reset(self.mock_host)  # type: ignore
        m_run.assert_called_once_with(
            "scrtnycli -i 2 reset -e",
        )

    @patch("time.sleep")
    @patch.object(MockHost, "run")
    def test_phy_link_reset(self, m_run, m_sleep) -> None:
        """Unittest for drive PHY link reset of a drive."""
        m_sleep.return_value = True
        phy_addr = 2
        ScrtnyCli.phy_link_reset(self.mock_host, phy_addr)  # type: ignore
        m_run.assert_called_once_with("scrtnycli -i 2 reset -pl 2", True)

    @patch("time.sleep")
    @patch.object(MockHost, "run")
    def test_phy_link_reset_all(self, m_run, m_sleep) -> None:
        """Unittest for PHY link reset of all drive."""
        m_sleep.return_value = True
        ScrtnyCli.phy_link_reset_all(self.mock_host)  # type: ignore
        m_run.assert_called_once_with("scrtnycli -i 2 reset -pla", True)

    @patch("time.sleep")
    @patch.object(MockHost, "run")
    def test_phy_hard_reset(self, m_run, m_sleep) -> None:
        """Unittest for PHY hard reset of a drive."""
        m_sleep.return_value = True
        phy_addr = 2
        ScrtnyCli.phy_hard_reset(self.mock_host, phy_addr)  # type: ignore
        m_run.assert_called_once_with("scrtnycli -i 2 reset -ph 2", True)

    @patch("time.sleep")
    @patch.object(MockHost, "run")
    def test_phy_hard_reset_all(self, m_run, m_sleep) -> None:
        """Unittest for PHY hard reset of all drives."""
        m_sleep.return_value = True
        ScrtnyCli.phy_hard_reset_all(self.mock_host)  # type: ignore
        m_run.assert_called_once_with("scrtnycli -i 2 reset -pha", True)

    @patch("time.sleep")
    @patch.object(MockHost, "run")
    def test_turn_phy_on(self, m_run, m_sleep) -> None:
        """Unittest for turning the PHY ON."""
        m_sleep.return_value = True
        mock_phy_value = 4
        ScrtnyCli.turn_phy_on(self.mock_host, mock_phy_value)  # type: ignore
        m_run.assert_called_once_with("scrtnycli -i 2 phy -on 4", True)

    @patch("time.sleep")
    @patch.object(MockHost, "run")
    def test_turn_phy_off(self, m_run, m_sleep) -> None:
        """Unittest for turning the PHY OFF."""
        m_sleep.return_value = True
        mock_phy_value = 4
        ScrtnyCli.turn_phy_off(self.mock_host, mock_phy_value)  # type: ignore
        m_run.assert_called_once_with("scrtnycli -i 2 phy -off 4", True)
