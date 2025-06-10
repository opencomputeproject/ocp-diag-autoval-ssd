# pyre-unsafe

from autoval_ssd.tests.storage_hw_eng.libs.data_types import lsscsi_data as scsi

from autoval_ssd.tests.storage_hw_eng.libs.data_types.data_record.data_record import (
    datarec,
    item,
)

from .drive_record import DriveRecord


@datarec
class JBODDriveRecord(DriveRecord):
    """
    Represents a drive on a JBOD
    """

    jbod = item(
        data_type=str, keyword="jbod", docstr="The JBOD on which this drive is on."
    )

    slot = item(data_type=int, keyword="slot", docstr="The slot on the system.")

    addr = item(
        data_type=scsi.SCSIAddress,
        keyword="addr",
        docstr="The SCSI address for this JBOD Drive",
    )
