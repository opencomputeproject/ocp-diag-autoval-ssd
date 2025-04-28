# pyre-unsafe
"""
.. fb:display_title::
  fio data

This includes the Data Records for fio input and output.
"""

import configparser
import copy
import enum
import itertools
import typing as t

from ..data_record.data_record import datarec, DictConstructable, item
from ..data_record.data_record_enum import enum_serial
from ..data_record.serial_type import Serializable
from ..data_size import DataSize

FioString = str
FioFloatList = str
FioInt = DataSize


class FioTime(FioInt):
    def __init__(self, i, *args, **kwargs):
        # Remove any second annotation
        if str(i).endswith("s") or str(i).endswith("S"):
            super().__init__(str(i)[:-1], *args, **kwargs)
        else:
            super().__init__(i, *args, **kwargs)

    def __new__(cls, i, *args, **kwargs):
        # Remove any second annotation
        if str(i).endswith("s") or str(i).endswith("S"):
            return super().__new__(cls, str(i)[:-1], *args, **kwargs)
        else:
            return super().__new__(cls, i, *args, **kwargs)


@enum_serial(by_name=False)
class FioReadWriteType(enum.Enum):
    """
    Represents the acceptable I/O patterns.
    """

    READ = "read"  # Sequential Reads
    WRITE = "write"  # Sequential Writes
    TRIM = "trim"  # Sequential Trims
    RAND_RD = "randread"  # Random Reads
    RAND_WR = "randwrite"  # Random Writes
    RAND_TRIM = "randtrim"  # Random Trims
    RW = "readwrite"  # Seqential mixed RW
    RAND_RW = "randrw"  # Random mixed RW
    TRIM_WRITE = "trimwrite"  # Sequntial Trim + Write


class FioBool(Serializable):
    """
    Represents an boolean for fio
    """

    def __init__(self, boolean):
        # Special string conversion case.
        if isinstance(boolean, str):
            if boolean.strip().upper() == "FALSE":
                self.boolean = False
            else:
                self.boolean = True
        else:
            self.boolean = bool(boolean)

    def __bool__(self):
        return self.boolean

    def __str__(self):
        if self.boolean:
            return "1"
        else:
            return "0"


class FioToggle(FioBool):
    def __str__(self):
        if self.boolean:
            return "1"
        else:
            return "None"


