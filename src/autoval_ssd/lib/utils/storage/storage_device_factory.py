#!/usr/bin/env python3

# pyre-unsafe
import re
from typing import List, Optional

from autoval.lib.host.host import Host
from autoval.lib.utils.async_utils import AsyncJob, AsyncUtils
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval_ssd.lib.utils.storage.drive import Drive
from autoval_ssd.lib.utils.storage.nvme.nvme_factory import NVMeDriveFactory
from autoval_ssd.lib.utils.storage.sas.sas_drive import SASDrive
from autoval_ssd.lib.utils.storage.sata.sata_drive import SATADrive


class StorageDeviceFactory:
    """
    Generate drive objects for the provided block names.
    """

    def __init__(
        self, host: Host, block_names: List[str], config: Optional[str] = None
    ) -> None:
        """
        @param Host host: host object
        @param String[] block_names: list of drive names; e.g. sdb, sdc
        @param String config: json file that controls how drive data is
            collected and validated
        """
        self.host = host
        self.block_names = block_names
        self.nvme_list = []
        self.sata_drive_list = []
        self.emmc_drive_list = ["mmcblk0"]
        self.config = config

    def create(self) -> List[Drive]:
        self._cache_nvme_names()
        self._cache_sata_drives_name()
        return AsyncUtils.run_async_jobs(
            [
                AsyncJob(func=self._create_drive, args=[block_name])
                for block_name in self.block_names
            ]
        )

    def _create_drive(self, block_name: str) -> Drive:
        obj = None
        host = self._get_host(thread=True)
        if self._is_drive_nvme(block_name):
            obj = NVMeDriveFactory.create(host, block_name, config=self.config)
        elif self._is_drive_sata(block_name):
            obj = SATADrive(host, block_name, config=self.config)
        elif self._is_drive_sas(block_name):
            obj = SASDrive(host, block_name, config=self.config)
        else:
            obj = Drive(host, block_name, config=self.config)
            AutovalLog.log_info(
                "WARNING: Drive %s interface not determined" % block_name
            )
        return obj

    def _is_drive_nvme(self, block_name: str) -> bool:
        if str(block_name) in self.nvme_list:
            return True
        return False

    def _cache_sata_drives_name(self) -> None:
        """
        Run `lsscsi` command to get all SATA drive names on the system.
        """
        patt = r"ATA.*\/dev\/(sd(?:\w+))"
        output = self._get_host().run("lsscsi")
        # Example output SATA drives
        # [6:0:76:0]   disk    ATA      <vendor_name>  <drive_model_id>  /dev/sdd
        # [6:0:108:0]  disk    ATA      <vendor_name>  <drive_model_id>  /dev/sdaj
        # ...
        # Example output SAS drives
        # [6:0:99:0]   disk    <vendor_name>      <drive_model_id>  C110  /dev/sdaa
        # [6:0:97:0]   disk    <vendor_name>      <drive_model_id>  C110  /dev/sdy
        # ...
        self.sata_drive_list.extend(re.findall(patt, output))

    def _cache_nvme_names(self) -> None:
        """
        `nvme list` shows info of all nvme drives on the system. Run this
            command once and cache its output to avoid repeated call for
            each drive
        """
        cmd_output = self._get_host().run("nvme list")
        nvme_list = re.findall(r"^/dev/(\w+)", cmd_output, re.M)
        self.nvme_list.extend(nvme_list)

    def _is_drive_sas(self, block_name: str) -> bool:
        smart = self._get_host(thread=True).run(
            "smartctl -x /dev/%s" % block_name, ignore_status=True
        )
        pattern = r"Transport\sprotocol:\s+SAS"
        if re.search(pattern, smart):
            return True
        return False

    def _is_drive_sata(self, block_name: str) -> bool:
        """
        @param String block_name: drive name in /dev/ path
        @return boolean
        """
        if str(block_name) in self.sata_drive_list:
            return True
        return False

    def _get_host(self, thread: bool = False) -> Host:
        """
        Provide a new host object for multi-threaded calls in create()
        """
        return Host(AutovalUtils.get_host_dict(self.host)) if thread else self.host
