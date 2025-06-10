# pyre-unsafe
import typing as t

from ..data_record.data_record import datarec, DictConstructable, item


def _str_to_list(val):
    if isinstance(val, str):
        return [val]
    return val


@datarec
class FBSynthFlashInput(DictConstructable):
    """
    Represents the input to a fio job.
    """

    devices = item(
        data_type=t.List[str],
        keyword="devices",
        converter=_str_to_list,
        docstr="The devices to run on.",
    )

    workload_suite = item(
        data_type=str, keyword="workload_suite", docstr="The workload_suite to run."
    )

    result_filename_prefix = item(
        data_type=str,
        keyword="result_filename_prefix",
        docstr="The result filename prefix.",
    )

    capacity = item(
        data_type=t.Optional[float],
        keyword="capacity",
        default=None,
        docstr="Capacity to run on for the drive.",
    )

    dry_run = item(
        data_type=t.Optional[bool],
        keyword="dry_run",
        default=None,
        docstr="Perform a dry run.",
    )

    health_monitoring = item(
        data_type=t.Optional[str],
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

    servers = item(
        data_type=t.List[str],
        keyword="servers",
        factory=list,
        docstr="Server for workload to run on.",
    )

    server_file = item(
        data_type=t.Optional[str],
        keyword="server_file",
        default=None,
        docstr="File with servers to run on.",
    )

    def __init__(
        self,
        devices=devices,
        workload_suite=workload_suite,
        result_filename_prefix=result_filename_prefix,
        capacity=capacity,
        dry_run=dry_run,
        health_monitoring=health_monitoring,
        skip_drive_prep=skip_drive_prep,
        num_runs=num_runs,
        flash_config_logging=flash_config_logging,
        servers=servers,
        server_file=server_file,
    ):
        devices = devices
        workload_suite = workload_suite
        result_filename_prefix = result_filename_prefix
        capacity = capacity
        dry_run = dry_run
        health_monitoring = health_monitoring
        skip_drive_prep = skip_drive_prep
        num_runs = num_runs
        flash_config_logging = flash_config_logging
        servers = servers
        server_file = server_file

    def to_cmd(self, binary="fiosynth"):
        """
        Generate the fiosynth command reflecting these input params.
        """

        def _y_n_bool(b: bool):
            return "y" if b else "n"

        def _create_option(val, opt: str, func: t.Optional[t.Callable] = None):
            if val is not None:
                if func is None:
                    return f" {opt} {val}"
                else:
                    return f" {opt} {func(val)}"
            else:
                return ""

        device_str = ":".join(self.devices)
        options = (
            f"-d {device_str} -w {self.workload_suite} -f {self.result_filename_prefix}"
        )
        capacity_op = _create_option(self.capacity, "-c")
        dry_run_op = _create_option(self.dry_run, "-r", func=_y_n_bool)
        health_monitoring_op = _create_option(self.health_monitoring, "-t")
        skip_drive_prep_op = _create_option(self.skip_drive_prep, "-p", func=_y_n_bool)
        num_runs_op = _create_option(self.num_runs, "-n")
        flash_config_logging_op = _create_option(
            self.flash_config_logging, "-g", func=_y_n_bool
        )
        servers_op = "".join([_create_option(server, "-s") for server in self.servers])
        server_file_op = _create_option(self.server_file, "-l")

        optional_ops = "".join(
            [
                capacity_op,
                dry_run_op,
                health_monitoring_op,
                skip_drive_prep_op,
                num_runs_op,
                flash_config_logging_op,
                servers_op,
                server_file_op,
            ]
        )

        return f"{binary} {options} {optional_ops}"