@datarec
class FioJobInputParams(DictConstructable):
    """
    Represents the input to a fio job.
    """

    ## Job Description ##

    name = item(
        data_type=t.Optional[FioString],
        keyword="name",
        default=None,
        docstr="The name of the job.",
    )

    description = item(
        data_type=t.Optional[FioString],
        keyword="description",
        default=None,
        docstr="The description of the job.",
    )

    loops = item(
        data_type=t.Optional[FioInt],
        keyword="loops",
        default=None,
        docstr="Number of loops for the job.",
    )

    numjobs = item(
        data_type=t.Optional[FioInt],
        keyword="numjobs",
        default=None,
        docstr="Number of clones of this job.",
    )

    ## Time Related Parameters ##

    runtime = item(
        data_type=t.Optional[FioTime],
        keyword="runtime",
        default=None,
        docstr="Runtime for the process.",
    )

    time_based = item(
        data_type=t.Optional[FioToggle],
        keyword="time_based",
        default=None,
        docstr="Set to make the test time based.",
    )

    ramp_time = item(
        data_type=t.Optional[FioTime],
        keyword="ramp_time",
        default=None,
        docstr="The ramptime for the job.",
    )

    ## Target File / Device ##

    filename = item(
        data_type=t.Optional[FioString],
        keyword="filename",
        default=None,
        docstr="The file to run FIO on.",
    )

    allow_file_create = item(
        data_type=t.Optional[FioBool],
        keyword="allow_file_create",
        default=None,
        docstr="Whether or not to allow the file to be created.",
    )

    ## I/O Type ##

    direct = item(
        data_type=t.Optional[FioBool],
        keyword="direct",
        default=None,
        docstr="Whether or not to use non-buffered I/O.",
    )

    readwrite = item(
        data_type=t.Optional[FioReadWriteType],
        keyword=("readwrite", "rw"),
        default=None,
        docstr="Type of I/O pattern.",
    )

    randrepeat = item(
        data_type=t.Optional[FioBool],
        keyword="randrepeat",
        default=None,
        docstr="Seed the RNG in predictable wai.",
    )

    norandommap = item(
        data_type=t.Optional[FioToggle],
        keyword="norandommap",
        default=None,
        docstr="If set, will get a random offset w/o looking at past history.",
    )

    ## Block Size ##
    blocksize = item(
        data_type=t.Optional[FioInt],
        keyword=("blocksize", "bs"),
        default=None,
        docstr="The Blocksize for the job.",
    )

    blockalign = item(
        data_type=t.Optional[FioInt],
        keyword="blockalign",
        default=None,
        docstr="Boundary to align random I/O units.",
    )

    ## Buffers and Memory ##
    invalidate = item(
        data_type=t.Optional[FioToggle],
        keyword="invalidate",
        default=None,
        docstr="Invalidate the buffer/page cache parts of the"
        + "files to be used prior to starting I/O.",
    )

    ## I/O Size ##

    ## I/O Engine ##

    ioengine = item(
        data_type=t.Optional[FioString],
        keyword="ioengine",
        default=None,
        docstr="The ioengine for the job.",
    )

    scramble_buffers = item(
        data_type=t.Optional[FioBool],
        keyword="scramble_buffers",
        default=None,
        docstr="Scramble the buffers.",
    )

    ## I/O Engine Specific Parameters ##

    ## I/O Depth ##
    iodepth = item(
        data_type=t.Optional[FioInt],
        keyword="iodepth",
        default=None,
        docstr="The number of I/O units to keep in flight.",
    )

    iodepth_batch_submit = item(
        data_type=t.Optional[FioInt],
        keyword="iodepth_batch_submit",
        default=None,
        docstr="How many pieces of I/O to submit at once.",
    )

    iodepth_batch_complete = item(
        data_type=t.Optional[FioInt],
        keyword="iodepth_batch_complete",
        default=None,
        docstr="How many pieces of I/O to retrieve at once.",
    )

    ## Measurements and reporting ##
    per_job_logs = item(
        data_type=t.Optional[FioBool],
        keyword="per_job_logs",
        default=None,
        docstr="Log by job vs aggregate.",
    )

    group_reporting = item(
        data_type=t.Optional[FioToggle],
        keyword="group_reporting",
        default=None,
        docstr="See final report by group rather than per job.",
    )

    percentile_list = item(
        data_type=t.Optional[FioFloatList],
        keyword="percentile_list",
        default=None,
        docstr="Overwrite default list of percentiles for latencies.",
    )

    write_bw_log = item(
        data_type=t.Optional[FioString],
        keyword="write_bw_log",
        default=None,
        docstr="Write BW Log.",
    )

    write_lat_log = item(
        data_type=t.Optional[FioString],
        keyword="write_lat_log",
        default=None,
        docstr="Write latency logs.",
    )

    ## Error Handling ##

    ## Cmd Line Options ##

    output = item(
        data_type=t.Optional[FioString],
        keyword="output",
        default=None,
        docstr="The output filename for the job.",
    )

    output_format = item(
        data_type=t.Optional[FioString],
        keyword=("output-format", "output_format"),
        default=None,
        docstr="The output format.",
    )

    fio_file = item(
        data_type=t.Optional[FioString],
        keyword="fio_file",
        default=None,
        docstr="FIO job file.",
    )

    additional_configs = item(
        data_type=t.Optional[t.Dict[str, t.Any]],
        keyword="additional_configs",
        default=None,
        docstr="Additional configs for fio.",
    )

    @classmethod
    def from_dict(cls, obj_dict: t.Dict, recurse: bool = True):
        """
        Create a FioJobInputParams from a dictionary representing the object.

        Params:
            obj_dict:
                The dictionary representing the FioJobInputParams object.
                All unknown keywords will be added to additional_configs.
            recurse:
                [Optional] Recurse through collection-type data structures.
                Defaults to True.

        Returns:
            An instance of the FioJobInputParams class from the dictionary.
        """
        data = super().from_dict(obj_dict, recurse)

        # Check for additional parameters that are not captured in a field.
        keywords = cls.get_all_valid_keywords()
        additional_items = {k: v for k, v in obj_dict.items() if k not in keywords}

        if data.additional_configs is not None:
            data.additional_configs.update(additional_items)
        else:
            data.additional_configs = additional_items

        return data

    def to_serializable(self) -> t.Any:
        """
        Returns:
        The object in a serializable form.
        """
        return self.to_dict(
            recurse=True, use_keyword=True, serialize=True, remove_val_eq_default=True
        )

    @classmethod
    def create_sweeping_parameters(
        cls, base_fio_params: t.Optional["FioJobInputParams"] = None, **kwargs
    ) -> t.Generator["FioJobInputParams", None, None]:
        """
        Generator for sweeping fio parameters.

        Params:
            base_fio_params (FioJobInputParams, optional)
                The fio params to use as a base while sweeping through other params.

        Yields:
            FioJobInputParams sweeping through different parameters.
        """

        sweep_params = kwargs.items()
        keys = [k for k, _ in sweep_params]

        for sweep_values in itertools.product(*(v for _, v in sweep_params)):
            sweep_params = dict(zip(keys, sweep_values))
            fio_params = cls.from_dict(sweep_params)

            if base_fio_params is not None:
                yield cls.combine(base_fio_params, fio_params)
            else:
                yield fio_params

    @classmethod
    def combine(
        cls, params1: "FioJobInputParams", params2: "FioJobInputParams"
    ) -> "FioJobInputParams":
        """ """
        params_dict = {k: v for k, v in params1.to_dict().items() if v is not None}
        params_dict.update(
            {k: v for k, v in params2.to_dict().items() if v is not None}
        )
        combined = cls.from_dict(params_dict)

        params1_add_config_dict = copy.deepcopy(params1.additional_configs)

        if params1_add_config_dict is not None:
            if combined.additional_configs is None:
                combined.additional_configs = params1_add_config_dict.additional_configs
            else:
                params1_add_config_dict.update(combined.additional_configs)
                combined.additional_configs = params1_add_config_dict

        return combined

    def to_fio_config(self) -> configparser.ConfigParser:
        """
        Converts this FioJobInputParams object to a string
        representing a config file.

        Returns:
        ConfigParser object with information included.
        """
        parser = configparser.ConfigParser()

        # Check for a name and that there is no specified fio file.
        if self.name is None:
            raise TypeError(
                "Field: name is not specified. Needed for creating a config file."
            )
        if self.fio_file is not None:
            raise TypeError(
                "Field: fio_file is specified. Field is not used in fio config files."
            )

        # Add additional configs if they exist.
        if self.additional_configs is not None:
            configs = self.additional_configs
        else:
            configs = {}

        # Go through configurations and add them to the config dict.
        for k, v in self.to_dict(serialize=True).items():
            # Reserved
            if k in ["name", "additional_configs", "fio_file"]:
                continue
            # Else add to the dictionary
            if v is not None:
                configs[k] = v

        parser.read_dict({self.name: configs})

        return parser

    def to_fio_command(self, cmd: str = "fio", options_only: bool = False) -> str:
        """
        Converts this FioJobInputParams object to a fio command.
        Note that empty string values are considered toggle only commands.

        Returns:
        String representing the fio command for this FioJobInputParams.
        """

        if options_only:
            cmd = ""

        config = self.to_dict(serialize=True)
        # Add the additional configs.
        if self.additional_configs is not None:
            config.update(self.additional_configs)
            del config["additional_configs"]

        # Always put name first!
        if config["name"] is not None:
            cmd += f' --name={config["name"]}'

        # Go through configurations.
        for k, v in config.items():
            # Reserved
            if k in ["fio_file", "name"]:
                continue
            # Else add to the dictionary
            if v is not None:
                if v == "":
                    cmd = f"{cmd} --{k}"
                elif v != "None":
                    cmd = f"{cmd} --{k}={v}"

        # If only want options
        if options_only:
            return cmd

        # Add file at end
        return f"{cmd} {self.fio_file}" if self.fio_file is not None else cmd

    @staticmethod
    def create_cmd_from_multiple(
        main_fio: "FioJobInputParams",
        *args,
        cmd: str = "fio",
        options_only: bool = False,
        strict: bool = True,
    ):
        main_fio_params = copy.deepcopy(main_fio)
        indexer = 0

        if options_only:
            cmd = ""

        if main_fio_params.name is None:
            main_fio_params.name = "global"
        cmd = f"{cmd} {main_fio_params.to_fio_command(options_only=True)}"

        for param in args:
            if param.name is None:
                if strict:
                    raise KeyError('Missing "name" for additional fio parameters!')
                param.name = f"unknown_job{indexer}"
                indexer += 1
            cmd = f"{cmd} {param.to_fio_command(options_only=True)}"

        # If only want options
        if options_only:
            return cmd

        # Add file at end
        return (
            f"{cmd} {main_fio_params.fio_file}"
            if main_fio_params.fio_file is not None
            else cmd
        )


