# pyre-unsafe
import typing as t

import pandas as pd
from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_exceptions import CmdError, TestError
from autoval.lib.utils.decorators import retry
from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.storage.drive import DriveType
from autoval_ssd.lib.utils.storage.nvme.fdp_utils import FDPUtils
from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil

from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.storage.storage_device_factory import StorageDeviceFactory
from autoval_ssd.lib.utils.system_utils import SystemUtils
from autoval_ssd.tests.storage_hw_eng.libs.component_common_lib.component_test_base import (
    ComponentTestBase,
)
from autoval_ssd.tests.storage_hw_eng.libs.data_types.dmesg_record import Dmesg
from autoval_ssd.tests.storage_hw_eng.libs.data_types.drive_record import SSDDriveRecord
from autoval_ssd.tests.storage_hw_eng.libs.ext_test_base.tasks import TestTask

from .ssd_data_base import SSDTestInputBase, SSDTestOutputBase
from .ssd_dmesg_check import DmesgCheckSSD

# { TB Capacity : Power State } mapping for performance testing
DRIVE_CAPACITY_POWER_STATES = {
    1: 8,
    2: 7,
    4: 6,
    8: 5,
    16: 2,
}


class SSDTestBase(ComponentTestBase):
    """
    The SSD Test base.
    """

    def __init__(self, inputT=SSDTestInputBase, outputT=SSDTestOutputBase, **kwargs):
        if not issubclass(inputT, SSDTestInputBase):
            TestError(
                f"Type {inputT} is not a subclass of {SSDTestInputBase}!"
                + " The SSD Test base requires that the input type be a subclass."
            )
        if not issubclass(outputT, SSDTestOutputBase):
            TestError(
                f"Type {outputT} is not a subclass of {SSDTestOutputBase}!"
                + " The SSD Test base requires that the output type be a subclass."
            )
        super().__init__(inputT=inputT, outputT=outputT, **kwargs)
        self.test_results = []
        self.pre_run_smartlog_data = None
        self.cleanup_test_drives = []
        self.test_specific_drives = []
        self.run_entry = []
        self.nvme_id_ctrl_filter: str = self.test_control.get(
            "nvme_id_ctrl_filter", "True"
        )

        self.collect_smart_log = self.test_control.get("collect_smart_log", True)
        self.collect_drive_data = self.test_control.get("collect_drive_data", True)
        self.drive_interface = self.test_control.get("drive_interface", None)
        self.drive_type = self.test_control.get("drive_type", None)
        self.disable_tools_upgrade = self.test_control.get(
            "disable_tools_upgrade", None
        )
        self.lbaf_combinations = self.test_control.get("lbaf_combinations", [])
        self.dix_ns_resize = self.test_control.get("dix_ns_resize", False)
        self.lba_format = self.test_control.get("lba_format", None)
        self.hypernode: bool = self.test_control.get("hypernode", False)
        self.fdp_setup = self.test_control.get("fdp_setup", None)
        self.fdp_enabled = False
        self.nvme_version = self.test_control.get(
            "nvme_version", "nvme-cli-1.11.2-1.fb20"
        )
        self.only_boot_drive = self.test_control.get("only_boot_drive", False)

    def setup(self, **kwargs):
        """
        Setup for the HDD Tests.
        """
        super().setup(**kwargs)
        SystemUtils.install_rpms(self.host, [self.nvme_version], force_install=True)

        if self.only_boot_drive:
            boot_drive_str = DiskUtils.get_boot_drive(self.host)
            self.log_info(f"Only testing boot drive: {boot_drive_str}")
            drive_list = [boot_drive_str]
            self.data_ssds = self.get_all_ssds(self.collect_drive_data, no_boot=False)

        else:
            # Get all SSDs
            self.data_ssds = self.get_all_ssds(self.collect_drive_data, no_boot=True)
            if len(self.data_ssds) == 0:
                self.log_info("Found No Testable NVMe Drives.")
                return

            self.log_info(
                "Found {} unique devices to test on.".format(
                    len(self.data_ssds.devname.unique()),
                )
            )

            drive_str = ", ".join(list(self.data_ssds.devname))
            self.log_info(f"Excutable drives: {drive_str}")

            # Set all wr cache correctly
            self.set_multi_ssd_wr_cache(
                devnames=list(self.data_ssds.devname), enable=self.input_params.wr_cache
            )
            drive_list = [
                drive_name[5:] for drive_name in self.data_ssds.devname.tolist()
            ]

        self.test_drives = StorageDeviceFactory(self.host, drive_list, None).create()
        self.nvme_id_ctrls = NvmeResizeUtil.get_nvme_ctrls(
            self.host, self.test_drives, self.nvme_id_ctrl_filter
        )
        tnvmcap = self.nvme_id_ctrls[str(self.test_drives[0])[:-2]]["tnvmcap"]
        _, TB_capacity = NvmeResizeUtil.get_reported_capacity(tnvmcap)
        self.drive_capacity_power_state = DRIVE_CAPACITY_POWER_STATES[TB_capacity]
        self.boot_drive = self.test_drives[0] if self.only_boot_drive else None

    def execute(self):
        """
        Execute function for the SSD Test Base.
        """

    def cleanup(self, **kwargs):
        """
        This is the cleanup function. This will be called after the execute function.
        Note that this will be called regardless of pass condition on execute.
        """

        # Call super with if are any kwargs
        if self._debug:
            super().cleanup(config_check=False)
        else:
            super().cleanup(**kwargs)

    def check_dmesg_errors(self, dmesg: Dmesg) -> t.List[t.Tuple]:
        """
        Checks the dmesg for a particular set of errors.
        """
        checker = DmesgCheckSSD()
        return checker.check(dmesg, ts_only=False)

    @retry(3, 5)
    def get_nvme_smartlog(
        self,
        *,
        drive: SSDDriveRecord,
        check_input_param: bool = False,
    ) -> t.Optional[t.Dict]:
        """
        Gets smartlog for a drive from a host.

        Params:
        drive (SSDDriveRecord):
            The drive to get the NVME smartlogs from.

        Return:
        The Smartlog output.
        """
        if drive.drive_obj is None or drive.drive_type is not DriveType.SSD:
            return {}
        return drive.drive_obj.get_smart_log()

    def get_all_ssds(
        self,
        collect_drive_data: bool,
        host: t.Optional[Host] = None,
        no_boot: bool = True,
    ) -> pd.DataFrame:
        """
        Gets all of the SSDs on a hosts.
        """

        host = self._default_host_if_none(host)

        self.log_info("Getting all SSDs.")
        drives = SSDDriveRecord.get_mounted_SSD_drives(
            host,
            collect_drive_data,
            logger=self.log_info,
        )
        bootDrive = DiskUtils.get_boot_drive(host)  # new line
        if bootDrive == "":  #
            bootDrive = "No boot drives detected"  #
            self.log_info("No boot drives detected")  #
        self.log_info("Boot Drives are:")
        self.log_info(bootDrive)
        if no_boot:
            drives = [drive for drive in drives if bootDrive not in drive.devname]

        records = [drive.to_dataframe_record(add_self="drive_obj") for drive in drives]
        df = pd.DataFrame(records)

        return df

    def check_if_bootdrive(self, devname: str, host: t.Optional[Host] = None) -> bool:
        """
        Checks if a drive is the bootdrive via looking for /boot
        """
        host = self._default_host_if_none(host)
        num = host.run(f"lsblk {devname} | grep /boot | wc -l")
        return int(num) > 0

    def set_multi_ssd_wr_cache(
        self,
        *,
        devnames: t.List[str],
        host: t.Optional[Host] = None,
        enable: bool = True,
    ):
        """
        Sets the write cache of multiple ssds. Multi-threaded.
        """
        self.log_info(f"Setting multiple write caches on SSDs to {enable}.")
        return self.operate_on_devnames(
            task=TestTask(func=self.set_ssd_wr_cache, kwargs={"enable": enable}),
            host=host,
            devnames=devnames,
        )

    def set_ssd_wr_cache(
        self, *, devname: str, host: t.Optional[Host] = None, enable: bool = True
    ):
        """
        Sets the write cache on a ssd by devicename and host.
        """
        host = self._default_host_if_none(host)
        devname = self.format_devname(devname, to_full_path=False)

        if enable:
            self.log_info(
                f"Attempting to enable write cache on {devname} on host {host.hostname}"
            )
            NVMeUtils.enable_write_cache(host, devname)
            return NVMeUtils.get_write_cache(host, devname) == 1
        else:
            self.log_info(
                f"Attempting to disable write cache on {devname} on host {host.hostname}"
            )
            NVMeUtils.disable_write_cache(host, devname)
            return NVMeUtils.get_write_cache(host, devname) == 0

    def entry_get_nvme_log(self, drive: SSDDriveRecord, msgs: t.List[str]):
        if drive.drive_obj is not None:
            try:
                return drive.drive_obj.get_smart_log()
            except CmdError as e:
                msg = f"Failed to get final nvme smartlogs for {drive.devname} on {drive.hostname} - {type(e)}:{e}."

        else:
            msg = f"Failed to get final nvme smartlogs for {drive.devname} on {drive.hostname} - drive obj is None."

        self.log_info(msg)
        msgs.append(msg)
        return None

    def fdp_single_namespace_setup(self) -> None:
        """
        Set up a single namespace with 4k LBA format and FDP enabled on the test drives.

        Raises:
            TestError: If FDP support validation fails.
        """

        FDPUtils.validate_fdp_support(self.host, self.nvme_id_ctrls)
        FDPUtils.fdp_setup(self.host, self.nvme_id_ctrls)
        self.log_info("FDP setup completed\n NVME LIST\n" + self.host.run("nvme list"))
        self.fdp_enabled = True
        self.performed_resize = True
