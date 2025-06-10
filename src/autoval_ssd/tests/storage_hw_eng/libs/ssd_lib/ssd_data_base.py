# pyre-unsafe
import typing as t

from autoval_ssd.tests.storage_hw_eng.libs.component_common_lib.component_data_base import (
    ComponentInputBase,
    ComponentOutputBase,
    ComponentTestEntry,
)
from autoval_ssd.tests.storage_hw_eng.libs.data_types.data_record.data_record import (
    datarec,
    item,
)
from autoval_ssd.tests.storage_hw_eng.libs.data_types.drive_record import SSDDriveRecord


@datarec
class SSDTestInputBase(ComponentInputBase):
    pass


@datarec
class SSDTestPerDriveEntry(ComponentTestEntry):
    drive = item(
        data_type=t.Optional[SSDDriveRecord],
        keyword="drive",
        default=None,
        docstr="Drive information.",
    )

    init_smartctl_smartlog = item(
        data_type=t.Optional[dict],
        keyword="init_smartctl_smartlog",
        default="",
        docstr="Initial Smartlog",
    )

    final_smartctl_smartlog = item(
        data_type=t.Optional[dict],
        keyword="final_smartctl_smartlog",
        default="",
        docstr="Final Smartlog",
    )

    init_nvme_smartlog = item(
        data_type=t.Optional[dict],
        keyword="init_nvme_smartlog",
        factory=dict,
        docstr="Initial Smartlog",
    )

    final_nvme_smartlog = item(
        data_type=t.Optional[dict],
        keyword="final_nvme_smartlog",
        factory=dict,
        docstr="Final Smartlog",
    )


@datarec
class SSDTestOutputBase(ComponentOutputBase):
    pass
