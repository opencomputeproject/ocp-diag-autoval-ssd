#!/usr/bin/env python3

# pyre-unsafe
"""
Test validates the MD5 checkusm on the SSD/HDD
by doing an fio write, get MD5 value on the written data,
reboot and again check the MD5 value and compare it with
original value using the MD5 function or FIO based on the
input control file for  filesystem and raw drives.
The size to be written for fio is based on the user input
from the control file.This test supports all interfaces like
NVME, SATA and SAS.
"""

import copy
import random
import time
from typing import Dict

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalUtils, TestError
from autoval.lib.utils.file_actions import FileActions
from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.filesystem_utils import FilesystemUtils
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase

MOUNT_PATH = "/mnt/fio_test_%s/"


class DriveMd5Verify(StorageTestBase):
    """
    Test validates the MD5 checksum on the SSD/HDD for both
    filesystem and raw drives using the MD5 function or the fio md5, based
    on the input. For the fio the size to be written is calculated based on
    the input from the control file. Once the FIO write is completed it goes
    for a reboot, then goes for FIO read and verify and checksum calculation.
    This test supports all interfaces like NVME, SATA and SAS.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initializes the SSD MD5 test.

        This method initializes the basic configuration for logging
        information, load and store the input details gathered from
        input/control (json) file.
        """
        super().__init__(*args, **kwargs)
        self.cycle_type_list = self.test_control.get("cycle_type_list", ["warm"])
        self.cycle_count = self.test_control.get("cycle_count", 1)
        self.filesystem = self.test_control.get("filesystem", False)
        self.percent_write_size = self.test_control.get("percent_write_size", 5)
        self.md5_verification = self.test_control.get("md5_verification", True)
        self.write_fio = self.test_control["write_fio"]
        self.read_fio = self.test_control["read_fio"]
        self.verify_fio = self.test_control["verify_fio"]
        self.wait_time = self.test_control.get("wait_time", 10)
        self.drives_md5 = {}
        if self.filesystem:
            fio_name = (
                self.write_fio.get("ssd_md5", {}).get("args", {}).get("NAME", "file1")
            )
            self.file_io = fio_name
        else:
            self.file_io = ""
        # Chunked MD5 settings for faster md5sum on large drives
        self.use_chunked_md5 = self.test_control.get("use_chunked_md5", False)
        self.num_chunks = self.test_control.get("num_chunks", 4)

    def setup(self, *args, **kwargs) -> None:
        super().setup(*args, **kwargs)
        # Setup fio
        if self.test_drives:
            self.test_control["drives"] = self.test_drives
        if self.boot_drive:
            self.test_control["boot_drive"] = self.boot_drive
        fio_runner = FioRunner(self.host, self.test_control)
        self.validate_no_exception(
            fio_runner.test_setup,
            [],
            "Fio setup()",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

    def get_test_params(self) -> str:
        """
        Returns a string of test_params for the Test Summary
        """
        params = (
            f"\nCycle count: {self.cycle_count}. Cycle type: {self.cycle_type_list}. "
        )
        params += f"Use filesystem: {self.filesystem}. MD5 verification: {self.md5_verification}"
        return params

    def execute(self) -> None:
        """
        This method calls the functions where it calculates size to be given
        for fio write and updates the same to the FioRunner function where it
        process the input json file.
        Test flow:
        1.Checks the filesystme type, number of cycles and capacity to
        from the input json. The capacity is in percentage.For ex, if its 10,
        it means,the size to be written in 10% of the least capacity drive.
        2.Call the fio run method where it schedules the fio run
        3.Calculate the MD5 value.(Based on the json check MD5 calculation
          will be done by fio or the inbuilt function used
        4.Power cycle the DUT
        6.Mount the drives again if it's a filesystem test
        7.Calculate the MD5 value after reboot (This is also based on the json
          check)
        8.Compare the MD5 values if the function method is used for checking the
          MD5 values.
        """
        initial_size = self.write_fio["ssd_md5"]["args"]["SIZE"]
        size = self.calculate_size_for_fio()
        if initial_size != size:
            self.log_info(f"Fio size has changed from {initial_size} to {size}")

        for i in range(1, self.cycle_count + 1):
            self.log_info(f"Starting cycle - {i}")

            if self.use_chunked_md5:
                self._execute_chunked(size)
            else:
                self._execute_standard(size)

    def _execute_standard(self, size: str) -> None:
        """Standard flow with single file per drive."""
        self.write_fio["ssd_md5"]["args"]["SIZE"] = size
        self.read_fio["ssd_md5"]["args"]["SIZE"] = size
        self.verify_fio["ssd_md5"]["args"]["SIZE"] = size

        self.log_info("FIO Write is starting")
        self.run_fio(self.write_fio, job_name="write")
        md5_before_power_cycle = None
        if self.md5_verification:
            md5_before_power_cycle = self.get_md5_value()
        self.power_cycle()
        self.log_info("FIO Read is starting")
        self.run_fio(self.read_fio, job_name="read")
        self.log_info("FIO Verify is starting")
        self.run_fio(self.verify_fio, job_name="verify")
        if md5_before_power_cycle is not None:
            md5_after_power_cycle = self.get_md5_value()
            diffs = self.diff_configs(md5_before_power_cycle, md5_after_power_cycle)
            self.validate_empty_diff(
                diffs,
                "MD5 checksum differences",
                raise_on_fail=True,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

    def _execute_chunked(self, total_size: str) -> None:
        """Chunked flow - N parallel FIO jobs per drive for faster md5sum.

        Filesystem mode: each chunk writes to its own file (offset 0).
        Raw mode: each chunk writes to a non-overlapping region of
        ``/dev/<dev>`` at ``chunk_idx * chunk_size`` (OFFSET is injected
        automatically; users do not need to set it in test_control).

        The test control JSON must use chunked FIO templates (without
        time_based/runtime) so FIO writes/reads every block exactly once,
        avoiding "bad magic header" errors.
        """
        if self.num_chunks <= 0:
            raise TestError(
                f"Invalid num_chunks={self.num_chunks}. num_chunks must be a "
                f"positive integer.",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.INPUT_ERR,
            )
        chunk_bytes = DiskUtils.get_bytes(total_size) // self.num_chunks
        chunk_mib = chunk_bytes // (1024**2)
        if chunk_mib <= 0:
            raise TestError(
                f"Computed chunk size is zero: total_size={total_size}, "
                f"num_chunks={self.num_chunks}. Reduce num_chunks or increase "
                f"total_size so each chunk is at least 1 MiB.",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.INPUT_ERR,
            )
        self.chunk_mib = chunk_mib
        chunk_size = f"{chunk_mib}m"
        self.log_info(
            f"Using {self.num_chunks} chunks of {chunk_size} each "
            f"({'filesystem files' if self.filesystem else 'raw device offsets'})"
        )

        # Write all chunks - first chunk creates filesystem, rest just mount
        self.log_info(f"FIO Write - Starting {self.num_chunks} chunks")
        self._run_fio_chunks(self.write_fio, chunk_size, "write", is_first_phase=True)

        self.log_info("Syncing filesystems before power cycle")
        # pyrefly: ignore [missing-attribute]
        self.host.run("sync", timeout=300)
        # Allow 120s for all in-flight I/O and writeback caches to flush to
        # NVMe media.  Enterprise SSDs can have large volatile write buffers
        # (several GB) that are only persisted after the device finishes its
        # internal garbage-collection / write-amplification passes.  A shorter
        # wait risks comparing stale on-media data after the power cycle.
        time.sleep(120)

        # Randomly select one chunk index for MD5 verification
        md5_chunk_idx = random.randint(0, self.num_chunks - 1)
        self.log_info(
            f"MD5 verification will be performed on chunk {md5_chunk_idx} "
            f"(randomly selected from {self.num_chunks} chunks)"
        )

        md5_before_power_cycle = None
        if self.md5_verification:
            md5_before_power_cycle = self._get_chunked_checksum(md5_chunk_idx)

        self.power_cycle()

        # Read all chunks after power cycle
        self.log_info(f"FIO Read - Starting {self.num_chunks} chunks")
        self._run_fio_chunks(self.read_fio, chunk_size, "read", is_first_phase=False)

        # Verify all chunks
        self.log_info(f"FIO Verify - Starting {self.num_chunks} chunks")
        self._run_fio_chunks(
            self.verify_fio, chunk_size, "verify", is_first_phase=False
        )

        if md5_before_power_cycle is not None:
            md5_after_power_cycle = self._get_chunked_checksum(md5_chunk_idx)
            diffs = self.diff_configs(md5_before_power_cycle, md5_after_power_cycle)
            self.validate_empty_diff(
                diffs,
                "MD5 checksum differences",
                raise_on_fail=True,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )

    def _run_fio_chunks(
        self,
        fio_config: dict,
        chunk_size: str,
        job_prefix: str,
        is_first_phase: bool = True,
    ) -> None:
        """Run all FIO chunk jobs fully in parallel after a dedicated
        filesystem setup step.

        Phase 1 – filesystem setup (sequential, fast):
          - Write phase (is_first_phase=True):  create filesystem + mount all
            drives via FioRunner.create_filesystem_mount.
          - Read/verify phases (is_first_phase=False): remount already-formatted
            drives via FilesystemUtils.mount_all (force_mount=False).
            FilesystemUtils.mount is idempotent: if a drive is already correctly
            mounted it returns immediately, so this call is safe even if the
            drives are still mounted from a previous phase.

        Phase 2 – parallel FIO (all N chunks at once):
          - Every chunk runs with skip_fs=True so FioRunner skips its own mount
            logic.  The idempotency check in FilesystemUtils.mount prevents
            "already mounted" races between concurrent threads.
        """
        if self.filesystem:
            data_drives = [
                d for d in self.test_drives if d.block_name != str(self.boot_drive)
            ]
            if is_first_phase:
                self.log_info("Creating filesystems and mounting all drives")
                ssd_md5_params = fio_config.get("ssd_md5", {})
                filesystem_type = ssd_md5_params.get("filesystem_type") or "xfs"
                filesystem_options = ssd_md5_params.get("filesystem_options") or ""
                tc = dict(self.test_control)
                fio_runner_setup = FioRunner(self.host, tc)
                fio_runner_setup.create_filesystem_mount(
                    self.host, data_drives, filesystem_type, filesystem_options
                )
            else:
                self.log_info("Remounting all drives (no reformat)")
                FilesystemUtils.mount_all(
                    # pyrefly: ignore [bad-argument-type]
                    self.host,
                    [d.block_name for d in data_drives],
                    "/mnt/fio_test_%s/",
                    force_mount=False,
                )

        self.log_info(f"FIO {job_prefix} - launching {self.num_chunks} chunks")
        threads = []
        for i in range(self.num_chunks):
            cfg = copy.deepcopy(fio_config)
            cfg["ssd_md5"]["args"]["SIZE"] = chunk_size
            cfg["ssd_md5"]["args"]["NAME"] = f"file_chunk{i}"
            # Raw: each chunk hits a different /dev/<dev> region.
            # FS: each chunk has its own file, offset stays 0.
            cfg["ssd_md5"]["args"]["OFFSET"] = (
                "0" if self.filesystem else f"{i * self.chunk_mib}m"
            )
            # Per-chunk safety file for the boot drive so concurrent chunks
            # don't share /root/fio_file. FioRunner pins this section's
            # offset to 0 so the file's start matches the writes.
            cfg["ssd_md5"]["files"] = {"file": f"/root/fio_file_chunk{i}"}
            if self.filesystem:
                cfg["ssd_md5"]["skip_fs"] = True
            threads.append(
                AutovalThread.start_autoval_thread(
                    self._run_fio_for_chunk,
                    cfg,
                    f"{job_prefix}_c{i}",
                    threadname=f"fio_{job_prefix}_c{i}",
                )
            )
        AutovalThread.wait_for_autoval_thread(threads)
        self.log_info(f"FIO {job_prefix} - {self.num_chunks} chunks done")

    def _run_fio_for_chunk(self, fio_config: dict, job_name: str) -> None:
        """Thread-safe FIO execution with an independent test_control copy.
        Uses a shallow copy of test_control so each thread has its own
        top-level dict for job_name and run_definition, while sharing
        references to non-copyable objects (Host, drives, loggers).
        """
        tc = dict(self.test_control)
        tc["job_name"] = job_name
        tc["run_definition"] = fio_config
        fio_runner = FioRunner(self.host, tc)
        fio_runner.start_test()
        self.log_info(f"FIO {job_name} completed")

    def _get_chunked_checksum(self, chunk_idx: int) -> Dict[str, str]:
        """Per-drive md5 keyed by id_path so it survives block-name shifts
        across power cycles. Filesystem mode hashes the chunk file under each
        mount; raw mode hashes the chunk's /dev/<dev> region via dd. Boot
        drive is always hashed as its per-chunk safety file.
        """
        data_drives = [
            d for d in self.test_drives if d.block_name != str(self.boot_drive)
        ]
        block = {id(d): d.block_name for d in data_drives}
        boot_path = f"/root/fio_file_chunk{chunk_idx}"
        boot_in_test = any(
            d.block_name == str(self.boot_drive) or str(d) == str(self.boot_drive)
            for d in self.test_drives
        )

        if self.filesystem:
            drive_chunk_map = {
                (getattr(d, "id_path", None) or block[id(d)]): [
                    f"{MOUNT_PATH % block[id(d)]}file_chunk{chunk_idx}"
                ]
                for d in data_drives
            }
            self.drives_md5 = {
                block[id(d)]: MOUNT_PATH % block[id(d)] for d in data_drives
            }
            if boot_in_test:
                drive_chunk_map[str(self.boot_drive)] = [boot_path]
            self.log_info(f"MD5 chunk {chunk_idx}: {drive_chunk_map}")
            md5values = DiskUtils.get_md5_for_drivelist_chunked(
                # pyrefly: ignore [bad-argument-type]
                self.host,
                drive_chunk_map,
            )
        else:
            offset_mib = chunk_idx * self.chunk_mib
            self.log_info(
                f"MD5 chunk {chunk_idx} (offset={offset_mib}MiB, "
                f"size={self.chunk_mib}MiB)"
            )
            keys, threads = [], []
            host_dict = AutovalUtils.get_host_dict(self.host)
            for d in data_drives:
                keys.append(getattr(d, "id_path", None) or block[id(d)])
                threads.append(
                    AutovalThread.start_autoval_thread(
                        Host(host_dict).run,
                        cmd=(
                            f"set -o pipefail; "
                            f"dd if=/dev/{block[id(d)]} bs=1M skip={offset_mib} "
                            f"count={self.chunk_mib} iflag=direct status=none "
                            f"| md5sum"
                        ),
                        timeout=7200,
                    )
                )
            if boot_in_test:
                keys.append(str(self.boot_drive))
                threads.append(
                    AutovalThread.start_autoval_thread(
                        Host(host_dict).run,
                        cmd=f"md5sum {boot_path}",
                        timeout=7200,
                    )
                )
            results = AutovalThread.wait_for_autoval_thread(threads)
            md5values = {k: self._parse_md5_output(k, r) for k, r in zip(keys, results)}
        self.log_info(f"MD5 values: {md5values}")
        return md5values

    def _parse_md5_output(self, key: str, output) -> str:
        """Extract md5 hash from `md5sum` output; raise on empty/missing data."""
        tokens = (output or "").split() if isinstance(output, str) else []
        if not tokens:
            raise TestError(
                f"MD5 computation failed for {key}: empty/missing output ({output!r}). "
                f"Likely a dd read error or thread failure.",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
            )
        return tokens[0]

    def run_fio(self, fio_input, job_name: str = "") -> None:
        """
        FIO Job of the SSD MD5 Test.
        This method executes the FIO start test method where the
        FIO process is started(creationg FIO job to  scheduling
        it on the DUT)

        Parameters
        ----------
        fio_input : String
           The fio configuration
        """
        if job_name:
            self.test_control["job_name"] = job_name
        self.test_control["run_definition"] = fio_input
        fio_runner = FioRunner(self.host, self.test_control)
        fio_runner.start_test()

    def calculate_size_for_fio(self) -> str:
        """
        This function will get the final size to be written
        on the disk for the fio operation.The return value will
        get updated on the fio job file.
        Example:if in the control file,if the percent_disk_size mentioned
        is 10,so it will calculate the 10% size of the all the drives and
        return 10% value of the least size drive which will be updated
        on the fio run definition size.
        """
        final_size = DiskUtils.calculate_min_size_of_drives(
            # pyrefly: ignore [bad-argument-type]
            self.host,
            self.percent_write_size,
            self.test_drives,
        )
        return final_size

    def power_cycle(self) -> None:
        """Power Cycle of the SSD MD5 Test.

        This method executes the power cycle for SSD MD5 test by
        executing the power cycle command on the DUT through OutOfBand
        based on the cycle type.
        """
        for cycle_type in self.cycle_type_list:
            if self.wait_time and cycle_type.lower() in ["on", "12v-on"]:
                self.log_info(
                    "%s seconds waiting to power on host %s"
                    % (
                        self.wait_time,
                        self.host.hostname,  # pyrefly: ignore [missing-attribute]
                    )  # pyrefly: ignore [missing-attribute]
                )
                # If cycle type is 'off' or '12v-off' follwed by 'on' or '12v-on'
                # waiting to power on the dut as per the wait_time.
                time.sleep(self.wait_time)
            self.log_info("Running %s power_cycle" % cycle_type)
            # pyrefly: ignore [missing-attribute]
            self.host.cycle_host(self.host, cycle_type)

    def get_md5_for_drivelist(
        self,
        drive_path_map: Dict[str, str],
        parallel: bool = True,
        key: str = "md5",
    ) -> Dict[str, str]:
        """
        This function will get the md5 values for all the devices sent.This will work
        for both filesystem and for raw disk.

        Parameters
        ----------
        host : :obj: 'Host'
           host : :obj: 'Host'
        drive_path_map: : Dict of :obj: 'str' of :obj: 'str'
           Dict of drive and path.
        path: String
           Path eg. /mnt/fio_test_%s/file1
        key: String
            md5, sha1, sha224, sha256, sha384, sha512

        Returns
        -------
        DiskUtils.md5: dictionary
           Drive name is key and md5 is value.
        """
        if key not in ["md5", "sha1", "sha224", "sha256", "sha384", "sha512"]:
            key = "md5"
        threads = []
        host_dict = AutovalUtils.get_host_dict(self.host)
        for device, path in drive_path_map.items():
            if parallel:
                threads.append(
                    AutovalThread.start_autoval_thread(
                        DiskUtils.get_md5_sum,
                        Host(host_dict),
                        path,
                        device=device,
                        key=key,
                    )
                )
            else:
                # pyrefly: ignore [bad-argument-type]
                DiskUtils.get_md5_sum(self.host, path, device=device, key=key)
        AutovalThread.wait_for_autoval_thread(threads)
        return DiskUtils.md5

    def get_md5_value(self):
        """
        This function calculates the md5 checksum which has been written on
        the mounted drive file.

        Returns
        -------
        md5values : Dict
            The md5 checksum value to its respective device.
        """
        md5values = {}
        self.drives_md5 = {
            d.block_name: (
                MOUNT_PATH % d.block_name + self.file_io
                if self.filesystem
                else f"/dev/{d.block_name}"
            )
            for d in self.test_drives
            if d.block_name != str(self.boot_drive)
        }
        if self.drives_md5:
            self.log_info(f"Checking MD5 on Data drives: {self.drives_md5}")
            md5values = self.get_md5_for_drivelist(self.drives_md5)
        if str(self.boot_drive) in str(self.test_drives):
            path = (
                MOUNT_PATH % self.boot_drive + self.file_io
                if self.filesystem
                else f"/dev/{self.boot_drive}"
            )
            if DiskUtils.is_drive_mounted(self.host, str(self.boot_drive)):
                path = FioRunner.MOUNTED_DRIVE_FIO_PATH
            self.log_info(f"Checking MD5 on Boot drive: {self.boot_drive}")
            md5 = DiskUtils.get_md5_sum(self.host, path)
            md5values.update({self.boot_drive: md5})
        self.log_info(f"MD5 values: {md5values}")
        return md5values

    def cleanup(self, *args, **kwargs) -> None:
        """Unmount drives and clean up per-chunk safety files."""
        self.validate_no_exception(
            FilesystemUtils.unmount_all,
            [self.host, list(self.drives_md5.keys()), MOUNT_PATH],
            "Clean drive",
            raise_on_fail=False,
            log_on_pass=False,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.DRIVE_ERR,
        )
        if self.use_chunked_md5:
            FileActions.rm("/root/fio_file_chunk*", host=self.host)
        super().cleanup(*args, **kwargs)
