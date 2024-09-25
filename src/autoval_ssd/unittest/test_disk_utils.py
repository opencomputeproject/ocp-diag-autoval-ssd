# pyre-unsafe
import copy
from unittest import mock, TestCase
from unittest.mock import patch

from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_utils import AutovalLog

from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.filesystem_utils import FilesystemUtils
from autoval_ssd.unittest.mock.lib.mock_host import MockHost

CMD_MAP = [
    {"cmd": "lsblk -J", "file": "lsblk_J"},
    {"cmd": "sg_readcap /dev/sda", "file": "sg_utils/sg_readcap"},
    {"cmd": "cat /proc/meminfo", "file": "meminfo"},
    {"cmd": "lsblk -i /dev/sda", "file": "lsblk"},
    {"cmd": "umount -fl", "file": "empty"},
    {"cmd": "yes | parted -a optimal /dev/nvme1n1 rm 1", "file": "empty"},
    {"cmd": "md5sum /mnt/", "file": "valuemd5"},
    {"cmd": "parted -s /dev/nvme1n1 unit b mkpart primary 128", "file": "empty"},
    {"cmd": "partprobe", "file": "empty"},
    {"cmd": "umount /dev/nvme1n1p1", "file": "empty"},
    {"cmd": "rmdir", "file": "umount"},
    {
        "cmd": "parted -a optimal /dev/nvme1n1 mktable gpt --script mkpart P1 0% 5%",
        "file": "empty",
    },
    {"cmd": "umount -f1 /mnt/autoval_mnt", "file": "empty"},
    {"cmd": "mountpoint /mnt/autoval_mnt", "file": "empty"},
    {"cmd": "rmdir /mnt/autoval_mnt", "file": "empty"},
    {
        "cmd": "lsblk -i /dev/nvme0n1",
        "result": """NAME    MAJ:MIN RM  SIZE RO TYPE MOUNTPOINT
        nvme0n1 259:0    0  353G  0 disk /mnt/fio_test_nvme0n1""",
    },
    {
        "cmd": "lsblk -i /dev/nvme1n1",
        "result": """NAME    MAJ:MIN RM  SIZE RO TYPE MOUNTPOINT
        nvme1n1 259:0    0  353G  0 disk """,
    },
]


