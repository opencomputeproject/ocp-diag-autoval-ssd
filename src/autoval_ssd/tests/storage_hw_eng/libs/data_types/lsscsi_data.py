# pyre-unsafe
"""
.. fb:display_title::
  lsscsi data

This includes the Data Records for lsscsi output.
"""

import enum
import re
import typing as t

from .data_record.data_record import datarec, DictConstructable, item
from .data_record.data_record_enum import enum_from_serial, enum_serial
from .data_size import DataSize


@enum_serial(by_name=False, default="UNKNOWN")
class SCSIPeriferalDeviceType(enum.Enum):
    """
    Enum for SCSI device types
    """

    DIRECT_ACCESS = ("disk", "Disk", 0x00)
    SEQUENTIAL_ACCESS = ("tape", 0x01)
    PRINTER = ("printer", 0x02)
    PROCESSOR = ("process", 0x03)
    WRITE_ONCE = ("worm", 0x04)
    CD_DVD = ("cd/dvd", 0x05)
    SCANNER = ("scanner", 0x06)
    OPTICAL = ("optical", 0x07)
    MEDIUM_CHANGER = ("mediumx", 0x08)
    COMMUNICATIONS = ("comms", 0x09)
    GRAPHIC_ARTS = ("gfx", "(0xa)", "(0xb)", 0x0A, 0x0B)
    STORAGE_ARRAY_CONTROLLER = ("storage", 0x0C)
    ENCLOSURE = ("enclosu", "EnclServ", 0x0D)
    SIMPLIFIED_DIRECT_ACCESS = ("sim dsk", 0x0E)
    OPTICAL_CARD = ("opti rd", 0x0F)
    BRIDGING_EXPANDERS = ("bridge", 0x10)
    OBJECT_BASED_STORAGE = ("osd", 0x11)
    AUTOMATION_DRIVE_INTERFACE = ("adi", 0x12)
    SECURITY_MANAGER = ("sec man", 0x13)
    HOST_MANAGED_ZONED_DEVICE = ("dbc", 0x14)
    REDUCED_MMC = ("rmmc", "(0x15)", 0x15)
    RESERVED = (
        "resv",
        "(0x16)",
        "(0x17)",
        "(0x18)",
        "(0x19)",
        "(0x1a)",
        "(0x1b)",
        "(0x1c)",
        "(0x1d)",
        0x16,
        0x17,
        0x18,
        0x19,
        0x1A,
        0x1B,
        0x1C,
        0x1D,
    )
    WELL_KNOWN_LOGICAL_UNIT = ("wlun", 0x1E)
    UNKNOWN = ("no dev", 0x1F)


@datarec(frozen=True, eq=True)
class SCSIAddress(DictConstructable):
    """
    Represents a SCSI address
    """

    host = item(data_type=int, keyword="host", docstr="host ID")

    channel = item(data_type=int, keyword="channel", docstr="channel ID")

    target = item(data_type=int, keyword="target", docstr="target ID")

    lun = item(data_type=int, keyword="lun", docstr="LUN")

    def __init__(self, host=host, channel=channel, target=target, lun=lun):
        SCSIAddress.host = host
        SCSIAddress.channel = channel
        SCSIAddress.target = target
        SCSIAddress.lun = lun

    def __str__(self):
        return f"[{self.host}:{self.channel}:{self.target}:{self.lun}]"

    @classmethod
    def from_str(cls, s: str):
        p = re.match(r"\[(\d+):(\d+):(\d+):(\d+)\]", s)
        if p:
            host, channel, target, lun = p.group(1), p.group(1), p.group(1), p.group(1)
            return cls(host=host, channel=channel, target=target, lun=lun)
        return None


@datarec
class SCSIDevice(DictConstructable):
    """
    Represents a device in the output of lsscsi.
    """

    addr = item(
        data_type=SCSIAddress,
        keyword="address",
        docstr="The SCSI address of the device.",
    )

    vendor = item(data_type=str, keyword="vendor", docstr="The device vendor.")

    model = item(data_type=str, keyword="model", docstr="The device model.")

    device_type = item(
        data_type=SCSIPeriferalDeviceType,
        keyword="device_type",
        docstr="The device type.",
    )

    fw_revision = item(
        data_type=str, keyword="fw_rev", docstr="The device's firmware revision."
    )

    devname = item(
        data_type=str,
        keyword="devname",
        docstr="The device's device name ex. /dev/sdX.",
    )

    genname = item(
        data_type=str,
        keyword="genname",
        docstr="The device's generic name ex. /dev/sgX.",
    )

    size = item(
        data_type=t.Optional[DataSize], keyword="size", docstr="The device's size."
    )

    def __init__(
        self,
        addr=addr,
        vendor=vendor,
        model=model,
        device_type=device_type,
        fw_revision=fw_revision,
        devname=devname,
        genname=genname,
        size=size,
    ):
        SCSIDevice.addr = addr
        SCSIDevice.vendor = vendor
        SCSIDevice.model = model
        SCSIDevice.device_type = device_type
        SCSIDevice.fw_revision = fw_revision
        SCSIDevice.devname = devname
        SCSIDevice.genname = (genname,)
        SCSIDevice.size = size

    @staticmethod
    def create_devname_mapping(
        devices: t.List["SCSIDevice"],
    ) -> t.Dict[str, "SCSIDevice"]:
        """
        Given a list of SCSIDevices, map devname to the device.
        """

        return {dev.devname: dev for dev in devices}

    @staticmethod
    def filter_lsscsi_output(
        devices: t.List["SCSIDevice"],
        host: t.Optional[int] = None,
        channel: t.Optional[int] = None,
        target: t.Optional[int] = None,
        lun: t.Optional[int] = None,
    ) -> t.List["SCSIDevice"]:
        """
        Filters the output of lsscsi for particular addresses.
        """

        def filter_function(x) -> bool:
            if host is not None and host != x.addr.host:
                return False
            if channel is not None and channel != x.addr.channel:
                return False
            if target is not None and target != x.addr.target:
                return False
            if lun is not None and lun != x.addr.lun:
                return False
            return True

        return [dev for dev in devices if filter_function(dev)]

    @classmethod
    def generate_from_lsscsi_output(cls, output: str) -> t.List["SCSIDevice"]:
        """
        Generates SCSI devices from lsscsi output.
        ex. lsscsi, lsscsi -g, lsscsi -g -s, lsscsi -s
        """
        devices = []

        lines = [lines.strip() for lines in output.split("\n")]
        for line in lines:
            columns = line.split()
            device = []

            if len(columns) < 8 or len(columns) > 9:
                continue

            if len(columns) == 8:
                device = cls(
                    addr=SCSIAddress.from_str(columns[0]),
                    device_type=enum_from_serial(columns[1], SCSIPeriferalDeviceType),
                    vendor=columns[2],
                    model=columns[3],
                    fw_revision=columns[4],
                    devname=columns[5] if columns[5] != "-" else "",
                    genname=columns[6] if columns[6] != "-" else "",
                    size=DataSize(columns[7]) if columns[7] != "-" else None,
                )

            if len(columns) == 9:
                device = cls(
                    addr=SCSIAddress.from_str(columns[0]),
                    device_type=enum_from_serial(columns[1], SCSIPeriferalDeviceType),
                    vendor=columns[2],
                    model=f"{columns[3]} {columns[4]}",
                    fw_revision=columns[5],
                    devname=columns[6] if columns[6] != "-" else "",
                    genname=columns[7] if columns[7] != "-" else "",
                    size=DataSize(columns[8]) if columns[8] != "-" else None,
                )

            devices.append(device)

        return devices
