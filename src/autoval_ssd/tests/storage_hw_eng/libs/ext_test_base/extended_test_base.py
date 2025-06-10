# pyre-unsafe
import concurrent.futures
import copy
import itertools
import pathlib
import pkgutil
import re
import sys
import time
import typing as t

from autoval.lib.host.host import Host
from autoval.lib.test_base import TestBase
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.site_utils import SiteUtils
from autoval_ssd.lib.utils.storage.drive import Drive
from autoval_ssd.lib.utils.system_utils import get_serial_number, SystemUtils
from autoval_ssd.tests.storage_hw_eng.libs.data_types.sensor_data import SensorData

from .background_polling import BackgroundPoll, BackgroundPollingDriver
from .tasks import TestTask


class ExtendedTestBase(TestBase):
    """
    Extended Test Base.
    """

    def __init__(self, *args, inputT, outputT, **kwargs):
        super().__init__(*args, **kwargs)
        self.inputT = inputT
        self.outputT = outputT
        self.test_drives: t.List[Drive] = []
        self._temp_dirs_to_clean: t.List[t.Tuple[Host, str]] = []

    def setup(self, init_bg_polling: bool = False, config_check: bool = True, **kwargs):
        """
        Setup for the Tests.
        """

        # Check if we are in debug mode
        self._debug = True if "DEBUG" in self.test_control else False

        if self._debug:
            if "config_check" in kwargs:
                del kwargs["config_check"]
            super().setup(config_check=False, **kwargs)
        else:
            super().setup(**kwargs)

        # Load in input parameters
        self.input_params = self.inputT.from_dict(self.test_control)
        self.output = self.outputT()
        self.output.input_params = self.input_params

        # Init background polling if Specified #
        self.bg_polling_driver = None
        if init_bg_polling:
            self._setup_background_polling()

    def cleanup(self, **kwargs):
        """
        Cleanup the test.
        """

        # Cleanup bg polling if exists.
        self._cleanup_background_polling()

        # Archive test results before cleanup
        self._archive_to_resultsdir()

        # Cleanup all of the temp directories
        self._cleanup_all_temp_dirs()

        # Write output
        if hasattr(self, "output"):
            self.log_info("Writing output.")
            self.result_handler.add_test_results(self.output.to_serializable())

        # Call super with if are any kwargs
        if self._debug:
            if "config_check" in kwargs:
                del kwargs["config_check"]
            super().cleanup(config_check=False, **kwargs)
        else:
            super().cleanup(**kwargs)

    ## Functions to Run Command in Background ##

    def create_bg_cmd_task(
        self, cmd: str, host: t.Optional[Host] = None, outfile: str = "/dev/null"
    ):
        host = self._default_host_if_none(host)

        return TestTask(
            func=self.remote_bg_execute,
            args=(cmd),
            kwargs={"host": host, "outfile": outfile},
        )

    def remote_bg_execute(
        self,
        cmd: str,
        host: t.Optional[Host] = None,
        outfile: str = "/dev/null",
        ignore_status: bool = False,
    ):
        """
        Execute a command remotely in the background.
        """

        host = self._default_host_if_none(host)

        return host.run(
            f"nohup {cmd} > {outfile} 2>&1 & echo $!", ignore_status=ignore_status
        )

    def chk_bg_process(self, pid: int, host: t.Optional[Host] = None):
        """
        Check a background process exists.
        """
        host = self._default_host_if_none(host)

        try:
            output = host.run(f"kill -0 {pid} > /dev/null && echo TRUE")
            return "TRUE" in output
        except Exception as e:
            self.log_error(
                f"Failed to check pid {pid} on host {host.hostname}. {type(e)} : {e}"
            )
            return False

    def kill_remote_process(
        self,
        pid: int,
        host: t.Optional[Host] = None,
        kill_decendents: bool = True,
        ignore_status: bool = True,
    ):
        """
        Kill a remote process via PID
        """

        host = self._default_host_if_none(host)

        if kill_decendents:
            return host.run(f"pkill -9 -P {pid}", ignore_status=ignore_status)

        return host.run(f"kill -9 {pid}", ignore_status=ignore_status)

    ## System Info ##
    def chk_host_runtime(
        self, host: Host, pkgs: t.List, ret_bool: bool = True, verbose: bool = True
    ) -> t.Union[bool, t.List[str]]:
        """
        Checks if the runtime contains certain packages.

        Params:
            host (Host):
                The host to check the runtime of.
            pkgs (List[Union[str, re.Pattern]]):
                The packages to check on the system.
            ret_bool (bool):
                Return a boolean representing if all packages exist.
            verbose (bool):
                Log to info.

        Returns:
            (Union[bool, List[Union[str, re.Match]]]) If ret_bool is set, will
            return if all packages are installed. Otherwise will return a list of
            packages which are missing.
        """
        req_pkgs = set(pkgs[:])

        # Get all installed pkgs
        pkg_mgr = SystemUtils.get_pkg_mgr(host)
        output_lines = host.run(f"{pkg_mgr} list installed")
        all_pkgs = [
            tuple(re.findall("[^ ]+", line))
            for line in output_lines.split("\n")
            if line != "Installed Packages"
        ]

        # Go through all install pkgs
        for pkg_entry in all_pkgs:
            if len(pkg_entry) == 3:
                name, _ver, _group = pkg_entry
                for pkg_name in set(pkgs[:]):
                    if isinstance(pkg_name, type(re.compile(""))):
                        # Remove if substring and the pkg has not been accounted for yet.
                        if (pkg_name.search(name) is not None) and (
                            pkg_name in req_pkgs
                        ):
                            req_pkgs.remove(pkg_name)
                    else:
                        # Remove if substring and the pkg has not been accounted for yet.
                        if (pkg_name in name) and (pkg_name in req_pkgs):
                            req_pkgs.remove(pkg_name)

        if verbose:
            if len(req_pkgs) == 0:
                self.log_info(
                    f"Host {host.hostname} contains all necessary runtimes for this test."
                )
            else:
                pkg_list_str = ",".join(req_pkgs)
                self.log_error(
                    f"Host {host.hostname} does not possess the following pkgs: {pkg_list_str}"
                )

        if ret_bool:
            return len(req_pkgs) == 0
        return list(req_pkgs)

    ## Telemetry Info ##

    def poll_sensor_data(self, host: t.Optional[Host] = None) -> SensorData:
        """
        Poll sensor data from the BMC
        """

        host = self._default_host_if_none(host)

        sensor_info = host.oob.all_sensor_data()
        return SensorData.parse_from_bmc_sensor_util(sensor_info)

    ## Task Running ##
    def run_task_sequence(self, tasks: t.Iterator[TestTask], submit_delay: float = 1.0):
        """
        Run tasks in sequence.
        """
        for task in tasks:
            task.run()
            time.sleep(submit_delay)

        results = [
            (x.result, x) if x.exception is None else (x.exception, x) for x in tasks
        ]

        return results

    def run_task_pool(
        self,
        tasks: t.Iterator[TestTask],
        max_workers: t.Optional[int] = None,
        submit_delay: float = 1.0,
    ):
        """
        Run tasks in a pool.
        """
        all_submitted_tasks = []
        unsubmitted = list(tasks)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            while len(unsubmitted) > 0:
                # Check that the task should be run.
                task = unsubmitted.pop()
                in_progress = [t for _, t in all_submitted_tasks]
                if task.can_run(in_progress, unsubmitted):
                    all_submitted_tasks.append((executor.submit(task.run), task))
                    time.sleep(submit_delay)
                else:
                    unsubmitted.append(task)

            concurrent.futures.wait([future for future, _ in all_submitted_tasks])

        # Process Results
        results = []
        for future, task in all_submitted_tasks:
            # If there is an exception in the future -> Log to the task.
            if future.exception() is not None:
                task.exception = future.exception()
                task.traceback = "Exception during pooled run future."
            results.append(
                (task.result, task)
                if task.exception is None
                else (task.exception, task)
            )

        return results

    def run_task_swept_kwargs(
        self,
        *,
        task: TestTask,
        groups: t.Dict[str, t.Iterable],
        max_workers: t.Optional[int] = None,
        submit_delay: float = 1.0,
        pool: bool = True,
    ):
        """
        Runs Tasks where the kwargs are swept.

        Params:
            task (Task):
                The task to run.
            groups (Dict[str, Iterable]):
                A dictionary of kwarg to a list of values to sweep over.
            max_workers (int, Optional):
                Maximum number of workers. (Pool run only)
            submit_delay (float):
                Delay between each submission. Defaults to 1.0s.
            pool (bool):
                Run in a pool. Defaults to True.

        Returns:
            Results from running all tasks.
        """
        items = groups.items()
        labels = [name for name, g in items]

        def generator(task, groups):
            for e in itertools.product(*(group for n, group in items)):
                kwargs = copy.deepcopy(task.kwargs)
                kwargs.update(dict(zip(labels, e)))

                yield TestTask(func=task.func, args=task.args, kwargs=kwargs)

        if pool:
            return self.run_task_pool(
                generator(task, groups),
                max_workers=max_workers,
                submit_delay=submit_delay,
            )
        else:
            return self.run_task_sequence(
                generator(task, groups), submit_delay=submit_delay
            )

    def operate_on_hosts(
        self,
        *,
        task: TestTask,
        hosts: t.Iterable[Host],
        max_workers: t.Optional[int] = None,
        submit_delay: float = 1.0,
    ):
        """ """
        return self.run_task_swept_kwargs(
            task=task,
            groups={"host": hosts},
            max_workers=max_workers,
            submit_delay=submit_delay,
        )

    ## Background ##

    def create_background_polling_task(
        self,
        task: TestTask,
        inter_poll_time: float,
        total_polling_period: float = 60.0,
        run_indefinately: bool = False,
    ):
        """
        Generate a BG polling task from a Task
        """

        submission = BackgroundPoll(
            function=task.func,
            args=task.args,
            kwargs=task.kwargs,
            inter_poll_time=inter_poll_time,
            total_polling_period=total_polling_period,
            run_indefinately=run_indefinately,
        )

        return submission

    def submit_background_polling_task(self, bg_poll_task: BackgroundPoll):
        """
        Submit a BG polling task.

        Returns:
        True if successfully submitted, False otherwise.
        """
        if hasattr(self, "bg_polling_driver"):
            if self.bg_polling_driver is not None:
                self.bg_polling_driver.submit(bg_poll_task)
                return True
        return False

    def restart_background_polling(self):
        """
        Restarts background polling. This clears the background tasks!
        """
        self._cleanup_background_polling()
        self._setup_background_polling()

    def _setup_background_polling(self):
        """ """
        # Create background event queue and start background polling.

        self.log_info("Starting Background Polling Loop")
        self.bg_polling_driver = BackgroundPollingDriver()
        self.bg_polling_driver.start()

    def _cleanup_background_polling(self):
        """ """
        # Stop all background polling
        if hasattr(self, "bg_polling_driver"):
            if self.bg_polling_driver is not None:
                self.log_info("Stopping Background Polling Loop")
                self.bg_polling_driver.stop()

    ## Temp Directory ##
    def create_timestamp(self) -> str:
        """
        Creates a timestamp based on the current system time.
        """
        timestamp = time.localtime()
        return (
            f"{timestamp.tm_mon:02d}{timestamp.tm_mday:02d}"
            + f"{timestamp.tm_hour:02d}{timestamp.tm_min:02d}"
        )

    def create_temp_directory(
        self,
        host: t.Optional[Host] = None,
        temp_dir: t.Optional[t.Any] = None,
        rm_first: bool = False,
        clean: bool = True,
    ) -> t.Tuple[bool, str]:
        """
        Creates a temp. directory on a host.

        Params:
            host (Host):
                The host to create the temp directory on.
            temp_dir (str, optional):
                Specifies the path for the temp directory. If unspecified,
                the name scheme is based on time so that it is unique.
            clean (bool, optional):
                Clean the temp directory on exit.

        Returns:
            The path to the remote directory. None if the creation failed.
        """

        host = self._default_host_if_none(host)

        if temp_dir is None:
            remote_tmp_dir = self.dut_logdir[self.host.hostname]
        else:
            remote_tmp_dir = temp_dir

        self.log_info(
            f"Creating remote temp directory {remote_tmp_dir} on {host.hostname}"
        )

        if not hasattr(self, "_temp_dirs"):
            self._temp_dirs = []

        try:
            if rm_first:
                host.run(f"mkdir -rf {remote_tmp_dir}")
            host.run(f"mkdir -p {remote_tmp_dir}")
            self._temp_dirs.append((host, remote_tmp_dir))
            if clean:
                self._temp_dirs_to_clean.append((host, remote_tmp_dir))
        except Exception:
            return (False, remote_tmp_dir)

        return (True, remote_tmp_dir)

    def create_multiple_temp_subdir(
        self,
        main_folder: t.Union[str, pathlib.Path],
        folder_names: t.List[str],
        host: t.Optional[Host] = None,
        clean: bool = True,
    ):
        """
        Create all results directories
        """
        success = True
        host = self._default_host_if_none(host)
        main_folder = (
            pathlib.Path(main_folder) if isinstance(main_folder, str) else main_folder
        )

        results_dirs = {}
        for name in folder_names:
            drive_result_dir = main_folder / pathlib.Path(name)
            folder_success, remote_drive_result_dir = self.create_temp_directory(
                self.host, temp_dir=drive_result_dir
            )
            if not folder_success:
                success = False
            results_dirs[name] = pathlib.Path(remote_drive_result_dir)

        return (success, results_dirs)

    def _archive_to_resultsdir(self):
        """
        Archive test results to manifold
        """
        for host, tmp_dir in self._temp_dirs_to_clean:
            try:
                serial_number = get_serial_number("baseboard", self.host)
            except Exception:
                AutovalLog.log_info("Unable to get the serial number")
                serial_number = None

            is_dut_log_empty = SiteUtils._is_dir_empty(host, tmp_dir)
            if not is_dut_log_empty:
                SiteUtils._archive_to_resultsdir(
                    host,
                    tmp_dir,
                    f"dut_logs-{serial_number if serial_number not in ['N/A', ' ', None] else host.hostname}.tgz",
                )

    def _cleanup_all_temp_dirs(self):
        """
        Clean all temp directories.
        """

        for host, tmp_dir in self._temp_dirs_to_clean:
            self._cleanup_temp_directory(host, tmp_dir)

    def _cleanup_temp_directory(self, host: Host, remote_tmp_dir: str):
        """
        Cleans up a temp directory
        """
        self.log_info(
            f"Removing remote temp folder {remote_tmp_dir} on {host.hostname}"
        )
        host.run(f"rm -rf {remote_tmp_dir}", ignore_status=True)

    ## Helper Functions ##

    def _default_host_if_none(self, host: t.Optional[Host]):
        return self.host if host is None else host

    def _vlog_info(self, *args, verbose, **kwargs):
        if verbose:
            self.log_info(*args, **kwargs)

    def _vlog_warning(self, *args, verbose, **kwargs):
        if verbose:
            self.log_warning(*args, **kwargs)

    def _vlog_error(self, *args, verbose, **kwargs):
        if verbose:
            self.log_error(*args, **kwargs)

    def get_pkg_data(
        self,
        resource,
        package: t.Optional[str] = None,
        raise_if_error: bool = False,
        encode: t.Optional[str] = None,
        verbose: bool = False,
    ) -> t.Optional[t.Union[str, bytes]]:
        """
        Get data from a package.

        Params:
            resource (str):
                The resource path from the package root.
            package (t.Optional[str], optional):
                The package (in dot notation) to get data from. Defaults to the package of the module
                from which this was called from.
            raise_if_error (bool, optional):
                Raise error if an error occurs during loading or ntohing was loaded.
            encode (t.Optional[str], optional):
                Encode the string using an encoding. None returns raw bytes.
            verbose (bool):
                Log operations.

        Returns:
            None if nothing loaded. If encoding specified, the data in that encoding. Otherwise
            will return the raw bytes.
        """

        # Somewhat crazy introspection
        if package is None:
            module = self.__class__.__module__
            package = ".".join(module.split(".")[:-1])

        pkg_str = f"{resource} from pkg {package}"
        self._vlog_info(f"Attempting to get resource {pkg_str}.", verbose=verbose)

        # Try to get data
        try:
            data = pkgutil.get_data(package, resource)
        except Exception as e:
            msg = f"Error while retrieving resource {pkg_str}!"
            self._vlog_info(msg, verbose=verbose)
            if raise_if_error:
                raise e
            return None

        # Check if data is None
        if data is None:
            msg = f"Failed to read resource {pkg_str}!"
            self._vlog_info(msg, verbose=verbose)
            if raise_if_error:
                raise IOError(msg)
            return None

        # Check if need to encode.
        if encode is not None:
            try:
                return str(data, encode)
            except Exception as e:
                msg = f"Failed to decode resource {pkg_str}!"
                self._vlog_info(msg, verbose=verbose)
                if raise_if_error:
                    raise e
                return None

        return data

    # Debugging functions
    @staticmethod
    def _print_err(*args, **kwargs):
        """
        Print to std error.
        """
        print(*args, file=sys.stderr, **kwargs)
