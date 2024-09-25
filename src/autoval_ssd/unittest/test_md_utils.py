# pyre-unsafe
from unittest import TestCase
from unittest.mock import patch

from autoval.lib.utils.autoval_exceptions import TestError, TestStepError
from autoval.lib.utils.autoval_log import AutovalLog

from autoval_ssd.lib.utils.md_utils import MDUtils
from autoval_ssd.unittest.mock.lib.mock_host import MockHost

CMDMAP = []
lsblk_drive = """NAME        MAJ:MIN RM  SIZE RO TYPE MOUNTPOINT
%s     259:0    0  1.8T  0 disk
`-%s%s 259:2    0  1.8T  0 part
"""
lsblk_mnt_point = """NAME        MOUNTPOINT
sda
`-sda1
  `-{0}   /mnt/autoval_{0}
nvme0n1
`-nvme0n1p1
  `-{0}   /mnt/autoval_{0}
"""
raid_df_info = "{0}     {1}  3838618247168 23932035072 3814686212096   1% {2}"

mdadm_detail = """/dev/md125:
           Version : 1.2
     Creation Time : Sun Sep 20 17:32:09 2020
        Raid Level : raid0
        Array Size : 3750483968 (3.49 TiB 3.84 TB)
      Raid Devices : 2
     Total Devices : 2
       Persistence : Superblock is persistent
       Update Time : Sun Sep 20 17:32:09 2020
             State : {state}
    Active Devices : 2
   Working Devices : 2
    Failed Devices : 0
     Spare Devices : 0
            Layout : original
        Chunk Size : 128K
Consistency Policy : none
              Name : ZSP93101231:125  (local to host ZSP93101231)
              UUID : d237bfdb:d3588f2c:38942584:db5bb910
            Events : 0
    Number   Major   Minor   RaidDevice State
       0     259        1        0      active sync   /dev/nvme0n1p1
       1       8        1        1      active sync   /dev/sda1
"""


