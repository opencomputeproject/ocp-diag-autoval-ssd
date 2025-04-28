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

    def __init__(
        self,
        workload_configs=workload_configs,
        capacity=capacity,
        health_monitoring=health_monitoring,
        skip_drive_prep=skip_drive_prep,
        num_runs=num_runs,
        flash_config_logging=flash_config_logging,
        wr_cache=wr_cache,
        timeout=timeout,
        local_wl_suite_folder=local_wl_suite_folder,
    ):
        self.workload_configs = workload_configs
        self.capacity = capacity
        self.health_monitoring = health_monitoring
        self.skip_drive_prep = skip_drive_prep
        self.num_runs = num_runs
        self.flash_config_logging = flash_config_logging
        self.wr_cache = wr_cache
        self.timeout = timeout
        self.local_wl_suite_folder = local_wl_suite_folder


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
        keyword="fio_data",
        factory=dict,
        docstr="The fio data for this run.",
    )

    flash_config = item(
        data_type=t.Dict[str, t.Any],
        keyword="flash_config",
        factory=dict,
        docstr="The flash_config data for this run.",
    )

    summary_data = item(
        data_type=t.List[dict],
        keyword="summary_data",
        factory=list,
        docstr="The fio data for this run.",
    )

    drive_entries = item(
        data_type=t.Dict[str, t.Any],
        keyword="drive_entries",
        factory=dict,
        docstr="Drive entries for this run.",
    )

    success = item(
        data_type=t.Optional[bool],
        keyword="success",
        default=None,
        docstr="If success is True",
    )

    msgs = item(
        data_type=t.Optional[str],
        keyword="msgs",
        default=None,
        docstr="The msgs for this run.",
    )

    def __init__(
        self,
        workload_name=workload_name,
        synthflash_params=synthflash_params,
        fio_data=fio_data,
        flash_config=flash_config,
        summary_data=summary_data,
        drive_entries=drive_entries,
        success=success,
        msgs=msgs,
    ):
        self.workload_name = workload_name
        self.synthflash_params = synthflash_params
        self.fio_data = fio_data
        self.flash_config = flash_config
        self.summary_data = summary_data
        self.drive_entries = drive_entries
        self.success = success
        self.msgs = msgs


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

    def __init__(self, entries=entries):
        self.entries = entries
