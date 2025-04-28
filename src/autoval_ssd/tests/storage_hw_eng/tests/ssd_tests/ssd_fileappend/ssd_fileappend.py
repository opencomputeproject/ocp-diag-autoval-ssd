# pyre-strict
import os
import subprocess
import threading
import time
from typing import Any, Dict, Iterable, List, Optional

from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_exceptions import CmdError, TestError
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalLog
from autoval.lib.utils.file_actions import FileActions
from autoval_ssd.lib.utils.storage.drive import Drive
from autoval_ssd.lib.utils.storage.nvme.fdp_utils import FDPUtils
from autoval_ssd.lib.utils.storage.nvme.nvme_resize_utils import NvmeResizeUtil
from autoval_ssd.lib.utils.storage.storage_device_factory import StorageDeviceFactory
from autoval_ssd.tests.storage_hw_eng.libs.component_common_lib.component_test_base import (
    ComponentTestBase,
)
from autoval_ssd.tests.storage_hw_eng.libs.ssd_lib.ssd_test_base import SSDTestBase
from autoval_ssd.tests.storage_hw_eng.tests.ssd_tests.ssd_fileappend.ssd_fileappend_data import (
    SSDFileAppendDriveEntry,
    SSDFileAppendInput,
    SSDFileAppendOutput,
)