class MdUtilsUnitTest(TestCase):
    """Class to test MdUtils"""

    def setUp(self) -> None:
        self.mock_host = MockHost(cmd_map=CMDMAP)
        self.output_dict = {}

    def mock_log(self, log):
        """Mock AutovalLog log_info"""
        self.log = ""
        if isinstance(log, dict):
            self.output_dict = log
        else:
            self.log += str(log)

    def get_cmd_list(self):
        """Generating dynamic cmd and result from arg_list"""
        args_list = [
            {
                "host": self.mock_host,
                "devices": ["nvme1n1", "nvme2n1"],
                "raid_device": "md125",
                "fstype": "xfs",
                "mount_point": "/mnt/autoval_md125",
                "stripe_size": 128,
            },
            {
                "host": self.mock_host,
                "devices": ["nvme1n1", "nvme2n1", "nvme3n1"],
                "raid_device": "md521",
                "fstype": "xfs",
                "mount_point": "/mnt/autoval_md521",
                "stripe_size": 128,
            },
            {
                "host": self.mock_host,
                "devices": ["nvme1n1", "sda"],
                "raid_device": "md123",
                "fstype": "ext4",
                "mount_point": "/mnt/autoval_md123",
                "stripe_size": 256,
            },
        ]
        cmd_result_1 = []
        for args in args_list:
            proc_partitions = ""
            for device in args["devices"]:
                proc_partitions += f"{259 + 1}        0 1875374424 {device}\n"
                cmd_result_1 += [
                    {
                        "cmd": f"lsblk -i /dev/{device}",
                        "result": lsblk_drive
                        % (device, device, "p1" if "nvme" in device else "1"),
                    },
                    {"cmd": f"umount /dev/{device}", "result": True},
                    {"cmd": f"parted -a optimal /dev/{device} rm", "result": True},
                    {
                        "cmd": f"parted -s /dev/{device} unit b "
                        f"mkpart primary 131072 1920383279104",
                        "result": True,
                    },
                    {"cmd": f"parted -s /dev/{device} set 1 raid", "result": True},
                    {
                        "cmd": (
                            f"mdadm --zero-superblock --force /dev/{device}p1"
                            if "nvme" in device
                            else f"mdadm --zero-superblock --force /dev/{device}1"
                        ),
                        "result": True,
                    },
                    {
                        "cmd": f'mdadm --manage /dev/{args["raid_device"]} '
                        f"--re-add {device}",
                        "result": True,
                    },
                ]

            cmd_result_2 = [
                {"cmd": f'mountpoint {args["mount_point"]}', "result": 1},
                {"cmd": "cat /proc/partitions", "result": proc_partitions},
                {
                    "cmd": f'cat /sys/block/{args["raid_device"]}/queue/'
                    f"physical_block_size",
                    "result": 4096,
                },
                {
                    "cmd": f'mountpoint -q {args["mount_point"]} && echo "mounted"',
                    "result": "mounted",
                },
                {"cmd": f'umount -fl {args["mount_point"]}', "result": True},
                {"cmd": f'rmdir {args["mount_point"]}', "result": True},
                {
                    "cmd": f'mkfs.xfs {"-f" if args["fstype"] == "xfs" else "-F"}'
                    + f" -K -i size=2048 -d su=131072,sw=2 -l su=4096 "
                    f'/dev/{args["raid_device"]}',
                    "result": "xfs file system created",
                },
                {
                    "cmd": f"mount -o noatime,nodiratime,discard,nobarrier "
                    f'/dev/{args["raid_device"]} {args["mount_point"]}',
                    "result": True,
                },
                {
                    "cmd": f'df -B 1 -T /dev/{args["raid_device"]}*',
                    "result": raid_df_info.format(
                        "/dev/" + args["raid_device"],
                        args["fstype"],
                        args["mount_point"],
                    ),
                },
                {
                    "cmd": f'mdadm --create /dev/{args["raid_device"]} --metadata'
                    f" 1.2 --chunk 128 --level 0 --run --raid-devices "
                    + f'{len(args["devices"])} /dev/'
                    + " /dev/".join(args["devices"]),
                    "result": f'mdadm: array /dev/{args["raid_device"]} started.',
                },
                {
                    "cmd": "cat /proc/mdstat",
                    "result": "Personalities :\n unused devices: <none>",
                },
                {"cmd": 'echo "AUTO -all" > /etc/mdadm.conf', "result": True},
                {"cmd": "partprobe", "result": True},
                {
                    "cmd": f'cat /sys/block/{args["raid_device"]}/md/sync_action',
                    "result": "Enabled",
                },
                {
                    "cmd": "lsblk -o name,mountpoint",
                    "result": lsblk_mnt_point.format(args["raid_device"]),
                },
                {"cmd": f'mdadm  --stop /dev/{args["raid_device"]}', "result": True},
                {"cmd": f'mdadm --remove /dev/{args["raid_device"]}', "result": True},
                {
                    "cmd": f'echo Enable > /sys/block/{args["raid_device"]}'
                    f"/md/sync_action",
                    "result": True,
                },
                {"cmd": f'parted -s /dev/{args["devices"][0]}p1 rm 1', "result": True},
                {"cmd": "cat /proc/partitions", "result": proc_partitions},
            ]
            cmd_result = cmd_result_1 + cmd_result_2
            for c_r in cmd_result:
                self.mock_host.update_cmd_map(cmd=c_r["cmd"], mock_output=c_r["result"])
            yield args

    @patch.object(AutovalLog, "log_info")
    @patch("time.sleep")
    def test_setup_md_raid0(self, mock_sleep, mock_log):
        """unittest for setup_md_raid0"""
        mock_sleep.return_value = True
        mock_log.side_effect = self.mock_log
        for args in self.get_cmd_list():
            MDUtils.setup_md_raid0(
                args["host"],
                args["devices"],
                raiddevice=args["raid_device"],
                fstype=args["fstype"],
                mount_point=args["mount_point"],
                stripe_size=args["stripe_size"],
            )
            self.assertIsInstance(self.output_dict, dict)
            self.assertEqual(self.output_dict["type"], args["fstype"])
            self.assertEqual(self.output_dict["mounted_on"], args["mount_point"])

    def test_list_md_arrays(self):
        """unittest for list_md_arrays"""
        for args in self.get_cmd_list():
            result = args["raid_device"] + " : active raid0 sda1[1] nvme0n1p1[0]"
            self.mock_host.update_cmd_map("cat /proc/mdstat", result)
            out = MDUtils.list_md_arrays(args["host"])
            self.assertIsInstance(out, dict)
            self.assertEqual(args["raid_device"], "".join(out.keys()))
            self.mock_host.update_cmd_map("cat /proc/mdstat", mock_output="")
            self.assertEqual(MDUtils.list_md_arrays(args["host"]), {})

    def test_get_md_mount_point(self):
        """unittest for get_md_mount_point"""
        for args in self.get_cmd_list():
            self.mock_host.update_cmd_map(
                "lsblk -o name,mountpoint",
                mock_output=lsblk_mnt_point.format(args["raid_device"]),
            )
            out = MDUtils.get_md_mount_point(args["host"], args["raid_device"])
            self.assertEqual(out, args["mount_point"])
            out = MDUtils.get_md_mount_point(args["host"], "")
            self.assertEqual(out, "")

    @patch.object(AutovalLog, "log_info")
    def test_remove_md_array(self, mock_log):
        """unittest for remove_md_array"""
        for args in self.get_cmd_list():
            mock_log.side_effect = self.mock_log
            out = MDUtils.remove_md_array(args["host"], args["raid_device"])
            self.assertFalse(out, "asserting nil raid devices")
            result = args["raid_device"] + " : active raid0 sda1[1] nvme0n1p1[0]"
            self.mock_host.update_cmd_map("cat /proc/mdstat", result)
            out = MDUtils.remove_md_array(args["host"], args["raid_device"])
            self.assertTrue(out, "asserting raid device remove")
            self.assertEqual(self.log, f'Deleted array {args["raid_device"]}')

    @patch.object(AutovalLog, "log_info")
    def test_remove_all_md_arrays(self, mock_log):
        """unittest for remove_all_md_arrays"""
        for args in self.get_cmd_list():
            mock_log.side_effect = self.mock_log
            result = args["raid_device"] + " : active raid0 sda1[1] nvme0n1p1[0]"
            self.mock_host.update_cmd_map("cat /proc/mdstat", result)
            MDUtils.remove_all_md_arrays(args["host"])
            self.assertEqual(self.log, f'Deleted array {args["raid_device"]}')

    def test_check_for_active_array(self):
        """unittest for check_for_active_array"""
        for args in self.get_cmd_list():
            result = args["raid_device"] + " : active raid0 sda1[1] nvme0n1p1[0]"
            self.mock_host.update_cmd_map("cat /proc/mdstat", result)
            self.assertTrue(MDUtils.check_for_active_array(args["host"]))
            self.mock_host.update_cmd_map("cat /proc/mdstat", mock_output="")
            self.assertFalse(MDUtils.check_for_active_array(args["host"]))
            result = args["raid_device"] + " : inactive raid0 sda1[1] nvme0n1p1[0]"
            self.mock_host.update_cmd_map("cat /proc/mdstat", mock_output=result)
            with self.assertRaises(TestError) as _:
                MDUtils.check_for_active_array(args["host"])

    def test_get_md_sync_action(self):
        """unittest for get_md_sync_action"""
        for args in self.get_cmd_list():
            out = MDUtils.get_md_sync_action(args["host"], args["raid_device"], "raid0")
            self.assertEqual(out, "Enabled")

    def test_validate_sync_action(self):
        """unittest for validate_sync_action"""
        for args in self.get_cmd_list():
            self.assertTrue(
                MDUtils.validate_sync_action(
                    args["host"], args["raid_device"], "Enabled", "raid0"
                )
            )
            with self.assertRaises(TestStepError) as _:
                self.assertTrue(
                    MDUtils.validate_sync_action(
                        args["host"], args["raid_device"], "Disabled", "raid0"
                    )
                )

    def test_readd_drive_to_md_array(self):
        """unittest for readd_drive_to_md_array"""
        for args in self.get_cmd_list():
            self.assertTrue(
                MDUtils.readd_drive_to_md_array(
                    args["host"], args["raid_device"], args["devices"][0]
                )
            )

    def test_set_md_sync_action(self):
        """Unittest for set_md_sync_action"""
        for args in self.get_cmd_list():
            MDUtils.set_md_sync_action(
                args["host"], args["raid_device"], "Enable", "raid1"
            )
            self.mock_host.update_cmd_map(
                f'echo Enable > /sys/block/{args["raid_device"]}' f"/md/sync_action",
                False,
            )
            with self.assertRaises(TestStepError) as exp:
                MDUtils.set_md_sync_action(
                    args["host"], args["raid_device"], "Enable", "raid1"
                )
            self.assertRegex(str(exp.exception), "Set md sync action as.*")

    def test_cleanup_md_raid0(self):
        """Unittest for cleanup_md_raid0"""
        for args in self.get_cmd_list():
            MDUtils.cleanup_md_raid0(args["host"], [args["devices"][0] + "p1"])
