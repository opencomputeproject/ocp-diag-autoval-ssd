#!/usr/bin/env python3

# pyre-unsafe
import json
import os
import re
import time

from autoval.lib.host.component.component import COMPONENT

from autoval.lib.transport.ssh import SSHConn
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.file_actions import FileActions
from autoval_ssd.lib.utils.disk_utils import DiskUtils
from autoval_ssd.lib.utils.filesystem_utils import FilesystemUtils
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.md_utils import MDUtils
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase


class Fsync(StorageTestBase):
    """
    Run file synchronization test. First, run fioRunner job
    on given drives or filtered drives. After finishing the fio job
    successfully, unmount the devices, create filesystem, and mount back.
    Finally, run fsync.c file on each device.
    """

    RECOMMENDED_FSYNCS = 1000000

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fio_job = self.test_control.get("run_definition", None)
        self.drive_type = self.test_control.get("drive_type", None)
        self.template = self.test_control.get("template", None)
        self.pre_cond_cycles = self.test_control.get("pre_condition_cycle", 0)
        self.fstype = self.test_control.get("fstype", "xfs")
        self.test_raid = self.test_control.get("test_raid", False)
        self.test_results_dict = {"hdd": {}, "ssd": {}}

    def validate_arguments(self) -> None:
        if "run_definition" not in self.test_control:
            raise TestError("Please define run_definition in test_control file")
        if "template" not in self.test_control:
            raise TestError("Please define template parameter in test file")
        if "BLKSIZE" not in self.fio_job:
            raise TestError("Please define BLKSIZE in fio_job")
        if "DEPTH" not in self.fio_job:
            raise TestError("Please define DEPTH in fio_job")
        if "LOOPS" not in self.fio_job:
            raise TestError("Please define LOOPS in fio_job")

    def get_test_params(self) -> str:
        params = (
            "drive_type: {} "
            + "\ntemplate: {}"
            + "\npre-condition cycles: {}"
            + "\nfilesystem type {}"
        ).format(self.drive_type, self.template, self.pre_cond_cycles, self.fstype)
        return params

    def update_loops_param(self, job, cycles):
        """
        Get the job parameter and update the loop key within the job.
        If job is None or not defined, it will return a new job with
        updated cycles.

        @param job: run_definition in the test_control file.
        @param cycles: total of cycles you want to loop for fio.
        """
        if not job:
            precondition = {"BLKSIZE": "128K", "DEPTH": 32, "LOOPS": cycles}
            return precondition
        updated_pre_fio_job = job
        updated_pre_fio_job["LOOPS"] = cycles
        return updated_pre_fio_job

    def precondition_fio_process(self, job, block_names) -> None:
        """
        This is a thread process. It will create fioRunner object,
        and its job. Then it  will run on dut.
        """
        AutovalLog.log_info("Running fio on %s" % (" ".join(block_names)))
        fioRunner = FioRunner(self.host, self.test_control)
        job = fioRunner.create_fio_job(
            drives=block_names, replace=job, templ_filename=self.template
        )
        fioRunner.run_fio_on_dut(job)
        AutovalLog.log_info("End of fio on %s" % (" ".join(block_names)))

    def precondition(self) -> None:
        """
        Create fioRunner object and its fio_job. Run that fio job

        @param cycles: how many cylces that it repeats for fio job.
        If parameter is mentioned, the cycle will change on fio job
        parameter
        """
        AutovalLog.log_info("Starting fsync precondition")
        updated_pre_fio_job = self.update_loops_param(
            job=self.fio_job, cycles=self.pre_cond_cycles
        )
        self.precondition_fio_process(
            job=updated_pre_fio_job,
            block_names=[device.block_name for device in self.test_drives],
        )
        AutovalLog.log_info("Successfully finished precondition")

    def _unmount(self, host, block_name) -> None:
        """
        Unmount the drive
        """
        cmd = "umount /dev/" + block_name
        host.run(cmd, ignore_status=True)

    def _mount(self, host, block_name, fstype) -> None:
        """
        Mount the drive
        """
        mnt_point = "/mnt/havoc_%s" % block_name
        FilesystemUtils.mount(host, block_name, mnt_point, filesystem_type=fstype)

    def start_fsync_for_each_drive(self, each_drive, fstype: str) -> None:
        """
        This function will unmount, create filesystem, mount,
        and run fsync.c file on each drive. At the end, it will unmount.

        @param each_drive: each Drive object from self.test_drives
        @param fstype (str): filesystem type
        """
        AutovalLog.log_info("Starting thread process for %s" % each_drive.block_name)
        host = self.host
        mnt = "/mnt/havoc_%s" % (each_drive.block_name)
        self._unmount(host=host, block_name=each_drive.block_name)
        DiskUtils.remove_all_partitions(host=host, device=each_drive.block_name)
        AutovalLog.log_info("Creating filesystem for %s:" % each_drive.block_name)
        FilesystemUtils.create_filesystem(
            host=host,
            device=each_drive.block_name,
            filesystem_type=fstype,
            options=" -K -i size=2048",
        )
        AutovalLog.log_info("Created filesystem")
        self._mount(host=host, block_name=each_drive.block_name, fstype=fstype)
        df = FilesystemUtils.get_df_info(host=host, device=each_drive.block_name)
        AutovalUtils.validate_condition(
            df["type"] == fstype,
            "Mounted %s at %s, type: %s" % (each_drive.block_name, mnt, df["type"]),
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.SYSTEM_ERR,
        )
        self.run_fsync(
            mnt=mnt, host=host, drive=each_drive, block_name=each_drive.block_name
        )
        self._unmount(host=host, block_name=each_drive.block_name)
        AutovalUtils.validate_condition(
            True,
            "Unmounted %s" % (mnt),
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.SYSTEM_ERR,
        )
        AutovalLog.log_info("End of thread process for %s" % each_drive.block_name)

    def setup_fsync(self, fstype) -> None:
        """
        Setup raid and delete the raid with cleanup if all devices
        parameter is True. Else, for each drive, unmount each drive,
        create a filesystem and mount back. Make sure that mount
        has completed. Validate the filesystem type.
        Unmount at the end of the process for each drive.

        @param fstype: the filesystem type
        """
        md_device = "md125"
        mnt = "/mnt/havoc_" + md_device
        if self.test_raid:
            try:
                AutovalLog.log_info("Creating md raid:")
                MDUtils.setup_md_raid0(host=self.host, devices=self.test_drives)
            except Exception as e:
                raise TestError("Could not setup RAID0 [%s]" % e)
            finally:
                self.run_fsync(
                    mnt=mnt, host=self.host, raid=self.test_raid, block_name="raid0"
                )
                AutovalLog.log_info("Deleting md raid:")
                MDUtils.cleanup_md_raid0(
                    host=self.host,
                    partition_list=[drive.block_name for drive in self.test_drives],
                )
        else:
            t_queue_list = []
            for each_drive in self.test_drives:
                t_queue_list.append(
                    AutovalThread.start_autoval_thread(
                        self.start_fsync_for_each_drive,
                        each_drive=each_drive,
                        fstype=fstype,
                    )
                )
            if t_queue_list:
                AutovalThread.wait_for_autoval_thread(t_queue_list)

    def run_fsync(self, mnt, host, block_name, raid: bool = False, drive=None) -> None:
        for bs in [512, 1024, 2048, 4096, 8192, 16384]:
            log = os.path.join(self.control_server_logdir, "fsync_%s.log" % block_name)
            itr = self.RECOMMENDED_FSYNCS

            cmd = "touch %s/tmp_%d.txt" % (mnt, bs)
            host.run(cmd)
            cmd = "cd " + self.dut_tmpdir[host.hostname]
            host.run(cmd)
            cmd = "./fsync %s/tmp_%d.txt %d %d" % (mnt, bs, itr, bs)
            out = host.run(
                cmd, timeout=2800, working_directory=self.dut_tmpdir[self.host.hostname]
            )
            key_prefix = "block_size_" + str(bs)
            out_dic = self.parse_results(out, bs, key_prefix)
            current_time = time.time()
            if raid:
                self.result_handler.add_test_results(out_dic)
            else:
                if not drive:
                    raise TestError(
                        "Please pass in drive object into run_fsync parameter."
                    )
                drive_type = drive.get_type().value
                self.format_the_output_result(
                    drive_type, drive.serial_number, out_dic, current_time
                )

            with open(log, "a") as outfile:
                json.dump(out_dic, outfile, indent=4, sort_keys=True)

            dic_key = key_prefix + "_rate"
            if out_dic[dic_key]:
                perf_test_data = {"val": out_dic[dic_key]}
                AutovalUtils.validate_condition(
                    perf_test_data,
                    "fsync regression test",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.TOOL_ERR,
                )
            AutovalUtils.validate_condition(
                True,
                "Ran %s" % cmd,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.SYSTEM_ERR,
            )

    def parse_results(self, out, bs, key_prefix):
        """
        Use regular epxression to extract the result (number) from the output.
        Then store the result into the dictionary and return that dictionary
        at the end.
        """
        if not out:
            raise TestError("The output from fsync.c is empty.")
        fsync = {}
        for line in out.split("\n"):
            fsync_re = re.search(r"block_size:\s+(\d+),\s+(\d+)\s+fsync/sec", line)
            if fsync_re:
                fsync[key_prefix + "_rate"] = int(fsync_re.group(2))

            latency_re = re.search(
                r"Avg:\s+(\d+),\s+P95:\s+(\d+),\s+P99:" + r"\s+(\d+),\s+Max:\s+(\d+)",
                line,
            )
            if latency_re:
                fsync[key_prefix + "_lat_avg"] = int(latency_re.group(1))
                fsync[key_prefix + "_lat_p95"] = int(latency_re.group(2))
                fsync[key_prefix + "_lat_p99"] = int(latency_re.group(3))
                fsync[key_prefix + "_lat_max"] = int(latency_re.group(4))

        if not fsync:
            raise TestError("The output from fsync is out of expected. \n %s" % out)
        return fsync

    def format_the_output_result(
        self, drive_type, serial_number, out_dic, time
    ) -> None:
        """
        Formatting the result into a list

        @param drive_type: the drive type
        @param serial number: the serial number of the drive
        @param out_dic: the output dictionary
        @param time: the time stamp
        """
        if str(serial_number) not in self.test_results_dict[drive_type]:
            self.test_results_dict[drive_type][str(serial_number)] = []

        for key in out_dic:
            formatted_result = []
            formatted_result.append(key)
            formatted_result.append(out_dic[key])
            formatted_result.append(time)
            self.test_results_dict[drive_type][str(serial_number)].append(
                formatted_result
            )

    def append_test_result(self) -> None:
        """
        Appending the test_result data after test_base.

        Step 1: Open the test_results.json produced by test_base
        Step 2: Read the json file and add fsync data
        Step 3: Save the modified data into test_results.json
        """
        AutovalLog.log_info("Appending result to test_results")
        test_res_file = self.get_test_results_file_path("test_results.json")
        if not os.path.exists(test_res_file):
            self.result_handler._save_json(self.test_results_dict, test_res_file)
        else:
            current_test_result_data = FileActions.read_data(test_res_file)
            current_test_result_data.update(self.test_results_dict)
            self.result_handler._save_json(current_test_result_data, test_res_file)

    def setup_fsync_cfile(self) -> None:
        """
        Before running the test, first need to get the fsync.c file
        and copy it to the DUT server.
        """
        tool_path = "tools"
        templ_filename = "fsync.c"
        file_path = FileActions.get_resource_file_path(
            os.path.join(tool_path, templ_filename), module="autoval_ssd"
        )
        remote_path = os.path.join(self.dut_tmpdir[self.host.hostname], templ_filename)
        SSHConn.put_file(self.host, file_path, remote_path)
        cmd = f"gcc {remote_path} -o fsync"
        self.host.run(cmd, working_directory=self.dut_tmpdir[self.host.hostname])

    def storage_test_setup(self) -> None:
        """
        The first setup gets called in storage_test_base. After the setup,
        the storage_test_setup from storage_test_base gets overwritten
        here; thus, this gets called.
        """
        self.validate_arguments()
        super().storage_test_setup()

    def execute(self) -> None:
        if self.pre_cond_cycles > 0:
            self.precondition()
        self.setup_fsync_cfile()
        self.setup_fsync(fstype=self.fstype)

    def cleanup(self, *args, **kwargs) -> None:
        super().cleanup(*args, **kwargs)
        self.append_test_result()