@datarec
class FioDiskUtilization(DictConstructable):
    """
    Represents the disk utilization output from FIO.
    """

    in_queue = item(
        data_type=int, keyword="in_queue", docstr="Total time spent in disk queue."
    )

    name = item(data_type=str, keyword="name", docstr="The timestamp in ms.")

    read_ios = item(
        data_type=int,
        keyword="read_ios",
        docstr="Number of read IOs performed by all groups.",
    )

    read_merges = item(
        data_type=int,
        keyword="read_merges",
        docstr="Number of read merges performed by scheduler.",
    )

    read_ticks = item(
        data_type=int,
        keyword="read_ticks",
        docstr="Number of ticks the disk was kept busy for reads.",
    )

    util = item(data_type=int, keyword="util", docstr="The disk utilization.")

    write_ios = item(
        data_type=int,
        keyword="write_ios",
        docstr="Number of write IOs performed by all groups.",
    )

    write_merges = item(
        data_type=int,
        keyword="write_merges",
        docstr="Number of write merges performed by scheduler.",
    )

    write_ticks = item(
        data_type=int,
        keyword="write_ticks",
        docstr="Number of ticks the disk was kept busy for writes.",
    )


@datarec
class FioLatency(DictConstructable):
    """
    Represents latency data in FIO
    """

    lat_max = item(data_type=float, keyword="max", docstr="Maximum latency (ns).")

    lat_mean = item(data_type=float, keyword="mean", docstr="Mean latency (ns).")

    lat_min = item(data_type=float, keyword="min", docstr="Minimum latency (ns).")

    lat_stddev = item(
        data_type=float, keyword="stddev", docstr="Standard Dev. latency (ns)."
    )

    bins = item(
        data_type=t.Optional[t.Dict[int, int]],
        keyword="bins",
        default=None,
        docstr="Mapping of latency bin to number of IO in that bin.",
    )

    percentile = item(
        data_type=t.Optional[t.Dict[float, int]],
        keyword="percentile",
        default=None,
        docstr="Mapping of percentile to time.",
    )