class DiskUtilUnitTest(TestCase):
    def setUp(self):
        self.mock_host = MockHost(copy.deepcopy(CMD_MAP))
        self.diskutils = DiskUtils()
        self.log = ""
        self.drive = "sda"
        self.drive_type = None
        self.power_on_all_slots = False

    def test_get_storage_devices(self):
        # Test with no drive type specified
        devices = DiskUtils.get_storage_devices(
            self.mock_host, self.drive_type, self.power_on_all_slots
        )
        self.assertIsInstance(devices, list)
        # Test with SSD drive type specified
        self.drive_type = "ssd"
        devices = DiskUtils.get_storage_devices(
            self.mock_host, self.drive_type, self.power_on_all_slots
        )
        self.assertIsInstance(devices, list)
        # Test with HDD drive type specified
        self.drive_type = "hdd"
        devices = DiskUtils.get_storage_devices(
            self.mock_host, self.drive_type, self.power_on_all_slots
        )
        self.assertIsInstance(devices, list)
        # Test with power on all slots set to True
        self.power_on_all_slots = True
        devices = DiskUtils.get_storage_devices(
            self.mock_host, self.drive_type, self.power_on_all_slots
        )
        self.assertIsInstance(devices, list)

    def test_get_block_devices(self):
        mock_cmd = "lsblk -o name,type"
        mock_output_valid = "lsblk"
        expected_drives = [
            "sda",
            "sdb",
            "sdc",
            "sdd",
            "sde",
            "sdf",
            "sdg",
            "sdh",
            "sdi",
            "sdj",
            "sdk",
            "sdl",
            "sdm",
            "sdn",
            "sdo",
            "sdp",
            "sdq",
            "sdr",
            "sds",
            "sdt",
            "sdu",
            "sdv",
            "sdw",
            "sdx",
            "sdy",
            "sdz",
            "sdaa",
            "sdab",
            "sdac",
            "sdad",
            "sdae",
            "sdaf",
            "sdag",
            "sdah",
            "sdai",
            "sdaj",
            "sdak",
            "nvme1n1",
            "nvme0n1",
        ]
        exclude_boot_drive = False
        self.mock_host.update_cmd_map(mock_cmd, mock_output_valid, is_file=True)
        drives = DiskUtils.get_block_devices(self.mock_host, exclude_boot_drive)
        self.assertEqual(expected_drives, drives)
        mock_output_invalid = ""
        self.mock_host.update_cmd_map(mock_cmd, mock_output_invalid)
        with self.assertRaises(TestError) as exp:
            DiskUtils.get_block_devices(self.mock_host)
        self.assertEqual(
            str(exp.exception),
            "[AUTOVAL TEST ERROR] Not able to match block devices from lsblk output",
        )

    def test_get_block_devices_info(self):
        """unit test for get_block_devices_info."""
        expected_out = [
            {
                "name": "loop0",
                "maj:min": "7:0",
                "rm": "0",
                "size": "100G",
                "ro": "0",
                "type": "loop",
                "mountpoint": "/var/oss/autoval/agent/control",
            },
            {
                "name": "sda",
                "maj:min": "8:0",
                "rm": "0",
                "size": "1.8T",
                "ro": "0",
                "type": "disk",
                "mountpoint": None,
                "children": [
                    {
                        "name": "sda1",
                        "maj:min": "8:1",
                        "rm": "0",
                        "size": "243M",
                        "ro": "0",
                        "type": "part",
                        "mountpoint": "/boot/efi",
                    },
                    {
                        "name": "sda2",
                        "maj:min": "8:2",
                        "rm": "0",
                        "size": "488M",
                        "ro": "0",
                        "type": "part",
                        "mountpoint": "/boot",
                    },
                    {
                        "name": "sda3",
                        "maj:min": "8:3",
                        "rm": "0",
                        "size": "1.9G",
                        "ro": "0",
                        "type": "part",
                        "mountpoint": "[SWAP]",
                    },
                    {
                        "name": "sda4",
                        "maj:min": "8:4",
                        "rm": "0",
                        "size": "1.8T",
                        "ro": "0",
                        "type": "part",
                        "mountpoint": "/",
                    },
                ],
            },
            {
                "name": "nvme0n1",
                "maj:min": "259:0",
                "rm": "0",
                "size": "1.7T",
                "ro": "0",
                "type": "disk",
                "mountpoint": None,
            },
        ]
        block_device = DiskUtils.get_block_devices_info(self.mock_host)
        self.assertEqual(expected_out, block_device)

    def test_get_drive_location(self):
        """Unittest for get_drive_location."""
        mock_drive = "nvme0n1"
        mock_cmd = f"ls -la /sys/block/{mock_drive}"
        mock_output = (
            "lrwxrwxrwx 1 root root 0 Oct 21 08:29 /sys/block/nvme0n1 -> "
            "../devices/pci0000:00/0000:00:1c.0/0000:01:00.0/nvme/nvme0/nvme0n1"
        )
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        # Invalid case
        out = DiskUtils.get_drive_location(self.mock_host, mock_drive)
        self.assertEqual(out, "0000:01:00.0")
        mock_output_invalid = (
            "lrwxrwxrwx 1 root root 0 Oct 21 08:29 /sys/block/nvme0n1 -> ../devices"
        )
        self.mock_host.update_cmd_map(mock_cmd, mock_output_invalid)
        with self.assertRaises(TestError) as exp:
            DiskUtils.get_drive_location(self.mock_host, mock_drive)
        self.assertEqual(
            str(exp.exception),
            f"[AUTOVAL TEST ERROR] Unable to get the physical "
            f"location for {mock_drive}",
        )

    def test_get_block_from_physical_location(self):
        """Unittest for get_block_from_physical_location."""
        mock_drives = [
            {
                "name": "nvme1n1",
                "maj:min": "8:224",
                "rm": "0",
                "size": "12.8T",
                "ro": "0",
                "type": "disk",
                "mountpoint": None,
            },
            {
                "name": "nvme0n1",
                "maj:min": "259:0",
                "rm": "0",
                "size": "726.3G",
                "ro": "0",
                "type": "disk",
                "mountpoint": None,
            },
        ]
        mock_cmd = "ls -la /sys/block/nvme0n1"
        mock_cmd2 = "ls -la /sys/block/nvme1n1"
        mock_output = (
            "lrwxrwxrwx 1 root root 0 Oct 21 08:29 /sys/block/nvme0n1 ->"
            " ../devices/pci0000:00/0000:00:1c.0/0000:01:00.0/nvme/nvme0/nvme0n1"
        )
        mock_output2 = (
            "lrwxrwxrwx 1 root root 0 Oct 21 08:29 /sys/block/nvme1n1 -> "
            "../devices/pci0000:3a/0000:3a:00.0/0000:3b:00.0/nvme/nvme1/nvme1n1"
        )
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        self.mock_host.update_cmd_map(mock_cmd2, mock_output2)
        out = DiskUtils.get_block_from_physical_location(
            self.mock_host, "0000:01:00.0", mock_drives
        )
        self.assertEqual(out, "nvme0n1")
        # Invalid case
        out = DiskUtils.get_block_from_physical_location(
            self.mock_host, "0000:00:1f.0", mock_drives
        )
        self.assertEqual(out, "")

    def test_is_drive_mounted(self):
        """Unittest for is_drive_mounted."""
        mock_drive = "nvme2n1"
        mock_cmd = "lsblk -J"
        # case 1: drive is partitioned and mounted
        mock_output = """{
"blockdevices": [
    {
        "name": "nvme2n1",
        "maj:min": "259:0",
        "rm": false,
        "size": "238.5G",
        "ro": false,
        "type": "disk",
        "mountpoints": [
            null
        ],
        "children": [
            {
            "name": "nvme2n1p1",
            "maj:min": "259:1",
            "rm": false,
            "size": "243M",
            "ro": false,
            "type": "part",
            "mountpoints": [
                "/boot/efi"
            ]
            }
        ]
    }
]
}"""
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        out = DiskUtils.is_drive_mounted(self.mock_host, mock_drive)
        self.assertTrue(out)

        # case 2: drive is partitioned but not mounted
        mock_output = """{
"blockdevices": [
    {
        "name": "nvme2n1",
        "maj:min": "259:0",
        "rm": false,
        "size": "238.5G",
        "ro": false,
        "type": "disk",
        "mountpoints": [
            null
        ],
        "children": [
            {
            "name": "nvme2n1p1",
            "maj:min": "259:1",
            "rm": false,
            "size": "243M",
            "ro": false,
            "type": "part",
            "mountpoints": [
                null
            ]
            }
        ]
    }
]
}"""
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        out = DiskUtils.is_drive_mounted(self.mock_host, mock_drive)
        self.assertFalse(out)

        # case 3: drive is unpartitioned and mounted
        mock_output = """{
"blockdevices": [
    {
        "name": "nvme2n1",
        "maj:min": "259:0",
        "rm": false,
        "size": "238.5G",
        "ro": false,
        "type": "disk",
        "mountpoints": [
            "/"
        ]
    }
]
}"""
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        out = DiskUtils.is_drive_mounted(self.mock_host, mock_drive)
        self.assertTrue(out)

        # case 4: drive is unpartitioned but not mounted
        mock_output = """{
"blockdevices": [
    {
        "name": "nvme2n1",
        "maj:min": "259:0",
        "rm": false,
        "size": "238.5G",
        "ro": false,
        "type": "disk",
        "mountpoints": [
            null
        ]
    }
]
}"""
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        out = DiskUtils.is_drive_mounted(self.mock_host, mock_drive)
        self.assertFalse(out)

    @patch(
        "autoval_ssd.lib.utils.disk_utils.DiskUtils.get_partitions_and_mount_points_in_drive"
    )
    @patch(
        "autoval_ssd.lib.utils.disk_utils.DiskUtils.get_block_from_physical_location"
    )
    def test_get_boot_drive(
        self,
        mock_get_block_from_physical_location,
        mock_get_partitions_and_mount_points_in_drive,
    ):
        # Test case 1: Boot drive is mounted and has mountpoint /boot
        self.mock_host = MockHost(copy.deepcopy(CMD_MAP))
        partition = {"sda": [{"mountpoint": "/boot"}]}
        mock_get_partitions_and_mount_points_in_drive.return_value = partition
        self.assertEqual(
            DiskUtils.get_boot_drive(self.mock_host, "0000:64:00.0"), "sda"
        )
        # Test case 2: Boot drive is not mounted but has boot sectors
        self.mock_host = MockHost(copy.deepcopy(CMD_MAP))
        mock_get_partitions_and_mount_points_in_drive.return_value = {}
        mock_get_block_from_physical_location.return_value = ""
        self.assertEqual(DiskUtils.get_boot_drive(self.mock_host, ""), "")
        # Test case 3: Boot drive is not mounted and doesn't have boot sectors, but has physical location in BOM file
        self.mock_host = MockHost(copy.deepcopy(CMD_MAP))
        mock_get_partitions_and_mount_points_in_drive.return_value = {}
        mock_get_block_from_physical_location.return_value = "sdc"
        self.assertEqual(
            DiskUtils.get_boot_drive(self.mock_host, "0000:65:00.0"), "sdc"
        )

    def test_get_partitions_and_mount_points_in_drive(self):
        """Unittest for get_partitions_and_mount_points_in_drive"""
        mock_cmd = "lsblk -J"
        mock_output = (
            '{\n "blockdevices": [\n {"name": "sdo", "maj:min": "8:224", '
            '"rm": "0", "size": "12.8T", "ro": "0", "type": "disk", '
            '"mountpoint": null}, \n {"name": "nvme9n1", "maj:min": "259:7",'
            '"rm": "0", "size": "1.8T", "ro": "0", "type": "disk", "mountpoint": null, \n'
            '"children": [\n {"name": "md0", "maj:min": "9:0", "rm": "0", "size": "3.5T", "ro": "0", "type": "raid0", "mountpoint": null, \n'
            '"children": [\n {"name": "md0p1", "maj:min": "259:18", "rm": "0", "size": "3.5T", "ro": "0", "type": "md", "mountpoint": "/"}\n]\n}\n]\n}\n]\n}'
        )
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        out = DiskUtils.get_partitions_and_mount_points_in_drive(self.mock_host)
        expected_out = {
            "nvme9n1": [
                {
                    "name": "md0",
                    "maj:min": "9:0",
                    "rm": "0",
                    "size": "3.5T",
                    "ro": "0",
                    "type": "raid0",
                    "mountpoint": None,
                    "children": [
                        {
                            "name": "md0p1",
                            "maj:min": "259:18",
                            "rm": "0",
                            "size": "3.5T",
                            "ro": "0",
                            "type": "md",
                            "mountpoint": "/",
                        }
                    ],
                }
            ]
        }
        self.assertDictEqual(expected_out, out)

    def test_create_partition(self):
        """Unittest for create_partition"""
        self.diskutils.create_partition(
            self.mock_host, "nvme1n1", "/mnt/autoval_mnt", 1, 0, 5, True
        )
        # Create partition by script
        self.diskutils.create_partition(
            self.mock_host,
            "nvme1n1",
            "/mnt/autoval_mnt",
            None,
            None,
            None,
            False,
            True,
            "unit b mkpart primary 128",
        )
        # validating Exception
        with mock.patch.object(
            self.mock_host, "run", side_effect=Exception("cmd failed")
        ), mock.patch.object(FilesystemUtils, "is_mounted", return_value=False):
            with self.assertRaises(TestError) as exp:
                self.diskutils.create_partition(
                    self.mock_host, "nvme1n1", "/mnt/autoval_mnt", 1, 0, 5, True
                )
            self.assertIn("Failed to create partition:", str(exp.exception))

    def test_get_drive_partitions_mountpoint(self):
        """unit test for get_drive_partitions_mountpoint."""
        mock_cmd = "lsblk -i /dev/nvme0n1"
        mock_cmd_output = (
            "nvme0n1      259:1    0 838.4G  0 disk\n"
            "├─nvme0n1p1  259:2    0  23.3G  0 part /mnt/d0 <- directory\n"
            "├─nvme0n1p2  259:3    0  23.3G  0 part /mnt/d1\n"
            "├─nvme0n1p3  259:4    0  23.3G  0 part /mnt/d2\n"
        )
        self.mock_host.update_cmd_map(mock_cmd, mock_cmd_output)
        out = DiskUtils.get_drive_partitions_mountpoint(self.mock_host, "nvme0n1")
        self.assertListEqual(out, ["/mnt/d0", "/mnt/d1", "/mnt/d2"])
        # in case no partition with mount point in format /mnt/d[0-9]+
        mock_cmd_output2 = (
            "NAME        MAJ:MIN RM   SIZE RO TYPE MOUNTPOINT\n"
            "nvme0n1     259:8    0 238.5G  0 disk\n"
            "|-nvme0n1p1 259:9    0   200M  0 part /boot/efi\n"
            "|-nvme0n1p2 259:10   0     1G  0 part /boot\n"
            "|-nvme0n1p3 259:11   0     1G  0 part [SWAP]\n"
            "`-nvme0n1p4 259:12   0 236.3G  0 part /\n"
        )
        self.mock_host.update_cmd_map(mock_cmd, mock_cmd_output2)
        out = DiskUtils.get_drive_partitions_mountpoint(self.mock_host, "nvme0n1")
        self.assertListEqual(out, [])

    @mock.patch.object(MockHost, "run")
    def test_umount_partition(self, mock_run):
        """Unit test for umount_partition"""
        # if not mounted is part of the Exception
        mock_run.side_effect = Exception("drive not mounted")
        DiskUtils.umount_partition(self.mock_host, "nvme0n1p1")
        # Validating exception
        mock_run.side_effect = Exception("Mounted Error")
        with self.assertRaises(TestError) as exp:
            DiskUtils.umount_partition(self.mock_host, "nvme0n1p1")
        self.assertEqual(
            "[AUTOVAL TEST ERROR] Fail to umount partition nvme0n1p1: Mounted Error",
            str(exp.exception),
        )

    def test_convert_from_bytes(self):
        byte_count = 100
        gb_unit = "g"
        expected_result_gb = 0.0000001
        tb_unit = "t"
        expected_result_tb = 0.0000000001
        mb_unit = "m"
        expected_result_mb = 0.0001
        result_gb = DiskUtils.convert_from_bytes(byte_count, gb_unit)
        self.assertEqual(result_gb, expected_result_gb)
        result_tb = DiskUtils.convert_from_bytes(byte_count, tb_unit)
        self.assertEqual(result_tb, expected_result_tb)
        result_mb = DiskUtils.convert_from_bytes(byte_count, mb_unit)
        self.assertEqual(result_mb, expected_result_mb)
        with self.assertRaises(TestError) as exp:
            DiskUtils.convert_from_bytes(byte_count, "fb")
        self.assertEqual(
            str(exp.exception), "[AUTOVAL TEST ERROR] fb unit is not supported"
        )

    @mock.patch.object(AutovalLog, "log_info")
    def test_remove_partition(self, mock_log):
        """
        This modules will validates the split, umount, & remove methods.
        """
        part = "nvme1n1p1"
        mock_log.side_effect = self.mock_log
        DiskUtils.remove_partition(self.mock_host, part)
        # Invalid case
        with mock.patch.object(
            DiskUtils,
            "split_block_and_part_num_from_partition",
            return_value=("mock_blk_nm", "mock_part_name"),
        ), mock.patch.object(
            DiskUtils, "umount_partition", return_value="pass"
        ), mock.patch.object(
            self.mock_host,
            "run",
            side_effect=[Exception("may not reflect"), Exception("cmd failed")],
        ), mock.patch.object(
            self.mock_host,
            "run",
            side_effect=[Exception("Partition doesn't exist"), Exception("cmd failed")],
        ):
            # In case the exception has may not reflect
            DiskUtils.remove_partition(self.mock_host, part)
            # Validating Exception
            with self.assertRaises(TestError) as exp:
                DiskUtils.remove_partition(self.mock_host, part)
            self.assertIn("Failed to remove partition", str(exp.exception))

    def test_split_block_and_part_num_from_partition(self):
        """Unittest for split_block_and_part_num_from_partition."""
        # nvme part
        part = "nvme1n1p1"
        blk_nm, part_no = DiskUtils.split_block_and_part_num_from_partition(part)
        self.assertEqual(blk_nm, "nvme1n1")
        self.assertEqual(part_no, "1")
        # hdd part
        part = "sda3"
        blk_nm, part_no = DiskUtils.split_block_and_part_num_from_partition(part)
        self.assertEqual(blk_nm, "sda")
        self.assertEqual(part_no, "3")
        # Invalid case
        part = "sda"
        with self.assertRaises(TestError) as exp:
            DiskUtils.split_block_and_part_num_from_partition(part)
        self.assertIn(
            f"Failed to get partition number from partition: {part}", str(exp.exception)
        )

    def test_get_physical_block_size(self):
        """Unittest for get_physical_block_size."""
        mock_cmd = "cat /sys/block/nvme0n1/queue/physical_block_size"
        mock_output = 256
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        out = DiskUtils.get_physical_block_size(self.mock_host, "nvme0n1")
        self.assertEqual(out, mock_output)

    def test_get_dev_size_bytes(self):
        """Unittest for get_dev_size_bytes."""
        mock_cmd = "cat /proc/partitions"
        mock_output = (
            "major minor  #blocks  name\n"
            "\n"
            " 259        0 1875374424 nvme3n1\n"
            " 259        3 1875373056 nvme3n1p1\n"
            " 259        1 1875374424 nvme2n1\n"
            " 259        4 1875373056 nvme2n1p1\n"
        )
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        out = DiskUtils.get_dev_size_bytes(self.mock_host, "nvme3n1")
        self.assertEqual(1920383410176, out)
        with self.assertRaises(TestError) as exp:
            DiskUtils.get_dev_size_bytes(self.mock_host, "sda")
        self.assertEqual(
            "[AUTOVAL TEST ERROR] Failed to get drive sda size", str(exp.exception)
        )

    def test_convert_to_bytes(self):
        """ "Unittest for convert_to_bytes"""
        # Type : int
        size = 2
        with self.assertRaises(TestError) as exp:
            DiskUtils.convert_to_bytes(size)
        self.assertIn(
            "Error: The input for convert_to_bytes is pure number. "
            "Needs to be in format of 2GB or 2TB or 2MB.",
            str(exp.exception),
        )
        size = "2GB"
        out = DiskUtils.convert_to_bytes(size)
        self.assertEqual(2147483648, out)
        size = "2TB"
        out = DiskUtils.convert_to_bytes(size)
        self.assertEqual(2199023255552, out)
        size = "2MB"
        out = DiskUtils.convert_to_bytes(size)
        self.assertEqual(2097152, out)
        size = "2KB"
        out = DiskUtils.convert_to_bytes(size)
        self.assertEqual(2048, out)
        size = "2XB"
        with self.assertRaises(TestError) as exp:
            DiskUtils.convert_to_bytes(size)
        self.assertIn(
            "Error: Please specify the data in TB, GB, MB or KB", str(exp.exception)
        )

    def test_get_md5_sum(self):
        """Unittest for get_md5_sum"""
        expected_md5_result = "491b74321392ef2afaa8d34c8aab67cf"
        path = "/mnt/"
        md5_result = DiskUtils.get_md5_sum(self.mock_host, path)
        self.assertEqual(str(md5_result), expected_md5_result)
        mock_cmd = "md5sum /mnt/"
        mock_output = ""
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        with self.assertRaises(TestError) as exp:
            DiskUtils.get_md5_sum(self.mock_host, path)
        self.assertEqual(
            "[AUTOVAL TEST ERROR] Failed to find md5sum in ", str(exp.exception)
        )

    def test_ramdisk(self):
        """Unittest for ramdisk."""
        # Create
        path = DiskUtils.ramdisk(self.mock_host, "create")
        self.assertEqual(path, "/mnt/autoval_test_ramdisk")
        # Delete
        path = DiskUtils.ramdisk(self.mock_host, "delete")
        self.assertEqual(path, "/mnt/autoval_test_ramdisk")
        # Other actions: Asserting if exception is raised.
        with self.assertRaises(TestError) as exp:
            DiskUtils.ramdisk(self.mock_host, "update")
        self.assertEqual(
            "[AUTOVAL TEST ERROR] Action update not supported", str(exp.exception)
        )

    def test_get_seconds(self):
        """Unittest for get_seconds."""
        time = "1200s"
        out = DiskUtils.get_seconds(time)
        self.assertEqual(out, 1200)
        time = "1200h"
        out = DiskUtils.get_seconds(time)
        self.assertEqual(out, 4320000)
        time = "2d"
        out = DiskUtils.get_seconds(time)
        self.assertEqual(out, 172800)
        time = "1w"
        out = DiskUtils.get_seconds(time)
        self.assertEqual(out, 604800)
        time = "120m"
        out = DiskUtils.get_seconds(time)
        self.assertEqual(out, 7200)
        time = "1y"
        with self.assertRaises(TestError) as exp:
            DiskUtils.get_seconds(time)
        self.assertEqual(
            f"[AUTOVAL TEST ERROR] Unable to convert {time} to seconds",
            str(exp.exception),
        )

    def test_get_bytes(self):
        """Unittest for get_bytes."""
        # valid case
        sizes = ["12kib", "12kb", "12mib", "12mb", "12gib", "12GB", "12tIB", "12Tb"]
        mock_outputs = [
            12288,
            12000,
            12582912,
            12000000,
            12884901888,
            12000000000,
            13194139533312,
            12000000000000,
        ]
        results = [DiskUtils.get_bytes(_size) for _size in sizes]
        self.assertListEqual(results, mock_outputs)
        # Invalid case
        size = "!2!b"
        with self.assertRaises(TestError) as exp:
            DiskUtils.get_bytes(size)
        self.assertEqual(
            f"[AUTOVAL TEST ERROR] Unable to convert {size} to bytes",
            str(exp.exception),
        )

    def test_get_size_of_directory(self):
        """Unittest for get_size_of_directory."""
        # Case with size_in_unit = b
        mock_cmd = "du -shb mock_dir"
        mock_output = "6       FB_Sphinx"
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        out = DiskUtils.get_size_of_directory(
            self.mock_host, "mock_dir", size_in_unit="b"
        )
        self.assertEqual(out, 6)
        # Case with size_in_unit = b
        mock_cmd = "du -sh --block-size=K mock_dir"
        mock_output = "0K       FB_Sphinx"
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        out = DiskUtils.get_size_of_directory(self.mock_host, "mock_dir")
        self.assertEqual(out, 0)
        # Invalid case
        mock_output = "mock"
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        with self.assertRaises(TestError) as exp:
            DiskUtils.get_size_of_directory(self.mock_host, "mock_dir")
        self.assertEqual(
            "[AUTOVAL TEST ERROR] No match for directory size "
            "found, check if directory exists",
            str(exp.exception),
        )

    def test_create_file(self):
        """Unittest for create_file."""
        mock_cmd = "fallocate -l 12884901888 mock"
        mock_output = "mock space allocated"
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        out = DiskUtils.create_file(self.mock_host, "mock", "12G")
        self.assertEqual(out, mock_output)
        # tool = dd
        mock_cmd = "dd if=/dev/urandom of=mock bs=1k count=12582912"
        mock_output = "mock space allocated"
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        out = DiskUtils.create_file(self.mock_host, "mock", "12G", tool="dd")
        self.assertEqual(out, mock_output)
        # other tools
        with self.assertRaises(TestError) as exp:
            DiskUtils.create_file(self.mock_host, "mock", "12G", tool="fio")
        self.assertEqual(
            "[AUTOVAL TEST ERROR] tool 'fio' not supported", str(exp.exception)
        )

    @mock.patch("autoval_ssd.lib.utils.disk_utils.Host")
    def test_get_md5_for_drivelist(self, mock_run):
        """Unittest for get_md5_for_drivelist."""
        mock_run.return_value = self.mock_host
        mock_cmd_map = {
            "md5sum mock/path_sd0": "491b74321392ef2afaa8d34c8aab67cf",
            "md5sum mock/path_nvme0n1": "491b74321392ef2afaa8d34c8aab67",
            "date +%s": "1603372118",
        }
        mock_output = {
            "sd0": "491b74321392ef2afaa8d34c8aab67cf",
            "nvme0n1": "491b74321392ef2afaa8d34c8aab67",
        }
        for cmd, result in mock_cmd_map.items():
            self.mock_host.update_cmd_map(cmd, result)
        drive_path_map = {"sd0": "mock/path_sd0", "nvme0n1": "mock/path_nvme0n1"}
        out = DiskUtils.get_md5_for_drivelist(
            self.mock_host,
            drive_path_map,
            parallel=False,
        )
        # parallel: True
        self.assertDictEqual(out, mock_output)
        out = DiskUtils.get_md5_for_drivelist(
            self.mock_host,
            drive_path_map,
            "mock/path",
        )
        self.assertDictEqual(out, mock_output)

    def test_list_scsi_devices(self):
        """Unittest for list_scsi_devices."""
        mock_cmd = "lsscsi -g"
        result = (
            "[0:0:1:0]    disk    FUJITSU  MAM3184MP        0105  /dev/sda  /dev/sg0\n"
            "[0:0:1:0]    disk    FUJITSU  MAM3184MP        0105  /dev/sdb  /dev/sg1"
        )
        # sda is a boot drive which should be excluded n final
        # output
        expected_output = [
            {
                "channel_target_lun": "[0:0:1:0]",
                "type": "disk",
                "device": "sdb",
                "sg_device": "sg1",
            }
        ]
        self.mock_host.update_cmd_map(mock_cmd, result)
        out = DiskUtils.list_scsi_devices(self.mock_host)
        self.assertListEqual(out, expected_output)

    def test_delete_partitions(self):
        """Unittest for delete_partitions."""
        mock_cmd = "sg_readcap /dev/nvme0n1p1"
        mock_output = "Logical block length=20"
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        DiskUtils.delete_partitions(self.mock_host, "nvme0n1p1")

    @mock.patch.object(MockHost, "run")
    def test_format_hdd(self, mock_run):
        """Unittest for format_hdd."""
        mock_device = "mock"
        mock_run.return_value = "pass"
        DiskUtils.format_hdd(self.mock_host, mock_device)
        mock_run.assert_called_once_with(
            "dd if=/dev/urandom of=/dev/%s bs=1M" % mock_device, timeout=43200
        )
        mock_run.reset_mock()
        DiskUtils.format_hdd(self.mock_host, mock_device, secure_erase_option=1)
        mock_run.assert_called_once_with(
            "shred -vfz /dev/%s" % mock_device, timeout=43200
        )

    def mock_log(self, log):
        """Method acts as and alternative to
        Autoval.log_info."""
        self.log += log

    @mock.patch.object(MockHost, "run")
    @mock.patch.object(AutovalLog, "log_info")
    def test_drop_cache_emmc(self, mock_log, mock_run):
        """Unittest for drop_cache_emmc."""
        mock_run.return_value = "pass"
        DiskUtils.drop_cache_emmc(self.mock_host)
        self.assertEqual(mock_run.call_count, 1)
        mock_run.side_effect = Exception("Command failed.")
        mock_log.side_effect = self.mock_log
        DiskUtils.drop_cache_emmc(self.mock_host)
        self.assertEqual(self.log, "Failed to drop cache: Command failed.")

    @mock.patch.object(MockHost, "run")
    @mock.patch.object(FilesystemUtils, "is_mounted")
    def test_umount(self, mock_is_mount, mock_run):
        """Unittest for umount."""
        mock_is_mount.return_value = True
        mock_run.return_value = "pass"
        mock_mnt_point = "mock/point"
        # Assert if the unmount and rmdir is called when mount point
        # is available.
        calls = [
            mock.call("umount -fl %s" % mock_mnt_point, sudo=True),
            mock.call("rmdir %s" % mock_mnt_point),
        ]
        DiskUtils.umount(self.mock_host, mock_mnt_point)
        mock_run.assert_has_calls(calls=calls)
        mock_run.reset_mock()
        # Asserting that the host.run is not called in case of
        # mount point not available.
        mock_is_mount.return_value = False
        DiskUtils.umount(self.mock_host, mock_mnt_point)
        self.assertFalse(mock_run.called)

    def test_calculate_min_size_of_drives(self):
        """Unittest calculate_min_size_of_drives."""
        mock_cmd = "cat /proc/partitions"
        mock_output = (
            "major minor  #blocks  name\n"
            "\n"
            " 259        0 1875374424 nvme3n1\n"
            " 259        3 1875373056 nvme3n1p1\n"
            " 259        1 1875374424 nvme2n1\n"
            " 259        4 1875373056 nvme2n1p1\n"
        )
        self.mock_host.update_cmd_map(mock_cmd, mock_output)
        out = DiskUtils.calculate_min_size_of_drives(
            self.mock_host, 80, ["nvme2n1", "nvme3n1"]
        )
        self.assertEqual(out, "1536gb")

    @mock.patch.object(AutovalLog, "log_info")
    def test_check_drive_health(self, mock_log_info):
        """Unit test to check drive health"""
        mock_log_info.side_effect = self.mock_log
        data = "slot1-2U-dev1 : Normal"
        DiskUtils.check_drive_health(data)
        log_msg = "All data drives are in good state: {'slot1-2U-dev1 ': ' Normal'}"
        self.assertIn(self.log, log_msg)

    @mock.patch.object(DiskUtils, "umount", return_value=None)
    def test_remove_mount_points(self, umount):
        # For drive with mountpoint
        self.assertIsNone(
            DiskUtils.remove_mount_points(self.mock_host, block_name="nvme0n1")
        )
        # For drive without mountpoint
        self.assertIsNone(
            DiskUtils.remove_mount_points(self.mock_host, block_name="nvme1n1")
        )
