# pyre-unsafe
import unittest
from unittest.mock import patch

from autoval.lib.connection.connection_utils import CmdResult
from autoval.lib.utils.autoval_exceptions import TestError, TestStepError
from autoval_ssd.lib.utils.sg_utils import SgUtils
from autoval_ssd.unittest.mock.lib.mock_host import MockHost

CMD_MAP = [
    {"cmd": "sg_readcap /dev/sg0", "file": "sg_utils/sg_readcap"},
    {"cmd": "sg_inq /dev/sg0", "file": "sg_utils/sg_inq"},
    {"cmd": "sdparm --command=capacity /dev/sg0", "file": "sg_utils/sdparm_capacity"},
    {"cmd": "sdparm --command=ready /dev/sg0", "result": "Ready"},
    {
        "cmd": "sg_test_rwbuf --size=4096 --times=5 --verbose /dev/sg0",
        "result": "Success",
    },
    {
        "cmd": "sg_verify -c 0x10000 -l 0 -v /dev/sg0",
        "result": "Verified without error",
    },
    {"cmd": "sg_verify -c 0x10000 -l 0 -v /dev/sg1", "result": "without error"},
    {"cmd": "sg_verify -c 0x10000 -l 0 -v /dev/sg2", "result": "Verified"},
    {"cmd": "sg_turs -p -v /dev/sg0", "result": "test unit ready"},
    {"cmd": "sg_requests /dev/sg0 --hex", "result": "00 70 0a"},
    {"cmd": "sg_requests /dev/sg1 --hex", "result": "abc"},
    {"cmd": "sg_write_long --wr_uncor /dev/sg0", "result": ""},
    {"cmd": "sg_read bs=4096 count=1 if=/dev/sg0", "result": 1},
    {"cmd": "sg_write_same -i /dev/zero -n 1 -x 4096 /dev/sg0", "result": ""},
    {"cmd": "sg_map -i -x", "result": "Generic_vendor_name"},
    {"cmd": "sg_logs sg0 --page=2", "result": "02 logs"},
]


class SgUtilsUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.host = MockHost(cmd_map=CMD_MAP)
        self.sgUtils = SgUtils()

    def test_get_hdd_lb_length(self):
        """Unittest for Get hdd lb length"""
        self.assertEqual(self.sgUtils.get_hdd_lb_length(self.host, "sg0"), 512)
        with self.assertRaises(TestError) as exp:
            self.sgUtils.get_hdd_lb_length(self.host, "sg1")
        self.assertRegex(str(exp.exception), r"Failed to get LB length.*")

    @patch.object(MockHost, "run")
    def test_start_device(self, mock_run):
        """Unittest for Start device"""
        cmd = "sg_start --start /dev/sg0"
        self.sgUtils.start_device(self.host, "sg0")
        mock_run.assert_called_once_with(cmd)

    @patch.object(MockHost, "run")
    def test_stop_device(self, mock_run):
        """Unittest for Stop device"""
        cmd = "sg_start --stop /dev/sg0"
        self.sgUtils.stop_device(self.host, "sg0")
        mock_run.assert_called_once_with(cmd)

    def test_get_hdd_last_lba(self):
        """Unittest for Get hdd last lba"""
        self.assertEqual(self.sgUtils.get_hdd_last_lba(self.host, "sg0"), 487325695)
        with self.assertRaises(TestError) as exp:
            self.sgUtils.get_hdd_last_lba(self.host, "sg1")
        self.assertRegex(str(exp.exception), r"Failed to get last LBA.*")

    def test_get_hdd_capacity(self):
        """Unittest for Get hdd capacity"""
        self.assertEqual(self.sgUtils.get_hdd_capacity(self.host, "sg0"), 249510756352)
        with self.assertRaises(TestError) as exp:
            self.sgUtils.get_hdd_capacity(self.host, "sg1")
        self.assertRegex(str(exp.exception), r"Failed to get drive.*")

    @patch.object(MockHost, "run")
    def test_validate_sg_readcap(self, mock_run):
        """Unittest for Validate SG readcap"""
        cmd = "sg_readcap sg0"
        self.sgUtils.validate_sg_readcap(self.host, "sg0")
        mock_run.assert_called_once_with(cmd)

    def test_validate_sg_readcap_output(self):
        """Unittest for Validate SG readcap output"""
        self.assertIsNone(
            self.sgUtils.validate_sg_readcap_output(self.host, "/dev/sg0")
        )

    @patch.object(MockHost, "run")
    def test_validate_sg_inq(self, mock_run):
        """Unittest for Validate SG inq"""
        cmd = "sg_inq sg0"
        self.sgUtils.validate_sg_inq(self.host, "sg0")
        mock_run.assert_called_once_with(cmd)

    def test_validate_sg_inq_output(self):
        """Unittest for Validate SG inq output"""
        self.assertIsNone(self.sgUtils.validate_sg_inq_output(self.host, "/dev/sg0"))
        with self.assertRaises(TestStepError) as exp:
            self.sgUtils.validate_sg_inq_output(self.host, "/dev/sg1")
        self.assertRegex(str(exp.exception), r"[AUTOVAL TEST STEP ERROR].*")

    @patch.object(MockHost, "run")
    def test_validate_sg_luns(self, mock_run):
        """Unittest for Validate SG luns"""
        cmd = "sg_luns sg0"
        self.sgUtils.validate_sg_luns(self.host, "sg0")
        mock_run.assert_called_once_with(cmd)

    @patch.object(MockHost, "run")
    def test_validate_sdparm_command_capacity(self, mock_run):
        """Unittest for Validate sdparm command capacity"""
        cmd = "sdparm --command=capacity sg0"
        self.sgUtils.validate_sdparm_command_capacity(self.host, "sg0")
        mock_run.assert_called_once_with(cmd)

    def test_validate_sdparm_command_capacity_output(self):
        """Unittest for Validate sdparm command capacity output"""
        self.assertIsNone(
            self.sgUtils.validate_sdparm_command_capacity_output(self.host, "/dev/sg0")
        )
        with self.assertRaises(TestStepError) as exp:
            self.sgUtils.validate_sdparm_command_capacity_output(self.host, "/dev/sg1")
        self.assertRegex(str(exp.exception), r"[AUTOVAL TEST STEP ERROR].*")

    @patch.object(MockHost, "run")
    def test_validate_sdparm_command_ready(self, mock_run):
        """Unittest for Validate sdparm command ready"""
        cmd = "sdparm --command=ready sg0"
        self.sgUtils.validate_sdparm_command_ready(self.host, "sg0")
        mock_run.assert_called_once_with(cmd)

    def test_validate_sdparm_command_ready_output(self):
        """Unittest for Validate sdparm command ready output"""
        self.assertIsNone(
            self.sgUtils.validate_sdparm_command_ready_output(self.host, "/dev/sg0")
        )
        with self.assertRaises(TestStepError) as exp:
            self.sgUtils.validate_sdparm_command_ready_output(self.host, "/dev/sg1")
        self.assertRegex(str(exp.exception), r"[AUTOVAL TEST STEP ERROR].*")

    @patch.object(MockHost, "run")
    def test_validate_sdparm_command_sense(self, mock_run):
        """Unittest for Validate sdparm command sense"""
        cmd = "sdparm --command=sense sg0"
        self.sgUtils.validate_sdparm_command_sense(self.host, "sg0")
        mock_run.assert_called_once_with(cmd)

    @patch.object(MockHost, "run")
    def test_validate_sdparm_all(self, mock_run):
        """Unittest for Validate sdparm all"""
        cmd = "sdparm --all sg0"
        self.sgUtils.validate_sdparm_all(self.host, "sg0")
        mock_run.assert_called_once_with(cmd)

    @patch.object(MockHost, "run")
    def test_validate_sdparm_inquiry(self, mock_run):
        """Unittest for Validate sdparm inquiry"""
        cmd = "sdparm --inquiry sg0"
        self.sgUtils.validate_sdparm_inquiry(self.host, "sg0")
        mock_run.assert_called_once_with(cmd)

    @patch.object(MockHost, "run")
    @patch.object(SgUtils, "get_scsi_device_buffer_size")
    def test_validate_sg_test_rwbuf(self, mock_object, mock_run):
        """Unittest for Validate SG test rwbuf"""
        cmd = "sg_test_rwbuf --size=4096 --times=5 --verbose sg0"
        mock_object.return_value = 4096
        self.sgUtils.validate_sg_test_rwbuf(self.host, "sg0")
        mock_run.assert_called_once_with(cmd)

    @patch.object(SgUtils, "get_scsi_device_buffer_size")
    def test_validate_sg_test_rwbuf_output(self, mock_object):
        """Unittest for Validate SG test rwbuf output"""
        mock_object.return_value = 4096
        self.assertIsNone(
            self.sgUtils.validate_sg_test_rwbuf_output(self.host, "/dev/sg0")
        )
        with self.assertRaises(TestStepError) as exp:
            self.sgUtils.validate_sg_test_rwbuf_output(self.host, "/dev/sg1")
        self.assertRegex(str(exp.exception), r"[AUTOVAL TEST STEP ERROR].*")

    @patch.object(MockHost, "run")
    def test_validate_sg_verify(self, mock_run):
        """Unittest for Validate SG verify"""
        cmd = "sg_verify -c 0x10000 -l 0 -v sg0"
        self.sgUtils.validate_sg_verify(self.host, "sg0")
        mock_run.assert_called_once_with(cmd)

    def test_validate_sg_verify_output(self):
        """Unittest for Validate SG verify output"""
        self.assertIsNone(self.sgUtils.validate_sg_verify_output(self.host, "/dev/sg0"))
        with self.assertRaises(TestStepError) as exp:
            self.sgUtils.validate_sg_verify_output(self.host, "/dev/sg1")
        self.assertRegex(str(exp.exception), r"[AUTOVAL TEST STEP ERROR].*")
        with self.assertRaises(TestStepError) as exp:
            self.sgUtils.validate_sg_verify_output(self.host, "/dev/sg2")
        self.assertRegex(str(exp.exception), r"[AUTOVAL TEST STEP ERROR].*")

    @patch.object(MockHost, "run")
    def test_validate_sg_turs(self, mock_run):
        """Unittest for Validate SG turs"""
        cmd = "sg_turs -p -v sg0"
        self.sgUtils.validate_sg_turs(self.host, "sg0")
        mock_run.assert_called_once_with(cmd)

    def test_validate_sg_turs_output(self):
        """Unittest for Validate SG turs output"""
        self.assertIsNone(self.sgUtils.validate_sg_turs_output(self.host, "/dev/sg0"))
        with self.assertRaises(TestStepError) as exp:
            self.sgUtils.validate_sg_turs_output(self.host, "/dev/sg1")
        self.assertRegex(str(exp.exception), r"[AUTOVAL TEST STEP ERROR].*")

    @patch.object(MockHost, "run_get_result")
    def test_test_scsi_command(self, mock_run):
        """Unittest for Test SCSI command"""

        def mock_object(stdout: str, return_code: int) -> CmdResult:
            return CmdResult(
                command="",
                stdout=stdout,
                stderr="",
                return_code=return_code,
                duration=1.0,
            )

        mock_run.side_effect = [
            mock_object(stdout="Not ready to ready change", return_code=0),
            mock_object(stdout="Ready to not ready change", return_code=1),
            mock_object(stdout="None", return_code=1),
        ]
        self.assertEqual(self.sgUtils.test_scsi_command(self.host, "sg0"), True)
        self.assertEqual(self.sgUtils.test_scsi_command(self.host, "sg0"), False)
        self.assertEqual(self.sgUtils.test_scsi_command(self.host, "sg0"), None)

    @patch.object(SgUtils, "test_scsi_command")
    def test_sg_requests(self, mock_object):
        """Unittest for Sg requests"""
        mock_object.side_effect = [True, False, True]
        self.assertListEqual(
            self.sgUtils.sg_requests(self.host, "/dev/sg0"), ["70", "0a"]
        )
        self.assertListEqual(self.sgUtils.sg_requests(self.host, "/dev/sg1"), [])
        self.assertListEqual(self.sgUtils.sg_requests(self.host, "/dev/sg1"), [])

    def test_get_scsi_inquiry(self):
        """Unittest for Get SCSI inquiry"""
        self.assertDictEqual(
            self.sgUtils.get_scsi_inquiry(self.host, "/dev/sg0"),
            {
                "Product identification": "GenericModel GNE2404",
                "Product revision level": "1020",
                "Unit serial number": "19208A800929",
                "Vendor identification": "ATA",
            },
        )
        self.assertDictEqual(self.sgUtils.get_scsi_inquiry(self.host, "/dev/sg1"), {})

    @patch.object(MockHost, "run")
    def test_get_scsi_device_buffer_size(self, mock_object):
        """Unittest for Get SCSI device buffer size"""
        mock_object.side_effect = [
            "buffer of 512 bytes",
            "buffer of 8192 bytes",
            "No Buffer",
        ]
        self.assertEqual(
            self.sgUtils.get_scsi_device_buffer_size(self.host, "/dev/sg0"), 512
        )
        self.assertEqual(
            self.sgUtils.get_scsi_device_buffer_size(self.host, "/dev/sg0"), 4096
        )
        with self.assertRaises(TestError) as exp:
            self.sgUtils.get_scsi_device_buffer_size(self.host, "/dev/sg0")
        self.assertRegex(
            str(exp.exception), r"Fail to get buffer size of SCSI device.*"
        )

    def test_get_all_sg_map_devices(self):
        """Unittest for Get all SG map device"""
        self.assertEqual(
            self.sgUtils.get_all_sg_map_devices(self.host), "Generic_vendor_name"
        )

    def test_get_sg_log_pages(self):
        """Unittest for Get SG log pages"""
        self.assertDictEqual(
            self.sgUtils.get_sg_log_pages(self.host, "sg0", 0x02),
            {"sense_data": "logs"},
        )

    def test_parse_sg_logs(self):
        """Unittest for Parse SG logs"""
        self.assertDictEqual(
            self.sgUtils._parse_sg_logs(r"(\w*.*):(\w*.*)", ["sg_logs:sg0"]),
            {"sg_logs": "sg0"},
        )

    def test_drive_error_injection(self):
        """Unittest for Drive error injection"""
        with self.assertRaises(TestStepError) as exp:
            self.sgUtils.drive_error_injection(self.host, "sg0")
        self.assertRegex(str(exp.exception), r"[AUTOVAL TEST STEP ERROR].*")
