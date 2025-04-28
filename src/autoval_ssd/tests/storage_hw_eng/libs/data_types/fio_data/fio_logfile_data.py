# pyre-unsafe
import enum as e
import re
import typing as t

from autoval_ssd.tests.storage_hw_eng.libs.data_types.data_record.data_record import (
    datarec,
    DictConstructable,
    item,
)

from autoval_ssd.tests.storage_hw_eng.libs.data_types.data_record.data_record_enum import (
    enum_from_serial,
    enum_serial,
    enum_to_serial,
)


@enum_serial(by_name=False)
class FioLogFileType(e.Enum):
    LATENCY = ("LATENCY", "Latency", "latency", "Lat", "lat")
    CLATENCY = (
        "COMPLETIONLATENCY",
        "COMPLETIONLAT",
        "COMP_LAT",
        "CLATENCY",
        "CompletionLatency" "CompetionLat",
        "CompLatency",
        "CompLat",
        "CLatency" "clatency",
        "cLat",
        "clat",
    )
    SLATENCY = (
        "SUBMISSIONLATENCY",
        "SUBMISSIONLAT",
        "SUBLATENCY",
        "SUB_LAT",
        "SLATENCY",
        "SubmissionLatency",
        "SubmissionLat",
        "SubLatency",
        "SubLat",
        "SLatency",
        "slatency",
        "sLat",
        "slat",
    )
    BANDWIDTH = ("BANDWIDTH", "Bandwidth", "bandwidth", "BW", "bw")
    IOPS = ("IOPS", "iops")


@enum_serial(by_name=False)
class FioDataDirection(e.Enum):
    READ = 0
    WRITE = 1
    TRIM = 2


@datarec
class FioLogEntry(DictConstructable):
    NUM_COLS = 5
    NUM_COLS_CMD = 6

    time = item(data_type=int, keyword="time", docstr="Time in ms.")

    value = item(data_type=int, keyword="value", docstr="Entry value")

    data_dir = item(
        data_type=FioDataDirection,
        keyword="data_direction",
        docstr="The data direction",
    )

    blk_size = item(data_type=int, keyword="blk_size", docstr="Block size in bytes")

    offset = item(data_type=int, keyword="offset", docstr="Offset in bytes")

    cmd_priority = item(
        data_type=t.Optional[int], keyword="cmd_priority", docstr="Command priority."
    )

    def __init__(
        self,
        time=time,
        value=value,
        data_dir=data_dir,
        blk_size=blk_size,
        offset=offset,
        cmd_priority=cmd_priority,
    ):
        FioLogEntry.time = time
        FioLogEntry.value = value
        FioLogEntry.data_dir = data_dir
        FioLogEntry.blk_size = blk_size
        FioLogEntry.offset = offset
        FioLogEntry.cmd_priority = cmd_priority

    @classmethod
    def from_log_line(cls, line: str):
        """
        Creates a FioLogEntry from a line in the log.
        """
        cols = [col.strip() for col in line.split(",")]

        if len(cols) == FioLogEntry.NUM_COLS:
            return cls(
                time=cols[0],
                value=cols[1],
                data_dir=cols[2],
                blk_size=cols[3],
                offset=cols[4],
                cmd_priority=None,
            )

        if len(cols) == FioLogEntry.NUM_COLS_CMD:
            return cls(
                time=cols[0],
                value=cols[1],
                data_dir=cols[2],
                blk_size=cols[3],
                offset=cols[4],
                cmd_priority=cols[5],
            )

        return None

    def to_log_line(self) -> str:
        """
        Creates a line in a fio log based on this entry.
        """

        return ",".join(
            (
                str(self.time),
                str(self.value),
                str(enum_to_serial(self.data_dir)),
                str(self.blk_size),
                str(self.offset),
                str(self.cmd_priority),
            )
        )


@datarec
class FioLogFile(DictConstructable):
    FILE_REGEX = re.compile(
        r"(?P<prefix>\w+)_"
        + r"(?P<file_type>[a-z]+)"
        + r"(\.(?P<job_index>\d+))?"
        + r"\.log"
    )

    file_type = item(
        data_type=t.Optional[FioLogFileType],
        default=None,
        keyword="file_type",
        docstr="Type of fio log file.",
    )

    job_index = item(
        data_type=t.Optional[int],
        default=None,
        keyword="job_index",
        docstr="Job index.",
    )

    entries = item(
        data_type=t.List[FioLogEntry],
        factory=list,
        keyword="entries",
        docstr="Log file entries.",
    )

    def __init__(self, file_type=file_type, job_index=job_index, entries=entries):
        FioLogFile.file_type = file_type
        FioLogFile.job_index = job_index
        FioLogFile.entries = entries

    @staticmethod
    def type_index_from_filename(
        logfile_name,
    ) -> t.Tuple[t.Optional[FioLogFileType], t.Optional[int]]:
        if logfile_name is None:
            return (None, None)

        match = FioLogFile.FILE_REGEX.search(logfile_name)
        if match is None:
            return (None, None)

        return (
            enum_from_serial(
                match.group("file_type"),
                FioLogFileType,
                strict=False,
                default=None,
                by_name=False,
            ),
            match.group("job_index"),
        )

    @classmethod
    def from_logtext(cls, text: str, logfile_name=None) -> "FioLogFile":
        file_type, job_index = FioLogFile.type_index_from_filename(logfile_name)

        entries = []
        for line in text.split("\n"):
            entry = FioLogEntry.from_log_line(line)
            if entry is not None:
                entries.append(entry)

        return cls(file_type=file_type, job_index=job_index, entries=entries)

    @staticmethod
    def write_csv_title(csv_file_obj, value_col: str = "value"):
        csv_file_obj.write(
            f"time,{value_col},direction,blksize,offset,cmd_pri,job_index,file_type\n"
        )

    def modify_values(self, func: t.Callable):
        for entry in self.entries:
            entry.value = func(entry.value)

    def write_to_csv_line(self, csv_file_obj):
        for entry in self.entries:
            csv_file_obj.write(
                f"{entry.to_log_line()},{self.job_index},{enum_to_serial(self.file_type)}\n"
            )