@datarec
class FioReadWriteData(DictConstructable):
    """
    Represents the data for each read write type in a job.
    """

    bw = item(
        data_type=t.Optional[float],
        keyword="bw",
        default=None,
        docstr="Average Bandwidth.",
    )

    bw_agg = item(
        data_type=t.Optional[float],
        keyword="bw_agg",
        default=None,
        docstr="Percent of total bandwidth.",
    )

    bw_bytes = item(
        data_type=t.Optional[int],
        keyword="bw_bytes",
        default=None,
        docstr="Average in bytes.",
    )

    bw_dev = item(
        data_type=t.Optional[float],
        keyword="bw_dev",
        default=None,
        docstr="Std dev of bandwidth samples.",
    )

    bw_max = item(
        data_type=t.Optional[int],
        keyword="bw_max",
        default=None,
        docstr="Maximum bandwidth based on samples.",
    )

    bw_mean = item(
        data_type=t.Optional[float],
        keyword="bw_mean",
        default=None,
        docstr="Mean of bandwidth samples.",
    )
    bw_min = item(
        data_type=t.Optional[int],
        keyword="bw_min",
        default=None,
        docstr="Minimum bandwidth based on samples.",
    )

    bw_samples = item(
        data_type=t.Optional[int],
        keyword="bw_samples",
        default=None,
        docstr="Number of samples taken for bandwidth.",
    )

    clat_ns = item(
        data_type=t.Optional[FioLatency],
        keyword="clat_ns",
        default=None,
        docstr="Completion latency.",
    )

    drop_ios = item(
        data_type=t.Optional[int],
        keyword="drop_ios",
        default=None,
        docstr="Number of dropped IOs.",
    )

    io_bytes = item(
        data_type=t.Optional[int],
        keyword="io_bytes",
        default=None,
        docstr="Average IO in bytes.",
    )

    io_kbytes = item(
        data_type=t.Optional[float],
        keyword="io_kbytes",
        default=None,
        docstr="Average IO in kbytes.",
    )

    iops = item(
        data_type=t.Optional[float],
        keyword="iops",
        default=None,
        docstr="Average IOPs.",
    )

    iops_max = item(
        data_type=t.Optional[int],
        keyword="iops_max",
        default=None,
        docstr="Maximum IOPs based on samples.",
    )

    iops_mean = item(
        data_type=t.Optional[float],
        keyword="iops_mean",
        default=None,
        docstr="Mean IOPs based on samples.",
    )

    iops_min = item(
        data_type=t.Optional[int],
        keyword="iops_min",
        default=None,
        docstr="Minimum IOPs based on samples.",
    )

    iops_samples = item(
        data_type=t.Optional[int],
        keyword="iops_samples",
        default=None,
        docstr="Number of samples taken for IOPs.",
    )

    iops_stddev = item(
        data_type=t.Optional[float],
        keyword="iops_stddev",
        default=None,
        docstr="Std dev of IOPs samples.",
    )

    lat_ns = item(data_type=FioLatency, keyword="lat_ns", docstr="Total latency.")

    runtime = item(
        data_type=t.Optional[int],
        keyword="runtime",
        default=None,
        docstr="Total runtime.",
    )

    short_ios = item(
        data_type=t.Optional[int],
        keyword="short_ios",
        default=None,
        docstr="Number of short IOs.",
    )

    slat_ns = item(
        data_type=t.Optional[FioLatency],
        keyword="slat_ns",
        default=None,
        docstr="Submission latency.",
    )

    total_ios = item(data_type=int, keyword="total_ios", docstr="Total number of IOs.")


