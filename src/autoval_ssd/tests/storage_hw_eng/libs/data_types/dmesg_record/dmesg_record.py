# pyre-unsafe
import datetime
import re
import typing as t
from collections import UserDict

from ..data_record.data_record import datarec, DictConstructable, item
from ..data_record.serial_type import Serializable


def time_converter(time: t.Optional[t.Union[datetime.datetime, str]]):
    if time is None:
        return None
    if isinstance(time, str):
        return datetime.datetime.strptime(time, r"%c")
    if isinstance(time, datetime.datetime):
        return time

    raise TypeError(f"Cannot convert {time} with type" + f"{type(time)} to a time.")


@datarec
class DmesgEntry(DictConstructable):
    """
    Represents a Dmesg Entry
    """

    valid = item(
        data_type=bool,
        keyword="valid",
        default=True,
        docstr="If the dmesg is in a valid format.",
    )

    facility = item(
        data_type=t.Optional[str],
        keyword="facility",
        default=None,
        docstr="The facility for this msg.",
    )

    priority = item(
        data_type=t.Optional[str],
        keyword="priority",
        default=None,
        docstr="The priority for this msg.",
    )

    sys_time = item(
        data_type=t.Optional[datetime.datetime],
        keyword="sys_time",
        default=None,
        converter=time_converter,
        serializer=lambda x: x.strftime(r"%c") if x is not None else x,
        docstr="The system time for this entry.",
    )

    msg = item(
        data_type=t.Optional[str], keyword="msg", default=None, docstr="The message."
    )

    raw = item(data_type=str, keyword="raw", docstr="Raw dmesg line.")

    def __init__(
        self,
        valid=valid,
        facility=facility,
        priority=priority,
        sys_time=sys_time,
        msg=msg,
        raw=raw,
    ):
        DmesgEntry.valid = valid
        DmesgEntry.facility = facility
        DmesgEntry.priority = priority
        DmesgEntry.sys_time = sys_time
        DmesgEntry.msg = msg
        DmesgEntry.raw = raw

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return False
        return self.raw.strip() == other.raw.strip()

    @classmethod
    def from_dmesg_line(cls, line: str, silent: bool = True) -> "DmesgEntry":
        """
        Parse from a line in dmesg
        """
        pattern = (
            r"((?P<facility>[a-z]+)[\t ]*:)?"
            + r"((?P<priority>[a-z]+)[\t ]*:)?[\t ]*"
            + r"(?P<time>[\d\-:,T\+]+)[\t ]*"
            + r"(?P<msg>[\S].*)\n?"
        )

        match = re.match(pattern, line)

        if match is None:
            if not silent:
                raise Exception(
                    "Malformed dmesg line! Please run dmesg with -x -p --time-format iso options."
                )
            else:
                return cls(valid=False, raw=line)

        time_str = match["time"]
        # Crazy parsing of dmesg time string... non-standard across versions =(
        if time_str[29] == ":":
            date_end = 32
            time_str = (
                time_str[:29] + time_str[30:date_end]
            )  # Remove colon from timestamp

        fac = match["facility"] if match["facility"] else "UNKNOWN"
        pri = match["priority"] if match["priority"] else "UNKNOWN"

        return cls(
            valid=True,
            facility=fac,
            priority=pri,
            sys_time=datetime.datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S,%f%z"),
            msg=match["msg"],
            raw=line,
        )


class Dmesg(Serializable, UserDict):
    def __init__(self):
        self.data = None

    def __delitem__(self, key):
        super().__delitem__(Dmesg._convert_to_ts(key))

    def __setitem__(self, key, value):
        if not isinstance(value, DmesgEntry):
            raise TypeError("Values must be DmesgEntry.")

        super().__setitem__(Dmesg._convert_to_ts(key), value)

    def __getitem__(self, key):
        return super().__getitem__(Dmesg._convert_to_ts(key))

    def __contains__(self, key):
        return super().__contains__(Dmesg._convert_to_ts(key))

    def has_keys(self, key):
        return super().has_keys(Dmesg._convert_to_ts(key))

    def pop(self, key, *args):
        return super().pop(Dmesg._convert_to_ts(key), *args)

    def __add__(self, o):
        """
        Add two Dmesg to add messages together.
        """
        copy = self.copy()
        copy.update(o)
        return copy

    def __sub__(self, o):
        """
        Removes keys that exist in the other Dmesg.
        """
        copy = self.copy()

        for key in o.keys():
            if key in copy:
                del copy[key]

        return copy

    @staticmethod
    def _convert_to_ts(item):
        """
        Convert various types to the proper float ts.
        """

        if isinstance(item, datetime.datetime):
            return item.timestamp()
        try:
            return float(item)
        except TypeError:
            raise TypeError("Dmesg keys must be convertable to float timestamp.")

    @staticmethod
    def dmesg_command(clear: bool = False):
        if clear:
            return "dmesg -c -p -x --time-format iso"
        return "dmesg -x -p --time-format iso"

    @classmethod
    def from_dmesg_output(cls, dmesg_output: str) -> t.Dict:
        """
        Load a dmesg object from
        """
        output = {}

        for line in dmesg_output.split("\n"):
            if line == "":
                continue

            try:
                dmesg_entry = DmesgEntry.from_dmesg_line(line)
                if dmesg_entry.sys_time is not None:
                    if dmesg_entry.sys_time in output:
                        output[dmesg_entry.sys_time].msg += f" | {dmesg_entry.msg}"
                        output[dmesg_entry.sys_time].raw += f"\n{dmesg_entry.raw}"
                    else:
                        output[dmesg_entry.sys_time] = dmesg_entry
            except Exception as e:
                print(e)
        return output

    def __str__(self):
        return str(self.to_serializable())

    def to_serializable(self) -> t.Dict[float, t.Dict]:
        return {k: v.to_serializable() for k, v in self.items()}

    @classmethod
    def from_serializable(cls, o: t.Union[t.Dict, "Dmesg"]):
        if isinstance(o, cls):
            return Dmesg.from_serializable(o.to_serializable())

        if not isinstance(o, dict):
            raise Exception("Dmesg needs a dictionary to serialize from.")

        output = cls()
        for k, v in o.items():
            if isinstance(v, DmesgEntry):
                output[k] = v
            else:
                output[k] = DmesgEntry.from_dict(v)

        return output
