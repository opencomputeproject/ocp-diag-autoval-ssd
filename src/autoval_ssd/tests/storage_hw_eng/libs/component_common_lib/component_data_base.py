# pyre-unsafe
import typing as t

from autoval_ssd.tests.storage_hw_eng.libs.data_types.data_record.data_record import (
    datarec,
    DictConstructable,
    item,
)
from autoval_ssd.tests.storage_hw_eng.libs.data_types.dmesg_record import Dmesg


@datarec
class ComponentInputBase(DictConstructable):
    collect_dmesg = item(
        data_type=bool,
        keyword="collect_dmesg",
        default=True,
        docstr="Whether or not to collect Dmesg.",
    )

    check_dmesg = item(
        data_type=bool,
        keyword="check_dmesg",
        default=True,
        docstr="Whether or not to check Dmesg in the end.",
    )

    collect_smart = item(
        data_type=bool,
        keyword="collect_smart",
        default=True,
        docstr="Whether or not to collect Smartlogs during runs.",
    )


@datarec
class ComponentTestEntry(DictConstructable):
    success = item(
        data_type=bool,
        keyword="success",
        default=True,
        docstr="If this entry has valid data.",
    )

    msgs = item(
        data_type=t.List[str], keyword="msgs", factory=list, docstr="Any run messages."
    )


@datarec
class ComponentOutputBase(DictConstructable):
    version = item(
        data_type=str, default="0.0.1", keyword="test_version", docstr="Test Version"
    )

    input_params = item(
        data_type=t.Optional[str],
        keyword="input_params",
        default=None,
        serializer=(lambda x: x.to_serializable() if x is not None else x),
        docstr="The input that generated this output.",
    )

    initial_dmesg = item(
        data_type=t.Optional[Dmesg],
        keyword="initial_dmesg",
        default=None,
        docstr="Initial dmesg pull.",
    )

    final_dmesg = item(
        data_type=t.Optional[Dmesg],
        keyword="final_dmesg",
        default=None,
        docstr="Final dmesg pull.",
    )

    initial_dmesg_raw = item(
        data_type=t.Optional[str],
        keyword="initial_dmesg_raw",
        default=None,
        docstr="Initial raw dmesg pull.",
    )

    final_dmesg_raw = item(
        data_type=t.Optional[str],
        keyword="final_dmesg_raw",
        default=None,
        docstr="Final raw dmesg pull.",
    )

    final_dmesg_check = item(
        data_type=t.Optional[str],
        keyword="final_dmesg_check",
        default=None,
        docstr="Check the final dmesg.",
    )