@datarec
class FioJob(DictConstructable):
    """
    Represents a FIO job.
    """

    ctx = item(
        data_type=int, keyword="ctx", docstr="Number of context switches for the CPU."
    )

    elapsed = item(
        data_type=int,
        keyword="elapsed",
        docstr="Total amount of time ellapsed in seconds.",
    )

    error = item(
        data_type=int, keyword="error", docstr="Number of errors during this job."
    )

    eta = item(data_type=int, keyword="eta", docstr="Time till the job is done.")

    groupid = item(
        data_type=int,
        keyword="groupid",
        docstr="Number of context switches for the CPU.",
    )

    iodepth_level = item(
        data_type=t.Dict[str, float],
        keyword="iodepth_level",
        docstr="Distribution of iodepths.",
    )

    job_options = item(
        data_type=FioJobInputParams,
        keyword="job options",
        docstr="Job options for fio.",
    )

    job_runtime = item(
        data_type=int, keyword="job_runtime", docstr="The runtime for the job in ms."
    )

    jobname = item(data_type=str, keyword="jobname", docstr="The name of the job.")

    latency_depth = item(
        data_type=int, keyword="latency_depth", docstr="The latency depth for the job."
    )

    latency_ms = item(
        data_type=t.Dict[str, float],
        keyword="latency_ms",
        docstr="Distribution of latencies in ms.",
    )

    latency_ns = item(
        data_type=t.Dict[str, float],
        keyword="latency_ns",
        docstr="Distribution of latencies in ns. (Up to 1000ns)",
    )

    latency_percentile = item(
        data_type=float,
        keyword="latency_percentile",
        docstr="Percent of I/Os that fall under the latency target/window.",
    )

    latency_target = item(
        data_type=int,
        keyword="latency_target",
        docstr="The target time for the latency.",
    )

    latency_us = item(
        data_type=t.Dict[str, float],
        keyword="latency_us",
        docstr="Distribution of latencies in us. (Up to 1000us)",
    )

    latency_window = item(
        data_type=int,
        keyword="latency_window",
        docstr="The sample window that the job is run in order to test performance.",
    )

    majf = item(
        data_type=int,
        keyword="majf",
        docstr="The number of major page faults on the CPU.",
    )

    minf = item(
        data_type=int,
        keyword="minf",
        docstr="The number of minor page faults on the CPU.",
    )

    sys_cpu = item(
        data_type=float, keyword="sys_cpu", docstr="System time CPU utilization."
    )

    usr_cpu = item(
        data_type=float, keyword="usr_cpu", docstr="User time CPU utilization."
    )

    read = item(
        data_type=FioReadWriteData, keyword="read", docstr="Statistics for reads."
    )

    sync = item(
        data_type=FioReadWriteData, keyword="sync", docstr="Statistics for syncs."
    )

    trim = item(
        data_type=FioReadWriteData, keyword="trim", docstr="Statistics for trims."
    )

    write = item(
        data_type=FioReadWriteData, keyword="write", docstr="Statistics for writes."
    )


