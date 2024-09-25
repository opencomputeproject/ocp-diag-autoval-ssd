# pyre-unsafe
import unittest
from collections import namedtuple
from unittest.mock import patch

from autoval_ssd.lib.utils.storage.storage_device_factory import StorageDeviceFactory

from autoval_ssd.unittest.mock.lib.mock_host import MockHost

CMD_MAP = [
    {"cmd": "nvme list", "file": "nvme_list"},
    {"cmd": "lsscsi", "file": "lsscsi"},
    {"cmd": "smartctl -x /dev/sdd", "file": "smartctl_sas_drive"},
]

MOCK_NVME = namedtuple("NVMeDrive", ["host", "block_name"])
MOCK_SATA = namedtuple("SATADrive", ["host", "block_name"])
MOCK_SAS = namedtuple("SASDrive", ["host", "block_name"])
MOCK_DRIVE = namedtuple("Drive", ["host", "block_name"])


class StorageDeviceFactoryUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.host = MockHost(cmd_map=CMD_MAP)
        self.invalid_drive = "xyz"

    @patch("autoval_ssd.lib.utils.storage.storage_device_factory.NVMeDriveFactory")
    def test_create_nvme(self, mock_nmve):
        """
        This method validates the drive object returned is the object
        of NVMeDrive class.
        """
        nvme0n1 = MOCK_NVME(self.host, "nvme0n1")
        nvme1n1 = MOCK_NVME(self.host, "nvme1n1")
        nvme2n1 = MOCK_NVME(self.host, "nvme2n1")
        nvme3n1 = MOCK_NVME(self.host, "nvme3n1")
        nvme4n1 = MOCK_NVME(self.host, "nvme4n1")
        nvme5n1 = MOCK_NVME(self.host, "nvme5n1")
        nvme6n1 = MOCK_NVME(self.host, "nvme6n1")
        block_names = [
            "nvme0n1",
            "nvme1n1",
            "nvme2n1",
            "nvme3n1",
            "nvme4n1",
            "nvme5n1",
            "nvme6n1",
        ]
        with patch.object(StorageDeviceFactory, "_get_host", return_value=self.host):
            mock_nmve.create.side_effect = (
                nvme0n1,
                nvme1n1,
                nvme2n1,
                nvme3n1,
                nvme4n1,
                nvme5n1,
                nvme6n1,
            )
            sdf = StorageDeviceFactory(self.host, block_names)
            drive_list = sdf.create()
            self.assertEqual(sdf.nvme_list, block_names)
            self.assertEqual(
                set(drive_list),
                {nvme0n1, nvme1n1, nvme2n1, nvme3n1, nvme4n1, nvme5n1, nvme6n1},
            )

    @patch("autoval_ssd.lib.utils.storage.storage_device_factory.SATADrive")
    def test_create_sata(self, mock_object):
        """
        This method validates the drive object returned is the object
        of SATADrive class.
        """
        sda = MOCK_SATA(self.host, "sda")
        block_name = ["sda"]
        with patch.object(StorageDeviceFactory, "_get_host", return_value=self.host):
            mock_object.return_value = sda
            sdf = StorageDeviceFactory(self.host, block_name)
            drive_list = sdf.create()
            self.assertEqual(sdf.sata_drive_list, block_name)
            self.assertListEqual(drive_list, [sda])

    @patch("autoval_ssd.lib.utils.storage.storage_device_factory.SASDrive")
    def test_create_sas(self, mock_object):
        """
        This method validates the drive object returned is the object
        of SASDrive class.
        """
        sdd = MOCK_SAS(self.host, "sdd")
        block_name = ["sdd"]
        with patch.object(StorageDeviceFactory, "_get_host", return_value=self.host):
            mock_object.return_value = sdd
            sdf = StorageDeviceFactory(self.host, block_name)
            drive_list = sdf.create()
            self.assertListEqual(drive_list, [sdd])

    @patch("autoval_ssd.lib.utils.storage.storage_device_factory.Drive")
    def test_create_no_drive_interface(self, mock_object):
        """
        This method validates the drive object returned is the object
        of Drive class.
        """
        invalid_drive = MOCK_DRIVE(self.host, self.invalid_drive)
        block_name = [self.invalid_drive]
        with patch.object(StorageDeviceFactory, "_get_host", return_value=self.host):
            mock_object.return_value = invalid_drive
            sdf = StorageDeviceFactory(self.host, block_name)
            drive_list = sdf.create()
            self.assertListEqual(drive_list, [invalid_drive])

    @patch("autoval_ssd.lib.utils.storage.storage_device_factory.NVMeDriveFactory")
    @patch("autoval_ssd.lib.utils.storage.storage_device_factory.SATADrive")
    @patch("autoval_ssd.lib.utils.storage.storage_device_factory.SASDrive")
    @patch("autoval_ssd.lib.utils.storage.storage_device_factory.Drive")
    def test_create_all_interface(self, mock_object, mock_sas, mock_sata, mock_nvme):
        """
        This method validates the list of drive object returned is the object
        of NVMeDrive, SATADrive, SASDrive and Drive class.
        """
        nvme0n1 = MOCK_NVME(self.host, "nvme0n1")
        nvme1n1 = MOCK_NVME(self.host, "nvme1n1")
        sda = MOCK_SATA(self.host, "sda")
        sdd = MOCK_SAS(self.host, "sdd")
        invalid_drive = MOCK_DRIVE(self.host, self.invalid_drive)
        block_names = [
            "mmcblk0",
            "nvme0n1",
            "sda",
            "sdd",
            self.invalid_drive,
            "nvme1n1",
        ]
        with patch.object(StorageDeviceFactory, "_get_host", return_value=self.host):
            mock_nvme.create.side_effect = (nvme0n1, nvme1n1)
            mock_sata.return_value = sda
            mock_sas.return_value = sdd
            mock_object.return_value = invalid_drive
            sdf = StorageDeviceFactory(self.host, block_names)
            drive_list = sdf.create()
            self.assertEqual(
                set(drive_list),
                {nvme0n1, sda, sdd, invalid_drive, nvme1n1},
            )