class SSDFileAppend(SSDTestBase):
    """
    SSD FileAppend Test.
    """

    performed_resize = False
    # globalself._host

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(
            *args, inputT=SSDFileAppendInput, outputT=SSDFileAppendOutput, **kwargs
        )
        self.workload_folder_path: Optional[str] = self.test_control.get(
            "workload_folder_path", None
        )
        self.workload_file_name: Optional[str] = self.test_control.get(
            "workload_file_name", None
        )
        self.update_JSON_config: bool = self.test_control.get(
            "update_JSON_config", False
        )
        self.pass_fail_verify: bool = self.test_control.get("pass_fail_verify", False)
        self.cycle: int = self.test_control.get("cycle_count", 1)
        self.dix_ns_resize: bool = self.test_control.get("dix_ns_resize", False)
        self.outliers: Dict[str, Any] = {}
        self.fileappend_data: Dict[str, int] = {}
        self._host: Host = self.host if self.host is not None else Host

    def setup(self, *args: Any, **kwargs: Any) -> None:
        super().setup(init_bg_polling=False)
        self._host = self.host if self.host is not None else Host
        # Create Remote Temp Directory
        success, temp_dir = self.create_temp_directory(self._host)

        self.validate_condition(
            success, f"Create temp directory {temp_dir} on {self._host.hostname}."
        )
        self.work_dir = temp_dir

        try:
            os.makedirs(f"{self.resultsdir}/results")
        except FileExistsError:
            # directory already exists
            pass
        except Exception as e:
            raise TestError(
                f"Failed to create local results directory -- {type(e)}:{e}"
            )

    def execute(self) -> None:
        """
        This function executes the main test logic for the SSD Fio Synthetic Workload test.

        It first gets all the NVMe drives on the system and checks if there are any testable drives.
        If no testable drives are found, it logs a message and returns.

        If testable drives are found, it sets the write cache correctly for all devices and initializes the test drives using the StorageDeviceFactory class.

        It then overrides the kernel parameters and deletes any existing RAID arrays.

        If the 'perform_resize' parameter is set to True in the test control, it over-provisions the drives.
        Otherwise, if the 'performed_resize' attribute is set to True, it also resizes the drives to their full capacity.
        If self.dix_ns_resize is True, it will perform a DIX namespace resize instead of the normal NVMe Resize.

        It also sets the power state on the devices if specified in the test control.

        Finally, it calls the filedelete method to delete any files that were created during the test.
        """
        super().execute()
        self.test_specific_drives = ComponentTestBase.drives_executable(
            self.test_drives, self.test_control
        )

        self.cleanup_test_drives = list(
            set(self.cleanup_test_drives + self.test_specific_drives)
        )
        self.log_info("================ Running FileAppend =======================")

        # Overriding the Kernal Parameters
        ComponentTestBase.override_kernel_parameters(
            self._host,
            self.test_specific_drives,
            preferred_scheduler=self.test_control.get("preferred_scheduler", None),
            io_timeout=self.test_control.get("io_timeout", None),
            discard_max_bytes=self.test_control.get("discard_max_bytes", None),
            max_sectors_kb=self.test_control.get("max_sectors_kb", None),
        )
        self.log_info("Deleting the RAID array/s if exists")
        self.delete_raid_array()

        self.perform_resize = self.test_control.get("perform_resize", False)
        self.nvme_id_ctrl_filter = self.test_control.get("nvme_id_ctrl_filter", "True")
        self.nvme_id_ctrls = NvmeResizeUtil.get_nvme_ctrls(
            self.host, self.test_specific_drives, nvme_id_ctrl_filter="True"
        )

        if self.dix_ns_resize:
            for dix_drive_list in self.dix_ns_resize_setup():
                self.set_power_state(dix_drive_list)
                self.initialize_drives(dix_drive_list)
                self.filedelete(dix_drive_list)

        elif self.fdp_setup:
            self.fdp_single_namespace_setup()

        elif self.perform_resize:
            self.over_provisioning_setup()

        elif self.performed_resize:
            self.resize_full_capacity()

        if not self.dix_ns_resize:
            self.set_power_state()
            self.initialize_drives()
            self.filedelete()

    def resize_full_capacity(self) -> None:
        """
        Resize drives to full capacity, setting OP to default.
        """
        self.log_info("+++++++++++ Resizing the drives to Full Capacity  ++++++++++ ")
        self.performed_resize = False
        self.sweep_param_key: "NvmeResizeUtil.SweepParamKeyEnum" = (
            NvmeResizeUtil.SweepParamKeyEnum["overprovisioning"]
        )
        self.sweep_param_unit: "NvmeResizeUtil.SweepParamUnitEnum" = (
            NvmeResizeUtil.SweepParamUnitEnum["percent"]
        )
        self.sweep_param_value = NvmeResizeUtil.DEFAULT_OP_PERCENT
        NvmeResizeUtil.perform_resize(
            self._host,
            self.test_specific_drives,
            sweep_param_key=self.sweep_param_key,
            sweep_param_unit=self.sweep_param_unit,
            sweep_param_value=self.sweep_param_value,
            nvme_id_ctrl_filter=self.nvme_id_ctrl_filter,
            cycle=self.cycle,
        )

    def over_provisioning_setup(self) -> None:
        """
        Configures the drives for over-provisioning by setting the sweep
        parameters (key, unit, and value) from the test control. Then
        performs resize operation on the drives to apply the over-provisioning settings.
        """
        self.log_info("+++++++++++ Over-provisioning the drives ++++++++++ ")
        self.performed_resize = True

        # Parse test_control json inputs
        try:
            self.sweep_param_key: "NvmeResizeUtil.SweepParamKeyEnum" = (
                NvmeResizeUtil.SweepParamKeyEnum[
                    self.test_control.get("sweep_param_key", None)
                ]
            )
            self.sweep_param_unit: "NvmeResizeUtil.SweepParamUnitEnum" = (
                NvmeResizeUtil.SweepParamUnitEnum[
                    self.test_control.get("sweep_param_unit", None)
                ]
            )
        except KeyError as e:
            raise TestError(f"Invalid/Missing sweep param in test_control: {str(e)}")
        self.sweep_param_value = self.test_control.get("sweep_param_value", "")

        NvmeResizeUtil.perform_resize(
            self._host,
            self.test_specific_drives,
            sweep_param_key=self.sweep_param_key,
            sweep_param_unit=self.sweep_param_unit,
            sweep_param_value=self.sweep_param_value,
            nvme_id_ctrl_filter=self.nvme_id_ctrl_filter,
            cycle=self.cycle,
        )

    def dix_ns_resize_setup(self) -> Iterable[List[Drive]]:
        """
        Set up the DIX namespace resize process for the test drives.

        This function configures the drives for DIX namespace resizing by setting the
        sweep parameters (key, unit, and value) and iterates over the LBA format combinations
        to perform the resize operation on the drives.

        Yields:
            It uses a generator to yield the test drives after each resize cycle,
            allowing for sequential processing of each configuration.
        """
        self.sweep_param_key: "NvmeResizeUtil.SweepParamKeyEnum" = (
            NvmeResizeUtil.SweepParamKeyEnum["overprovisioning"]
        )
        self.sweep_param_unit: "NvmeResizeUtil.SweepParamUnitEnum" = (
            NvmeResizeUtil.SweepParamUnitEnum["percent"]
        )
        self.sweep_param_value = 75
        self.performed_resize = True
        lbaf_to_flbas_map = (
            NvmeResizeUtil.validate_drives_support_dix_resize_lba_formats(
                self.host, self.test_specific_drives
            )
        )
        self.log_info(f"lbaf to flbas map: {lbaf_to_flbas_map}")
        self.lbaf_combinations = self.test_control.get("lbaf_combinations", [])
        if self.lbaf_combinations == []:
            self.lbaf_combinations = [
                ["4096+64", "4096+64"],
                ["4096+64", "512"],
                ["4096+64", "4096"],
            ]
        dix_test_drives = self.test_specific_drives

        for resize_cycle, combo in enumerate(self.lbaf_combinations):
            self.log_info(
                f"Starting resize cycle {resize_cycle} with combination {combo}"
            )

            NvmeResizeUtil.perform_resize(
                self.host,
                dix_test_drives,
                sweep_param_key=self.sweep_param_key,
                sweep_param_unit=self.sweep_param_unit,
                sweep_param_value=self.sweep_param_value,
                cycle=self.cycle,
                combination=combo,
                lbaf_to_flbas_map=lbaf_to_flbas_map,
                use_existing_ns=(resize_cycle != 0),
            )
            time.sleep(5)

            self.data_ssds = self.get_all_ssds(self.collect_drive_data, no_boot=True)
            dix_drives_list = [
                drive_name[5:] for drive_name in self.data_ssds.devname.tolist()
            ]
            dix_test_drives = StorageDeviceFactory(
                self.host, dix_drives_list, None
            ).create()

            dix_test_drives = [
                drive
                for drive in dix_test_drives
                if any(
                    drive.block_name.startswith(test_drive.block_name[:-1])
                    for test_drive in self.test_specific_drives
                )
            ]

            self.log_info(f"test drives {dix_test_drives}")
            yield dix_test_drives

    def initialize_drives(self, drives: Optional[List[Drive]] = None) -> None:
        """
        Initialize and prepare specific drives for testing by setting up drive objects and entries

        Args:
            drives: A list of drives to set the power state for. Defaults to None.
        """
        if drives is None:
            drives = self.test_specific_drives

        for drive in drives:
            devname = "/dev/%s" % str(drive.block_name)
            entries = {devname: SSDFileAppendDriveEntry()}
            entry = entries[devname]

            # Get the drive object
            entry.drive = self.entry_get_drive(
                self._host, devname, self.data_ssds, msgs=entry.msgs
            )
            if entry.drive is None:
                entry.success = False
                return

    def set_power_state(self, drives: Optional[List[Drive]] = None) -> None:
        """
        Set power state on drives.

        Args:
            drives: A list of drives to set the power state for. Defaults to None.
        """
        if drives is None:
            drives = self.test_specific_drives
        if self.test_control.get("set_power_state", False):
            power_state = self.test_control.get("power_state", "")
            if not power_state:
                power_state = self.drive_capacity_power_state
            ComponentTestBase.power_state(
                self._host,
                drives,
                power_state_set_key=power_state,
            )

    def filedelete(self, drives: Optional[List[Drive]] = None) -> None:
        """
        This function will delete all the files present in the workdir

        Args:
            drives: A list of drives to delete the files from. Defaults to None.
        """
        if drives is None:
            drives = self.test_specific_drives
        self.log_info("Starting FileAppend Tests")
        time.sleep(5)
        for drive in drives:
            self.umount(drives)
            mount_path = "/data/fileappend/"
            AutovalLog.log_info("Creating Mountpath directory %s" % mount_path)
            if not FileActions.exists(mount_path, host=self._host):
                FileActions.mkdirs(mount_path, host=self._host)
            self._host.run(f"mkfs.xfs -f -K -i size=2048 /dev/{drive}")
            self._host.run(
                f"/bin/mount -o noatime,nodiratime,discard /dev/{drive} /data/fileappend"
            )
            for size_mb in self.test_control.get("file_sizes_mb", []):
                file_name = f"/data/fileappend/tfile_{size_mb}"
                self._host.run(f"touch {file_name}")
                subprocess.run(
                    [
                        "dd",
                        "if=/dev/zero",
                        f"of={file_name}",
                        "oflag=direct",
                        "bs=1M",
                        f"count={size_mb}",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                AutovalLog.log_info(f"Deleting {size_mb} MB Files on {drive}...")

                self._host.run(
                    f'echo "Deleting {size_mb} MB Files on {drive}..." >> {self.work_dir}/fa_results.log'
                )
                # Create a thread to run fileappend() in parallel
                thread_fileappend = threading.Thread(
                    target=self.fileappend,
                    args=(
                        size_mb,
                        self._host,
                    ),
                )
                thread_fileappend.start()
                time.sleep(1)  # Small delay for the python script to start
                subprocess.run(["rm", "-f", f"/data/fileappend/tfile_{size_mb}*"])
                time.sleep(15)
                self._host.run("killall python3 2> /dev/null")

                outliers_raw_data = self._host.run(
                    "cat /data/fileappend/result.txt"
                ).split("\n")
                # Append outliers_raw_data to fa_results.log
                for line in outliers_raw_data:
                    self._host.run(f'echo "{line}" >> {self.work_dir}/fa_results.log')

                self.fileappend_data[f"{drive}_{size_mb}MB file outliers count"] = sum(
                    "io stall time" in i for i in outliers_raw_data
                )
                outliers_count = self.fileappend_data[
                    f"{drive}_{size_mb}MB file outliers count"
                ]
                check = True if outliers_count == 0 else False
                if outliers_count > 0:
                    self.outliers[f"{drive}_{size_mb}MB file outliers"] = {
                        i: j
                        for i, j in enumerate(outliers_raw_data, start=1)
                        if "io stall" in j
                    }
                self.validate_condition(
                    condition=check,
                    msg=f"{outliers_count} File Append Outliers are found",
                )
                self.umount(drives)

        self.output.entries.append(self.fileappend_data)

    def fileappend(self, size_mb: int, host: Host) -> None:
        filename = "/data/fileappend/test.out"
        py_file = "/data/fileappend/test.py"
        self._host.run(f"touch {filename}")
        self._host.run(f"touch {py_file}")
        py_script = r"""
#!/usr/bin/python

import os, time
import sys

filename = '/data/fileappend/test.out'
try:
    f = open(filename, 'w')
except IOError:
    print('cannot wite to %s' % filename)
    sys.exit(1)

results_file = open('/data/fileappend/result.txt', 'w')
while True:
    s = time.time()
    f.write('x' * 500)
    f.flush()
    os.fsync(f.fileno())  # Use fileno() to get the file descriptor
    e = time.time()
    d = e - s
    if d > 0.01:
        print('io stall time = %s seconds, %s' % (d, time.ctime()))
        print('io stall time = %s seconds, %s' % (d, time.ctime()), file=results_file, end='\n')
    time.sleep(0.001)
        """
        # Write a python script to the file
        self._host.run(f"""echo "{py_script}" >> {py_file}""")

        try:
            # print("Python script is Working ")
            self._host.run(f"python3 {py_file}")
        except CmdError:
            return
        except IOError:
            print("cannot write to %s" % filename)
            return

    def umount(self, drives: Optional[List[Drive]] = None) -> None:
        """
        This function will unmount the mounted drives.

        Args:
            drives: A list of drives to unmount. Defaults to None.
        """
        if drives is None:
            drives = self.test_specific_drives
        for drive in drives:
            try:
                self._host.run(f"umount /dev/{drive}")
            except CmdError:
                pass

    def cleanup(self, **kwargs: Any) -> None:
        """
        This function performs the cleanup process for the SSD Fio Synthetic Workload test.
        It first restores any saved workloads that were modified during the test.
        It then deletes any RAIDed volumes that were created during the test.
        If the 'performed_resize' attribute is set to True, it also resizes the drives to their full capacity.
        Finally, it unmounts any mounted file systems and calls the parent class's cleanup method.

        """

        self.log_info("================ Clean Up Process=======================")
        if hasattr(self, "saved_old_wl"):
            self._host = self.host
            self.log_info(
                f"Restoring workloads from {self.saved_old_wl} on {self._host.hostname}"
            )
            # First remove current folder, then restore the original folder.
            self._host.run(f"rm -rf {self.SSDCachebenchTest.WL_SUITES}")
            self._host.run(
                f"cp -rf {self.saved_old_wl} {self.SSDCachebenchTest.WL_SUITES}"
            )
            self.log_info(f"Removing {self.saved_old_wl} on {self._host.hostname}")
            self._host.run(f"rm -rf {self.saved_old_wl}")

        self.log_info("++++++ Deleting the RAIDed Volumes +++++++")
        self.delete_raid_array()

        if self.performed_resize:
            self.log_info(
                "+++++++++++ Resizing the drives to Full Capacity  ++++++++++ "
            )
            self.sweep_param_key: "NvmeResizeUtil.SweepParamKeyEnum" = (
                NvmeResizeUtil.SweepParamKeyEnum["overprovisioning"]
            )
            self.sweep_param_unit: "NvmeResizeUtil.SweepParamUnitEnum" = (
                NvmeResizeUtil.SweepParamUnitEnum["percent"]
            )
            self.sweep_param_value = NvmeResizeUtil.DEFAULT_OP_PERCENT
            if self.fdp_enabled:
                FDPUtils.fdp_cleanup(self.host, self.nvme_id_ctrls)
            ns_validate_queue = []
            for device in self.nvme_id_ctrls:
                ns_validate_queue.append(
                    AutovalThread.start_autoval_thread(
                        NvmeResizeUtil.ns_resize,
                        self.host,
                        self.nvme_id_ctrls,
                        self.sweep_param_unit,
                        self.sweep_param_key,
                        device,
                        self.sweep_param_value,
                    )
                )
                if ns_validate_queue:
                    AutovalThread.wait_for_autoval_thread(ns_validate_queue)
            AutovalLog.log_info(
                "NVME LIST AFTER CLEANUP\n" + self.host.run("nvme list")
            )
        self.umount()
        super().cleanup(**kwargs)