@datarec
class FioOutput(DictConstructable):
    """
    Represents the output to a fio job.
    """

    fio_version = item(
        data_type=FioString,
        keyword="fio version",
        docstr="The version of fio where this output is from.",
    )

    timestamp = item(data_type=int, keyword="timestamp", docstr="The timestamp in s.")

    timestamp_ms = item(
        data_type=int, keyword="timestamp_ms", docstr="The timestamp in ms."
    )

    time = item(
        data_type=FioString, keyword="time", docstr="String version of the time."
    )

    global_options = item(
        data_type=t.Optional[FioJobInputParams],
        keyword="global options",
        default=None,
        docstr="Global options for fio.",
    )

    jobs = item(data_type=t.List[FioJob], keyword="jobs", docstr="List of fio jobs.")

    disk_util = item(
        data_type=t.List[FioDiskUtilization],
        keyword="disk_util",
        docstr="Disk utilization statistics.",
    )

    def extract_bandwidth(self, job=0):
        """
        Extract the bandwidth from a job.

        Params:
        job (int, optional): The job to get the bandwidth from.
        Defaults to the first job.

        Returns:
        A tuple of read, write and trim bandwidth in KB/s.
        """
        bw = (self.jobs[job].read.bw, self.jobs[job].write.bw, self.jobs[job].trim.bw)

        return bw

    def extract_iops(self, job=0):
        """
        Extract the iops from a job.

        Params:
        job (int, optional): The job to get the iops from.
        Defaults to the first job.

        Returns:
        A tuple of read, write and trim iops.
        """
        iops = (
            self.jobs[job].read.iops,
            self.jobs[job].write.iops,
            self.jobs[job].trim.iops,
        )

        return iops
