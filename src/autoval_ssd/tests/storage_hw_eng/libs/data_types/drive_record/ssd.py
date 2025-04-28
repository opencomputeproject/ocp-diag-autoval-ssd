# pyre-unsafe
import json
import typing as t

import autoval.lib.host.host as havoc_host
import autoval_ssd.lib.utils.storage.storage_device_factory as dev_fact
from autoval_ssd.lib.utils.storage.nvme.nvme_drive import NVMeDrive
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.tests.storage_hw_eng.libs.data_types.data_record.data_record import (
    datarec,
    item,
)

from .drive_record import DriveRecord


def load_if_json(val):
    if isinstance(val, str):
        return json.loads(val)


@datarec
class SSDDriveRecord(DriveRecord):
    """
    Represents a SSD Drive on a host.
    """

    vendor_id = item(data_type=int, keyword="vendor_id", docstr="The Vendor ID.")

    id_ctrl = item(
        data_type=t.Union[t.Dict, str],
        keyword="id_ctrl",
        converter=load_if_json,
        docstr="ID Nvme Controller.",
    )

    id_ns = item(
        data_type=t.Union[t.Dict, str],
        keyword="id_ns",
        converter=load_if_json,
        docstr="ID Namespace.",
    )

    power_mode = item(
        data_type=t.Optional[str], keyword="power_mode", docstr="SSD Power Mode"
    )

    def __init__(
        self, vendor_id=vendor_id, id_ctrl=id_ctrl, id_ns=id_ns, power_mode=power_mode
    ):
        SSDDriveRecord.vendor_id = vendor_id
        SSDDriveRecord.id_ctrl = id_ctrl
        SSDDriveRecord.id_ns = id_ns
        SSDDriveRecord.power_mode = power_mode

    @staticmethod
    def get_mounted_SSD_drives(
        host: havoc_host.Host,
        collect_drive_data: bool,
        devnames: t.Optional[t.List[str]] = None,
        logger=None,
    ) -> t.List["SSDDriveRecord"]:
        # Get list of drive devnames
        if devnames is None:
            devnames = [dev["DevicePath"] for dev in NVMeUtils.get_nvme_list(host)]

        # Gather information from the factory method
        logger("Generating Drives")
        devnames_ending = [devname.split("/")[-1] for devname in devnames]
        drive_objs = dev_fact.StorageDeviceFactory(host, devnames_ending).create()

        # Now create the list of SSDDriveRecords
        drives = []
        for drive_obj in drive_objs:
            if not collect_drive_data:
                logger(
                    f"Skipping Drive Information from {f'/dev/{drive_obj.block_name}'}"
                )
                data = {"id_ctrl": None, "id_ns": None}
            else:
                logger(
                    f"Grabbing Drive Information from {f'/dev/{drive_obj.block_name}'}"
                )
                data = drive_obj.collect_data()

            # Try getting the Power Mode
            try:
                power_mode = NVMeDrive(host, drive_obj).get_power_mode()
            except Exception:
                power_mode = None

            # Create the Record
            record = SSDDriveRecord.from_drive(
                drive_obj,
                data=data,
                hostname=host.hostname,
                vendor_id=NVMeUtils.get_vendor_id(host, drive_obj),
                id_ctrl=data["id_ctrl"],
                id_ns=data["id_ns"],
                power_mode=power_mode,
            )
            drives.append(record)

        return drives
