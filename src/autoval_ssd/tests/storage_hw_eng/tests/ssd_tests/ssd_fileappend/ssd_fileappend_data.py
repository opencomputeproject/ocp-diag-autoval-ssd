# pyre-unsafe
import typing as t

from autoval_ssd.tests.storage_hw_eng.libs.component_common_lib.component_data_base import (
    ComponentTestEntry,
)
from autoval_ssd.tests.storage_hw_eng.libs.data_types.data_record.data_record import (
    datarec,
    DictConstructable,
    item,
)
from autoval_ssd.tests.storage_hw_eng.libs.data_types.drive_record import SSDDriveRecord
from autoval_ssd.tests.storage_hw_eng.libs.ssd_lib.ssd_data_base import SSDTestInputBase


def str_list_converter(val):
    if isinstance(val, str):
        return [val]
    else:
        return val


@datarec
class SSDFileAppendInput(SSDTestInputBase):
    """
    Input to the SSD File Append Test
    """

    capacity = item(
        data_type=t.Optional[float],
        keyword="capacity",
        default=None,
        docstr="Capacity to run on for File Append .",
    )

    health_monitoring = item(
        data_type=t.Optional[bool],
        keyword="health_monitoring",
        default=None,
        docstr="Vendor specific health monitor tool execution.",
    )

    skip_drive_prep = item(
        data_type=t.Optional[bool],
        keyword="skip_drive_prep",
        default=None,
        docstr="Skip drive preperations.",
    )

    num_runs = item(
        data_type=t.Optional[int],
        keyword="num_runs",
        default=None,
        docstr="Number of runs.",
    )

    flash_config_logging = item(
        data_type=t.Optional[bool],
        keyword="flash_config_logging",
        default=None,
        docstr="Enable flash configuration logging.",
    )

    wr_cache = item(
        data_type=bool, default=True, keyword="wr_cache", docstr="Enable write cache."
    )

    timeout = item(
        data_type=int,
        keyword="timeout",
        default=24 * 60 * 60,
        docstr="Timeout for FileAppend.",
    )

    local_wl_suite_folder = item(
        data_type=t.Optional[str],
        default=None,
        keyword="local_wl_suite_folder",
        docstr="Folder with workload suites to transfer over to FileAppend.",
    )


@datarec
class SSDFileAppendDriveEntry(ComponentTestEntry):
    drive = item(
        data_type=t.Optional[SSDDriveRecord],
        keyword="drive",
        default=None,
        docstr="Drive information.",
    )


@datarec
class SSDFileAppendEntry(ComponentTestEntry):
    """
    SSD Workload Performance Test Entry
    """

    workload_name = item(
        data_type=str,
        keyword="workload_name",
        default="",
        docstr="Name of the workload.",
    )

    drive_entries = item(
        data_type=t.Dict[str, SSDFileAppendDriveEntry],
        keyword="drive_entries",
        factory=dict,
        docstr="Drive entries for this run.",
    )


@datarec
class SSDFileAppendOutput(DictConstructable):
    """
    Output to the FileAppend Test
    """

    entries = item(
        data_type=t.List[SSDFileAppendEntry],
        keyword="entries",
        factory=list,
        docstr="List of entries by workload.",
    )
