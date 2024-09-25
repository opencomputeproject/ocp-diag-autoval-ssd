# pyre-unsafe
from unittest import TestCase
from unittest.mock import call, Mock, patch

from autoval.lib.connection.connection_utils import CmdResult
from autoval_ssd.lib.utils.filesystem_utils import FilesystemUtils
from autoval_ssd.unittest.mock.lib.mock_host import MOCK_HOSTS, MockHost


CMD_MAP = [
    {"cmd": "mkfs.xfs -f  /dev/sda", "file": "mkfs_xfs"},
    {"cmd": "mkfs. -F  /dev/sda", "file": "mkfs"},
    {"cmd": "mkfs.ext4 -F  /dev/sda", "file": "mkfs"},
    {"cmd": "fstrim -v /mnt/autoval_nvme0n1", "file": "fstrim"},
    {"cmd": "dd if=/dev/zero of=/dev/sda bs=1M count=2", "file": "dd"},
]


class FileSystemUtilsUnitTest(TestCase):
    def setUp(self):
        self.mock_host = MockHost(cmd_map=CMD_MAP)
        self.log = ""

    def test_create_xfs_filesystem(self):
        """
        This method mock the command in the create_filesystem method
        for the filesystem type "xfs".
        """
        self.assertRegex(
            FilesystemUtils.create_filesystem(self.mock_host, "sda", "xfs", ""),
            "meta-data=/dev/sda",
        )
        try:
            FilesystemUtils.create_filesystem(self.mock_host, "", "xfs", "")
        except Exception as e:
            self.assertEqual(
                str(e),
                "Failed to create filesystem on /dev/sda. Please check the filesystem type.",
            )

    def test_create_filesystem(self):
        """
        This method mock the command in the create_filesystem method
        if the filesystem type is other than "xfs". Default filesystem
        type is "ext4".
        """
        self.assertRegex(
            FilesystemUtils.create_filesystem(self.mock_host, "sda", "ext4", ""),
            "mke2fs 1.42.9",
        )
        self.assertRegex(
            FilesystemUtils.create_filesystem(self.mock_host, "sda", "", ""),
            "mke2fs 1.42.9",
        )
        try:
            FilesystemUtils.create_filesystem(self.mock_host, "", "ext4", "")
        except Exception as e:
            self.assertEqual(
                str(e),
                "Failed to create filesystem on /dev/sda. Please check the filesystem type.",
            )

    def test_fstrim(self):
        self.assertRegex(
            FilesystemUtils.fstrim(self.mock_host, "/mnt/autoval_nvme0n1"), "trimmed"
        )
        try:
            FilesystemUtils.fstrim(self.mock_host, "/mnt/autoval_nvme0n1")
        except Exception as e:
            self.assertEqual(
                str(e),
                "Failed to fstrim /mnt/autoval_nvme0n1. Please check the mount point.",
            )

    def mock_cmd_log(self, *args, **kwargs):
        """This method acts as an mock alternative to
        log the cmd execution."""
        self.log += args[0]

    def test_unmount(self):
        """Unittest for un-mount."""
        FilesystemUtils.unmount(self.mock_host, "mock_path")

    @patch.object(FilesystemUtils, "create_filesystem", autospec=True)
    @patch.object(FilesystemUtils, "unmount", autospec=True)
    @patch.object(MockHost, "run")
    @patch("autoval_ssd.lib.utils.filesystem_utils.Host", autospec=True)
    def test_mount(self, mock_host, mock_run, mock_unmount, mock_create_fs):
        """Unittest for mount."""
        mock_device = "mock_device"
        mock_mnt_point = "/mock/point"
        FilesystemUtils.mount(
            self.mock_host, mock_device, mock_mnt_point, force_mount=False
        )
        # If mounted, force_mount: True, if mount point is
        # already present, mnt_options: True.
        self.log = ""
        mock_unmount.return_value = "pass"
        mock_create_fs.return_value = "pass"
        mock_host.return_value = self.mock_host
        mock_run.side_effect = [
            "mounted",
            Exception("mkdir -p failed"),
            "rm -r passed",
            "mount command passed",
        ]
        FilesystemUtils.mount(MOCK_HOSTS, mock_device, mock_mnt_point, mnt_options="-a")
        # asserting if the un-mount is called once if the force_mount is True.
        mock_unmount.assert_called_once_with(self.mock_host, mock_mnt_point)
        # asserting if the create_filesystem is called once if the
        # Filesystem is passed as input.
        mock_create_fs.assert_called_once_with(self.mock_host, mock_device, "ext4", "")

    def test_get_df_info(self):
        """Unittest for get_df_info."""
        # valid case
        mock_device = "mock"
        cmd = f"df -B 1 -T /dev/{mock_device}*"
        mock_output_valid = (
            "Filesystem     Type    1B-blocks  Used    Available Use% Mounted on\n"
            "devtmpfs       xfs 134948618240     0 134948618240   0% /dev\n"
        )
        expected_output = {
            "type": "xfs",
            "1b_blocks": 134948618240,
            "used": 0,
            "available": 134948618240,
            "use_pct": "0%",
            "mounted_on": "/dev",
        }
        self.mock_host.update_cmd_map(cmd, mock_output_valid)
        out = FilesystemUtils.get_df_info(self.mock_host, mock_device)
        self.assertDictEqual(out, expected_output)
        # Test search
        out = FilesystemUtils.get_df_info(self.mock_host, mock_device, "xfs")
        self.assertDictEqual(out, expected_output)
        # Invalid case
        mock_output_invalid = ""
        self.mock_host.update_cmd_map(cmd, mock_output_invalid)
        out = FilesystemUtils.get_df_info(self.mock_host, mock_device)
        self.assertDictEqual(out, {})

    @patch.object(FilesystemUtils, "is_mounted", autospec=True)
    @patch.object(FilesystemUtils, "unmount", autospec=True)
    def test_clean_filesystem_with_mount(self, mock_unmount, mock_mount):
        """Unittest for clean_filesystem with mount."""
        # case if the mount point is mounted
        mock_mount.return_value = True
        mock_unmount.return_value = "unmounted"
        mock_device = "mock/device"
        mock_point = "mock/point"
        FilesystemUtils.clean_filesystem(
            self.mock_host, mock_device, mnt_point=mock_point
        )
        mock_mount.assert_called_once_with(self.mock_host, mock_point)
        mock_unmount.assert_called_once_with(self.mock_host, mock_point)

    @patch.object(FilesystemUtils, "is_mounted", autospec=True)
    @patch.object(FilesystemUtils, "unmount", autospec=True)
    def test_clean_filesystem_with_no_mount(self, mock_unmount, mock_mount):
        """Unittest for clean_filesystem with mount."""
        # case if the mount point is not mounted
        mock_mount.return_value = False
        mock_device = "mock/device"
        mock_point = "mock/point"
        FilesystemUtils.clean_filesystem(
            self.mock_host, mock_device, mnt_point=mock_point
        )
        mock_mount.assert_called_once_with(self.mock_host, mock_point)
        # asserting unmount is not called if no mount is available
        self.assertFalse(mock_unmount.called)

    def test_is_mounted(self):
        """Unittest for is_mounted."""
        cmd = "mountpoint"
        valid_value = CmdResult(cmd, "", "", 0, 1)
        invalid_value = CmdResult(cmd, "", "", 1, 1)
        self.mock_host.run = Mock(side_effect=[valid_value, invalid_value])
        self.assertTrue(FilesystemUtils.is_mounted(self.mock_host, "mock/path"))

    @patch.object(FilesystemUtils, "mount")
    def test_mount_all(self, mock_mount):
        """Unittest for mount all."""
        mock_drive_list = ["mock_drive1", "mock_drive2", "mock_drive3"]
        mnt = "mock/mount_%s"
        calls = []
        for drive in mock_drive_list:
            calls.append(call(self.mock_host, drive, mnt % drive, "", "", "", False))
        mock_mount.return_value = "mounted"
        FilesystemUtils.mount_all(self.mock_host, mock_drive_list, mnt)
        mock_mount.assert_has_calls(calls=calls)

    @patch.object(FilesystemUtils, "clean_filesystem", autospec=True)
    def test_unmount_all(self, mock_unmount):
        """Unittest for unmount all."""
        mock_drive_list = ["mock_drive1", "mock_drive2", "mock_drive3"]
        mnt = "mock/mount_%s"
        calls = []
        for drive in mock_drive_list:
            calls.append(call(self.mock_host, drive, mnt % drive))
        print(calls)
        mock_unmount.return_value = "un_mounted"
        FilesystemUtils.unmount_all(self.mock_host, mock_drive_list, mnt)
        mock_unmount.assert_has_calls(calls=calls)

    def test_create_zero_file(self):
        """Unit test for create zero file."""
        # blocksize = None , count = None
        file_path = "mock/file"
        cmd = f"dd if=/dev/zero of={file_path}"
        mock_output = "file created with default block size and count"
        self.mock_host.update_cmd_map(cmd, mock_output)
        out = FilesystemUtils.create_zero_file(self.mock_host, file_path)
        self.assertEqual(out, mock_output)
        _bs = "205"
        _count = "36"
        cmd = f"dd if=/dev/zero of={file_path} bs={_bs} count={_count}"
        mock_output = "file created with given input block size and count"
        self.mock_host.update_cmd_map(cmd, mock_output)
        # with blocksize and count
        out = FilesystemUtils.create_zero_file(
            self.mock_host, file_path, blocksize=_bs, count=_count
        )
        self.assertEqual(out, mock_output)
