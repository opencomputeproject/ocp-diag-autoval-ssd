# pyre-unsafe
"""
.. fb:display_title::
  Drive Data Records

This includes the Data Records to represent drives
"""

import typing as t

import autoval_ssd.lib.utils.storage.drive as havoc_drive
from autoval_ssd.tests.storage_hw_eng.libs.data_types import data_size as data_size
from autoval_ssd.tests.storage_hw_eng.libs.data_types.data_record.data_record import (
    datarec,
    DictConstructable,
    item,
)


@datarec
class DriveRecord(DictConstructable):
    """
    Represents a drive in a system.
    """

    devname = item(
        data_type=str, keyword="devname", docstr="The device name -- ex. /dev/sdX"
    )

    drive_type = item(
        data_type=str,
        keyword="drive_type",
        docstr="The type of drive.",
    )

    interface = item(
        data_type=str,
        keyword="interface",
        docstr="The interface for this drive.",
    )

    capacity = item(
        data_type=t.Optional[data_size.DataSize],
        keyword="capacity",
        docstr="The capacity of the drive.",
    )

    manufacturer = item(
        data_type=t.Optional[str],
        keyword="manufacturer",
        docstr="The drive manufacturer.",
    )

    serial = item(
        data_type=t.Optional[str], keyword="serial", docstr="The drive serial."
    )

    model = item(data_type=t.Optional[str], keyword="model", docstr="The drive model.")

    write_cache = item(
        data_type=t.Optional[bool],
        keyword="wr_cache",
        docstr="If write cache is enabled/disabled.",
    )

    read_cache = item(
        data_type=t.Optional[bool],
        keyword="rd_cache",
        docstr="If read cache is enabled/disabled.",
    )

    fw_revision = item(
        data_type=t.Optional[str],
        keyword="fw_rev",
        docstr="The device's firmware revision.",
    )

    hostname = item(
        data_type=t.Optional[str],
        keyword="hostname",
        default=None,
        docstr="The hostname.",
    )

    drive_obj = item(
        data_type=t.Optional[havoc_drive.Drive],
        keyword="drive_obj",
        do_not_serialize=True,
        default=None,
        docstr="The Havoc Drive object.",
    )

    @classmethod
    def from_drive(cls, device: havoc_drive.Drive, data=None, **kwargs):
        """
        Create data record from drive.
        """

        if data is None:
            data = device.collect_data()

        def get_if_exists(data, key):
            if key in data:
                return data[key]
            else:
                return None

        def run_bool_if_hasattr(device, func, *args, **kwargs):
            if hasattr(device, func):
                return bool(getattr(device, func)(*args, **kwargs))
            return None

        defaults = {
            "devname": f"/dev/{device.block_name}",
            "drive_type": get_if_exists(data, "type"),
            "interface": get_if_exists(data, "interface"),
            "capacity": get_if_exists(data, "capacity"),
            "manufacturer": get_if_exists(data, "manufacturer"),
            "serial": get_if_exists(data, "serial_number"),
            "model": get_if_exists(data, "model"),
            "write_cache": run_bool_if_hasattr(device, "get_write_cache"),
            "read_cache": run_bool_if_hasattr(device, "get_read_lookahead"),
            "fw_revision": get_if_exists(data, "firmware"),
            "drive_obj": device,
        }

        defaults.update(kwargs)
        return cls(**defaults)
