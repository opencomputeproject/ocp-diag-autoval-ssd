# pyre-unsafe
import typing as t

from autoval_ssd.tests.storage_hw_eng.libs.component_common_lib.component_data_base import (
    ComponentTestEntry,
)
from autoval_ssd.tests.storage_hw_eng.libs.data_types.data_record.data_record import (
    datarec,
    item,
)
from autoval_ssd.tests.storage_hw_eng.libs.data_types.fb_synthflash_data import (
    FBSynthFlashInput,
)
from autoval_ssd.tests.storage_hw_eng.libs.data_types.fio_data import FioOutput
from autoval_ssd.tests.storage_hw_eng.libs.ssd_lib.ssd_data_base import (
    SSDTestInputBase,
    SSDTestOutputBase,
    SSDTestPerDriveEntry,
)


def str_list_converter(val):
    if isinstance(val, str):
        return [val]
    else:
        return val


@datarec
class SSDSynthFlashInput(SSDTestInputBase):
    """
    Input to the SSD SynthFlash Test
    """

    # devices = item(
    #     data_type=t.List[str],
    #     keyword="devices",
    #     converter=str_list_converter,
    #     docstr="The device(s) to run on.",
    # )

    workload_configs = item(
        data_type=t.List[str],
        keyword="workload_configs",
        converter=str_list_converter,
        docstr="List of workload suites to run.",
    )

    capacity = item(
        data_type=t.Optional[float],
        keyword="capacity",
        default=None,
        docstr="Capacity to run on for SynthFlash.",
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
        docstr="Timeout for SynthFlash.",
    )

    local_wl_suite_folder = item(
        data_type=t.Optional[str],
        default=None,
        keyword="local_wl_suite_folder",
        docstr="Folder with workload suites to transfer over to SynthFlash.",
    )


@datarec
class SSDSynthFlashDriveEntry(SSDTestPerDriveEntry):
    pass


@datarec
class SSDSynthFlashEntry(ComponentTestEntry):
    """
    SSD Workload Performance Test Entry
    """

    workload_name = item(
        data_type=str,
        keyword="workload_name",
        default="",
        docstr="Name of the workload.",
    )

    synthflash_params = item(
        data_type=t.Optional[FBSynthFlashInput],
        keyword="fio_params",
        default=None,
        docstr="The fio parameters for this run.",
    )

    fio_data = item(
        data_type=t.Dict[str, FioOutput],
        keyword="synthflash_data",
        factory=dict,
        docstr="The fio data for this run.",
    )

    flash_config = item(
        data_type=t.List[t.List[str]],
        keyword="synthflash_data",
        factory=list,
        docstr="The fio data for this run.",
    )

    summary_data = item(
        data_type=t.List[t.List[str]],
        keyword="synthflash_data",
        factory=list,
        docstr="The fio data for this run.",
    )

    drive_entries = item(
        data_type=t.Dict[str, SSDSynthFlashDriveEntry],
        keyword="drive_entries",
        factory=dict,
        docstr="Drive entries for this run.",
    )


@datarec
class SSDSynthFlashOutput(SSDTestOutputBase):
    """
    Output to the Synthflash Test
    """

    entries = item(
        data_type=t.List[SSDSynthFlashEntry],
        keyword="entries",
        factory=list,
        docstr="List of entries by workload.",
    )
