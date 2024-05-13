#!/usr/bin/env python3

# pyre-unsafe
from typing import Optional

from autoval_ssd.lib.utils.storage.nvme.nvme_drive import NVMeDrive


class NVMeDriveFactory:
    @staticmethod
    def create(host, drive: str, config: Optional[str] = None) -> NVMeDrive:
        """
        @param Host host:
        @param String drive: e.g. nvme1n1
        @param String config: config file name
        """
        return NVMeDrive(host, drive, config=config)
