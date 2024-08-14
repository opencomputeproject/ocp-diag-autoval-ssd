#!/usr/bin/env python3

# pyre-unsafe
"""Utils for FioSynthFlash test"""
import json
import os
import re
import time
from glob import glob
from typing import Dict, List, Optional, Tuple

from autoval.lib.host.component.component import COMPONENT

from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.file_actions import FileActions
from autoval.lib.utils.generic_utils import GenericUtils
from autoval_ssd.lib.utils.system_utils import SystemUtils


class FioSynthFlashUtils:
    """
    Summary:
        This is FioSynthFlashUtils. This will run command on host for
        FioSynthFlash commands and also will verify the output of the command.
        If the parallel parameter is given true, then it will run
        parallel for each drive and output in dictionary format of test_result.

        If the parallel parameter is false or not given, then it will
        run the fioSynthflash in all drives in single command. If this is the case,
        then the output will be just the result direcotry in string, not the
        dictionary.

        **Please look at start_fio_synth_flash function which is the main
        function.
    """

    results = []

    @staticmethod
    def tool_setup(host) -> None:
        AutovalLog.log_info("Installing fiosynth")
        SystemUtils.install_rpms(host, ["fiosynth"])
        FioSynthFlashUtils.get_version(host)

    @staticmethod
    def get_version(host) -> None:
        out = host.run("fiosynth -v")
        pattern = r"\d+\.\d+\.*\d*"
        match = re.search(pattern, out)
        if match:
            version = match.group(0)
            AutovalLog.log_info("+++Running fiosynth version: %s" % version)
        else:
            AutovalLog.log_info("fiosynth version not detected: Reinstalling")
            SystemUtils.install_rpms(host, ["fiosynth"], force_install=True)
            out = host.run("fiosynth -v")
            match2 = re.search(pattern, out)
            if match2:
                version = match2.group(0)
                AutovalLog.log_info("+++Running fiosynth version: %s" % version)
            else:
                raise TestError(
                    "fiosynth version not detected: %s" % out,
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.TOOL_ERR,
                )

    @staticmethod
    def find_csv_files(host, results_dir: str) -> List:
        """
        Find the output csvfile from fio_synth_flash. Returns a list
        of found csvfiles from that directory.

        @param results_dir: the directory where the output is stored
        """
        found = []
        AutovalLog.log_info(
            "[FioSynthFlash Log] Finding csv file in dir %s" % results_dir
        )
        files = FileActions.ls(results_dir, host=host)
        for f in files:
            filename = os.path.join(results_dir, f)
            if f.endswith(".csv"):
                found.append(filename)
        return found

    @staticmethod
    def find_errors(host, results_dir: str, ignore_error: bool = False) -> List:
        """
        Find error files and check if there is error in result by going through
        each json files from the result directory.

        @param results_dir: the directory where the output is stored
        @return errors: it will return list of json file directory that
        has errors.
        """
        AutovalLog.log_info(
            "[FioSynthFlash Log] Finding errors in json file at dir %s" % results_dir
        )
        if ignore_error:
            AutovalLog.log_info(
                "[FioSynthFlash Log] Warning that the ignoring error mode is on"
            )
        errors = []
        files = FileActions.ls(results_dir, host=host)
        for filename in files:
            file_path = os.path.join(results_dir, filename)
            if filename.endswith(".json"):
                try:
                    result = FileActions.read_data(
                        file_path, json_file=False, host=host
                    )
                    if not result.startswith("{"):
                        AutovalUtils.validate_condition(
                            False,
                            f"{os.path.basename(file_path)} has some non-JSON data at the beginning of the file",
                            warning=True,
                            error_type=ErrorType.TOOL_ERR,
                        )
                        result = FioSynthFlashUtils.remove_non_json_prefix(result)
                    result = json.loads(result)
                    for job in result.get("jobs", {}):
                        if job["error"] != 0:
                            if ignore_error:
                                errors.append(file_path)
                            else:
                                raise TestError(
                                    "Fio job has warnings or errors, "
                                    "Check '%s' for more info" % file_path,
                                    component=COMPONENT.STORAGE_DRIVE,
                                    error_type=ErrorType.DRIVE_ERR,
                                )
                except Exception as log_error:
                    raise TestError(
                        str(log_error),
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.DRIVE_ERR,
                    )
        return errors

    @staticmethod
    def remove_non_json_prefix(json_str: str) -> str:
        """
        Removes any non-JSON data from the beginning of the input string.
        Args:
            json_data (str): A string representing a JSON object that may have stray data at the start.
        Returns:
            str: The modified value of json_data with non-JSON data removed from the start.
        Note:
            This only works if json_data represents a JSON object (starts with '{').  It doesn't work
            if json_data is an array (starts with '['), string, number, boolean or some other JSON type
        """
        return re.sub(r".*?({.*})", r"\1", json_str, flags=re.DOTALL)

    @staticmethod
    def start_fio_synth_flash(
        host: Host,
        workload: str,
        resultsdir: str,
        options=None,
        test_drive_filter=None,
        test_drives=None,
        ignore_error: bool = False,
        lm_enabled_drives: Optional[List[str]] = None,
    ):
        """
        This is the main function to start the fio_synth_flash.
        By giving the parameter of options, the command will have additional
        options. For example,

        fio_synth_params: {
            'raid': true, <- this will run the ALLRAID
            'parallel': true, <- this will run fio_synth_flash in parallel
            'synth_options': ... <- passing additional options to fio_snyth command
            'synth_verify': <- This will run the fio_synth output validation,
                               synth_verify is only supported when parallel is true.
        }

        Note that you have to pass test_drives as a parameter if you want
        to run in parallel.

        Return format:
            if parallel,
                the return format will be (drive, filepath, timestmap, cmd).
            However,
                if its not parallel, it will return in (filepath, timestamp, cmd)
                without the drive.
        """
        if lm_enabled_drives is None:
            lm_enabled_drives = []
        FioSynthFlashUtils.tool_setup(host)
        if options is None:
            options = {}
        raid = options.get("raid", False)
        parallel = options.get("parallel", False)
        synth_options = options.get("synth_options", None)
        synth_verify = options.get("synth_verify", None)
        if synth_verify and (not parallel):
            msg = f"Current setting synth_verify={synth_verify}, parallel={parallel}"
            raise TestError(
                f"synth verify is only supported with fiosynth parallel run, {msg}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.INPUT_ERR,
            )
        AutovalLog.log_info("[FioSynthFlash Log] Starting fioSynthFlash.")
        cmd = "fiosynth -x -w %s" % workload
        if raid:
            AutovalLog.log_info("[FioSynthFlash Log] Running in ALLRAID.")
            results_file = workload + "_raid_results"
            cmd += " -f %s -d ALLRAID" % results_file
        elif test_drive_filter:
            list_of_drives = "_".join(str(drive.block_name) for drive in test_drives)
            AutovalLog.log_info(
                "[FioSynthFlash Log] Running on mentioned test drives: %s"
                % list_of_drives
            )
            if parallel:
                AutovalLog.log_info("[FioSynthFlash Log] Running in Parallel")
                t_queue_list = []
                for drive in test_drives:
                    t_queue_list.append(
                        AutovalThread.start_autoval_thread(
                            FioSynthFlashUtils.run_fio_synth_parallel,
                            host=host,
                            workload=workload,
                            resultsdir=resultsdir,
                            drive=drive,
                            cmd=cmd,
                            synth_options=synth_options,
                            ignore_error=ignore_error,
                        )
                    )
                if t_queue_list:
                    AutovalThread.wait_for_autoval_thread(t_queue_list)
                if synth_verify:
                    FioSynthFlashUtils.synth_output_validation(
                        host, resultsdir, workload, test_drives, lm_enabled_drives
                    )
                return FioSynthFlashUtils.results
            else:
                results_file = workload + "_%s_results" % list_of_drives
                cmd += " -f %s" % results_file
                list_of_block_names = [
                    "/dev/%s" % drive.block_name for drive in test_drives
                ]
                list_of_block_names = ":".join(list_of_block_names)
                cmd += " -d %s" % list_of_block_names
        else:
            AutovalLog.log_info(
                "[FioSynthFlash Log] Running on all drives with single command"
            )
            results_file = workload + "_all_drives_results"
            cmd += " -f %s -d ALL" % results_file
        result_directory, cmd = FioSynthFlashUtils.run_fio_synth_cmd(
            host=host, cmd=cmd, resultsdir=resultsdir, synth_options=synth_options
        )
        FioSynthFlashUtils.csv_output_validation(host, result_directory)
        errors = FioSynthFlashUtils.find_errors(host, result_directory, ignore_error)
        time_stamp = int(time.time())
        return [(result_directory, time_stamp, cmd, errors)]

    @staticmethod
    def run_fio_synth_parallel(
        host,
        workload: str,
        resultsdir: str,
        drive,
        cmd: str,
        synth_options=None,
        ignore_error: bool = False,
    ) -> None:
        host_dict = AutovalUtils.get_host_dict(host)
        new_host = Host(host_dict)
        results_file = workload + ("_%s_results" % str(drive.block_name))
        cmd += " -f %s" % results_file
        cmd += " -d /dev/%s" % str(drive.block_name)
        output_folder, cmd = FioSynthFlashUtils.run_fio_synth_cmd(
            host=new_host, cmd=cmd, resultsdir=resultsdir, synth_options=synth_options
        )
        csv_files_found = FioSynthFlashUtils.csv_output_validation(host, output_folder)
        errors = FioSynthFlashUtils.find_errors(host, output_folder, ignore_error)
        FioSynthFlashUtils.csv_into_resultjson(resultsdir, workload)
        time_stamp = int(time.time())
        FioSynthFlashUtils.results.append(
            (drive, csv_files_found[0], time_stamp, cmd, errors)
        )

    @staticmethod
    def csv_output_validation(host, resultsdir: str) -> List:
        """
        Validate the fio_synth output by checking if csv files exist
        within the result directory.
        """
        AutovalLog.log_info(
            "[FioSynthFlash Log] Validating csv_files at %s" % resultsdir
        )
        csv_files_found = FioSynthFlashUtils.find_csv_files(host, resultsdir)
        AutovalUtils.validate_non_empty_list(
            csv_files_found,
            "checking csvfiles at %s" % resultsdir,
            component=COMPONENT.SYSTEM,
            error_type=ErrorType.SYSTEM_ERR,
        )
        return csv_files_found

    @staticmethod
    def run_fio_synth_cmd(
        host, cmd: str, resultsdir: str, synth_options=None
    ) -> Tuple[str, str]:
        """
        run fio_synth command

        @param host: the host of the server
        @param resultsdir: the result directory of fio_synth_flash
        @param cmd: the command for fio_synth_flash to execute

        @return: returns a result directory and final command that it ran.
        """
        if synth_options:
            cmd += " %s " % synth_options
        AutovalLog.log_info("Starting command: %s" % cmd)
        try:
            # resultsdir = FileActions.get_local_path(host, resultsdir, recursive=True)
            output = host.run(
                cmd=cmd, timeout=3600 * 24 * 10, working_directory=resultsdir
            )
        except Exception as e:
            raise TestError(
                "[FioSynthFlash Log] Failed to run %s %s" % (cmd, e),
                component=COMPONENT.SYSTEM,
                error_type=ErrorType.SYSTEM_ERR,
            )
        folder_name = FioSynthFlashUtils.parse_out_result_folder(output)
        result_folder = os.path.join(resultsdir, folder_name)
        AutovalLog.log_info("[FioSynthFlash Log] Output: %s" % result_folder)
        return result_folder, cmd

    @staticmethod
    def parse_out_result_folder(output) -> str:
        """
        Once get the output from running fio_synth_flash command, get the
        result directory from that string output.

        @param output: the string output from the fio_synth command
        """
        match = re.search(r"Results are in directory:\s*(\S+)", output)
        if match:
            return match.group(1)
        raise TestError(
            f"[FioSynthFlash Log] The result directory is not in: {output}",
            component=COMPONENT.SYSTEM,
            error_type=ErrorType.SYSTEM_ERR,
        )

    @staticmethod
    def synth_output_validation(
        host,
        results_dir: str,
        synth_workload: str,
        test_drives: List,
        lm_enabled_drives: Optional[List[str]] = None,
    ) -> None:
        """Synth Output Validation.

        Each fio workload in synth is compared with it's range in target
        workload file.

        Parameters
        -----------
        results_dir
             Master result directory of synth load.
        synth_workload
             FioSynth workload.
        test_drives
             List of drive objects that is to be tested.
        lm_enabled_drives
             List of drives that support latency monitor.
        """
        if lm_enabled_drives is None:
            lm_enabled_drives = []
        AutovalLog.log_info(
            f"synth verification running on {synth_workload} with drives {test_drives}..."
        )
        filename = "Workload_Loop_Targets.json"
        for drive in test_drives:
            if hasattr(drive, "is_ocp_2_6_drive"):
                if drive.is_ocp_2_6_drive():
                    filename = "Workload_Loop_Targets_OCP2.6.json"
                    break
        cfg_dir = "cfg"
        relative_cfg_file_path = os.path.join(cfg_dir, filename)
        benchmark_dict = GenericUtils.read_resource_cfg(
            file_path=relative_cfg_file_path, module="autoval_ssd"
        )
        csv_files = ""
        fio_results_dir = FioSynthFlashUtils.find_file_paths(
            host, results_dir, file_extension=""
        )
        global_target = ""
        if re.search(r".Workload_loop", synth_workload):
            global_target = re.sub(r".Workload_loop", "_Global", synth_workload)
        else:
            global_target = synth_workload + "_Global"
        AutovalLog.log_info(
            "[%s]: global_target %s synth_workload" % (global_target, synth_workload)
        )
        # try to find the results dir with time-stamp
        for fio_load_dir in fio_results_dir:
            if FileActions.exists(fio_load_dir, host=host):
                if "nvme" in fio_load_dir:
                    match = re.search(r"(nvme\d+n\d+)", fio_load_dir)
                    if match:
                        drive = match.group(0)
                    else:
                        raise TestError(
                            "NVMe drive block name not in dir: %s" % fio_load_dir,
                            component=COMPONENT.STORAGE_DRIVE,
                            error_type=ErrorType.TOOL_ERR,
                        )
                else:
                    # TODO: Need to add SATA/SAS drive output verification
                    raise TestError(
                        "Not supported for SATA/SAS drive output verification",
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.TOOL_ERR,
                    )
                verify_workload = False
                for drive_obj in test_drives:
                    if drive_obj.block_name == drive:
                        verify_workload = drive_obj.get_workload_target_status()
                        break
                # try to find the CSV verification file
                csv_files = FioSynthFlashUtils.find_file_paths(
                    host, fio_load_dir, file_extension=".csv"
                )
                if len(csv_files):
                    csv_file = csv_files[0]
                else:
                    raise TestError(
                        "Can't find CSV file in this dir: %s" % fio_load_dir,
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.TOOL_ERR,
                    )
                output_json_files = FioSynthFlashUtils.find_file_paths(
                    host, fio_load_dir, file_extension=".json"
                )
                csv_list = FileActions.read_data(csv_file, csv_file=True, host=host)
                if csv_list:
                    for index in range(len(output_json_files)):
                        # check for synthload in benchmark dict.
                        try:
                            if benchmark_dict[synth_workload]:
                                FioSynthFlashUtils.compare_csv_json(
                                    host,
                                    global_target,
                                    synth_workload,
                                    benchmark_dict,
                                    csv_list[index],
                                    drive,
                                    verify_workload,
                                    lm_enabled_drives,
                                )
                        except KeyError:
                            msg = "Synthload %s is not available in the benchmark dict"
                            raise TestError(msg % synth_workload)
            else:
                raise TestError(
                    "[synth_verify]: This synthload result dir is not avialble: %s"
                    % fio_load_dir,
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.TOOL_ERR,
                )

    @staticmethod
    def compare_csv_json(
        host,
        global_target: str,
        synth_workload: str,
        benchmark_dict: Dict[str, Dict],
        csv_dict: Dict,
        drive: str,
        verify_workload: bool,
        lm_enabled_drives: Optional[List[str]] = None,
    ) -> None:
        """Compare CSV Json.

        Compare each fio load output with target json reference value.

        Parameters
        ----------
        global_target
            Benchmark dict key that references to target values for drives that have lower performance expectations.
        synth_workload
            FioSynth workload.
        benchmark_dict
            Reference target value.
        csv_dict
            The csv output data.
        drive
            The drive name eg: nvme0n1.
        verify_workload
            True if workload targets are to be validated.
        lm_enabled_drives
            List of drives that support latency monitor
        """
        if lm_enabled_drives is None:
            lm_enabled_drives = []
        if "precondition" in csv_dict["Jobname"]:
            AutovalLog.log_info(
                "[%s]: Precondition output verification is skipped" % drive
            )
            return None
        # TODO: T119547981
        # Skipping BurstTrim validation.
        elif "BurstTrim" in csv_dict["Jobname"]:
            AutovalLog.log_info(
                "[%s]: BurstTrim output verification is skipped" % drive
            )
            return None
        else:
            # FIO work load.
            # eg: If Jobname is 4K_L2R6DWPD_wTRIM_run1, just removed "_run1" part.
            fio_load = re.sub(r".run\d", "", csv_dict["Jobname"])
            verification_fields = {}
            try:
                if verify_workload:
                    verification_fields = benchmark_dict[synth_workload][fio_load]
                else:
                    verification_fields = benchmark_dict[synth_workload][global_target]
            except KeyError:
                AutovalLog.log_info(
                    "[synth_verify]:This fio load does not have comparison data:%s"
                    % fio_load
                )
            AutovalLog.log_info(
                f"{drive}: The {verify_workload} verify_workload synth Verification output:  {fio_load}"
            )
            # checking dict is not empty
            if not len(verification_fields) and synth_workload == "TrimRate":
                AutovalLog.log_info(
                    f"{drive}: The {verify_workload} verify_workload synth Verification output:  {fio_load}"
                    "{synth_verify]: Fio load verification fields is empty: "
                )
                return None
            if not len(verification_fields) and synth_workload != "TrimRate":
                raise TestError(
                    "[synth_verify]: Fio load verification fields is empty:%s "
                    % fio_load,
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.INPUT_ERR,
                )
            AutovalLog.log_info(
                "[%s]: The synth Verification output:  %s" % (drive, fio_load)
            )
            tb_target_scaling_factor = FioSynthFlashUtils.get_tb_target_scaling_factor(
                host, drive
            )

            for k in verification_fields.keys():
                warning = False
                metric, bound, is_per_tb = FioSynthFlashUtils.parse_verification_key(k)
                if metric not in csv_dict:
                    continue
                if drive in lm_enabled_drives and "latency" in k.lower():
                    warning = True

                if bound == "MIN":
                    mult = tb_target_scaling_factor if is_per_tb else 1.0
                    fio_op_val = float(csv_dict[metric])
                    AutovalUtils.validate_greater(
                        fio_op_val,
                        float(verification_fields[k].split(">")[1]) * mult,
                        msg=f"[{drive}]: {k}",
                        warning=warning,
                        raise_on_fail=False,
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.SYSTEM_ERR,
                    )
                elif bound == "MAX":
                    fio_op_val = (
                        0.0 if csv_dict[metric] == "na" else float(csv_dict[metric])
                    )
                    AutovalUtils.validate_less(
                        fio_op_val,
                        float(verification_fields[k].split("<")[1]),
                        msg=f"[{drive}]: {k}",
                        warning=warning,
                        raise_on_fail=False,
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.DRIVE_ERR,
                    )
                else:
                    raise TestError(
                        "[synth_verify]: Substring 'MIN' or 'MAX' is not provided",
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.INPUT_ERR,
                    )

    @staticmethod
    def parse_verification_key(key: str) -> Tuple[str, str, bool]:
        key, bound = key.rsplit("_", 1)
        if bound not in {"MAX", "MIN"}:
            raise Exception(f"Unexpected bound '{bound}' in key '{key}'")
        result = key.rsplit("_PER_TB", 1)
        is_per_tb = len(result) == 2
        return (key, bound, is_per_tb)

    @staticmethod
    def find_file_paths(host: Host, results_dir: str, file_extension: str) -> List[str]:
        """Return a list of paths matching file extension provided.

        Note:  If file extension isn't one of the following, then *all* files will be returned:
          .json
          .csv
          .log
          .txt
        """
        files = FileActions.ls(results_dir, host=host)
        if file_extension in (".csv", ".json", ".log", ".txt"):
            return [
                os.path.join(results_dir, _file)
                for _file in files
                if _file.endswith(file_extension)
            ]
        else:
            return [os.path.join(results_dir, _file) for _file in files]

    @staticmethod
    def setup_synth_resultdir(host, resultsdir):
        """
        Setup the path for result directory for fio_synth result files.
        If the path already exists, then do not try to create.
        Step 1: Create full string for the target filepath
        Step 2: If already exists, do nothing. Else, create the path
        Step 3: Store the target path into self.synth_result_dir variable
        """
        synth_result_dir = os.path.join(resultsdir, "FioSynthFlash")
        AutovalLog.log_info("Creating FioSynthFlash directory %s" % synth_result_dir)
        if not FileActions.exists(synth_result_dir, host=host):
            FileActions.mkdirs(synth_result_dir, host=host)
        return synth_result_dir

    @staticmethod
    def csv_into_resultjson(results_dir: str, work_load: str) -> None:
        """Stores CSV output in test result json.

           This method gets each synth workload IOPS/latency output
           from csv file and stores it in test_result.json.

        Parameters
        -----------
        results_dir: String
             Master result directory of synth load.
        synth_workload: String
             FioSynth workload.
        """
        # Find all CSV file from master log folder
        all_csv_files = glob(results_dir + "/*/*.csv")
        for csv_file in all_csv_files:
            # Filter the work_load files
            if work_load in csv_file:
                csv_list = FileActions.read_data(csv_file, csv_file=True)
                # Find each drive results string
                match = re.search(r"%s\w+" % work_load, csv_file)
                if match:
                    result_for_drive = match.group()
                else:
                    raise TestError(
                        "%s not in CSV Files: %s" % (work_load, csv_file),
                        component=COMPONENT.SYSTEM,
                        error_type=ErrorType.SYSTEM_ERR,
                    )
                fiosynth_result = {result_for_drive: csv_list}
                # Add Fiosynth results in test_results.json file
                AutovalUtils.result_handler.add_test_results(fiosynth_result)

    @staticmethod
    def get_tb_target_scaling_factor(host: "Host", drive: str) -> float:
        """
        Get target scaling factor of the drive based on its capacity in TB.
        Parameters
        ------------
        host: Host
            Host object to run commands on.
        drive: str
            Drive name.
        Returns
        ------------
        scaling_factor: float
            Scaling factor for drive targets based on drive capacity in TB.
            The scaling factor is the drive capacity in TB rounded down to 2 decimal places.
            The scaling factor is 1.0 if capacity not found or if capacity is lower than 1TB.
        """
        scaling_factor = 1.0
        capacity_out = host.run(
            f"sudo smartctl -i -H /dev/{drive} | grep -i 'total nvm capacity'"
        )
        match = re.match(r"Total NVM Capacity:\s+([\d,]+)", capacity_out)
        if match:
            cap = float(match.group(1).replace(",", ""))
            cap_tb = round(cap / pow(10, 12), 2)
            scaling_factor = max(cap_tb, 1.0)
        return scaling_factor
