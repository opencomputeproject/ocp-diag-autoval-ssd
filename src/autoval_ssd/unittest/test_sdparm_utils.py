# pyre-unsafe
import unittest

from autoval.lib.utils.autoval_exceptions import TestError

from autoval_ssd.lib.utils.sdparm_utils import SdparmUtils
from autoval_ssd.unittest.mock.lib.mock_host import MockHost

cmd_map = [
    {"cmd": "sdparm --get WCE /dev/sda", "result": "WCE         1  [cha: y, def:  1]"},
    {"cmd": "ls  /sys/block/sda/device/scsi_disk", "result": "0:0:0:0"},
    {
        "cmd": "echo 'write back' > /sys/block/sda/device/scsi_disk/0:0:0:0/cache_type",
        "result": "True",
    },
    {
        "cmd": "sdparm --set WCE=1 --save /dev/sda",
        "result": "/dev/sda: ATA       SanDisk SD9SN8W2  1020",
    },
    {
        "cmd": "sdparm --set WCE=1 /dev/sda",
        "result": "/dev/sda: ATA       SanDisk SD9SN8W2  1020",
    },
    {
        "cmd": "echo 'write through' > /sys/block/sda/device/scsi_disk/0:0:0:0/cache_type",
        "result": "True",
    },
    {
        "cmd": "sdparm --set WCE=0 --save /dev/sda",
        "result": "/dev/sda: ATA       SanDisk SD9SN8W2  1020",
    },
    {
        "cmd": "sdparm --set WCE=0 --save /dev/sda",
        "result": "/dev/sda: ATA       SanDisk SD9SN8W2  1020",
    },
    {"cmd": "sdparm --get DRA /dev/sda", "result": "DRA         0  [cha: n, def:  0]"},
    {
        "cmd": "sdparm --set DRA=1 --save /dev/sda",
        "result": "/dev/sda: ATA       SanDisk SD9SN8W2  1020",
    },
    {
        "cmd": "sdparm --set DRA=1 /dev/sda",
        "result": "/dev/sda: ATA       SanDisk SD9SN8W2  1020",
    },
    {
        "cmd": "sdparm --set DRA=0 --save /dev/sda",
        "result": "/dev/sda: ATA       SanDisk SD9SN8W2  1020",
    },
    {
        "cmd": "sdparm --set DRA=0 /dev/sda",
        "result": "/dev/sda: ATA       SanDisk SD9SN8W2  1020",
    },
]


class SdparmUtilsUnitTest(unittest.TestCase):
    def setUp(self):
        self.mock_host = MockHost(cmd_map)
        self.sdparm_utils = SdparmUtils()

    def test_get_write_cache(self):
        """unit test for get_write_cache"""
        SdparmUtils.get_write_cache(self.mock_host, "sda")

        # Validate exception case
        cmd = "sdparm --get WCE /dev/sda"
        mock_result = "WCE           [cha: y, def:  1]"
        self.mock_host.update_cmd_map(cmd, mock_result)
        self.assertRaises(TestError, SdparmUtils.get_write_cache, self.mock_host, "sda")

    def test_enable_write_cache(self):
        """unit test for the enable_write_cache"""
        SdparmUtils.enable_write_cache(self.mock_host, "sda")
        SdparmUtils.enable_write_cache(self.mock_host, "sda", True)

    def test_disable_write_cache(self):
        """unit test for the disable_write_cache"""
        SdparmUtils.disable_write_cache(self.mock_host, "sda")
        SdparmUtils.enable_write_cache(self.mock_host, "sda", True)

    def test_get_read_lookahead(self):
        """unit test for the get_read_lookahead"""
        SdparmUtils.get_read_lookahead(self.mock_host, "sda")

        # Validate exception case
        cmd = "sdparm --get DRA /dev/sda"
        mock_result = "DRA           [cha: n, def:  0]"
        self.mock_host.update_cmd_map(cmd, mock_result)
        self.assertRaises(
            TestError, SdparmUtils.get_read_lookahead, self.mock_host, "sda"
        )

    def test_enable_read_lookahead(self):
        """unit test for the enable_read_lookahead"""
        SdparmUtils.enable_read_lookahead(self.mock_host, "sda")
        SdparmUtils.enable_read_lookahead(self.mock_host, "sda", True)

    def test_disable_read_lookahead(self):
        """unit test for the disable_read_lookahead"""
        SdparmUtils.disable_read_lookahead(self.mock_host, "sda")
        SdparmUtils.enable_read_lookahead(self.mock_host, "sda", True)
