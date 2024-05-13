#!/usr/bin/env python3

# pyre-unsafe
import re
from typing import Dict, Optional, Tuple

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils


def compare_drive_data(
    drive_serial_no: str,
    validate_config: Dict,
    smart_before: Dict,
    smart_after: Dict,
    ignore_smart: bool = False,
) -> None:
    """
    Usees instructions from validate_config dictionary and to compare drive
    SMART data before and after the test
    """
    if len(smart_before) == 0:
        raise TestError("smart_before is empty", error_type=ErrorType.SMART_COUNTER_ERR)
    if len(smart_after) == 0:
        raise TestError("smart_after is empty", error_type=ErrorType.SMART_COUNTER_ERR)
    for field in validate_config:
        compare_instr = validate_config[field]
        actual, expected = _validate_smart_value(
            field, smart_before, smart_after, drive_serial_no
        )
        AutovalLog.log_debug(
            f"SMART Validation: Drive: {drive_serial_no}, Field: {field}, After: {actual}, Instr: {compare_instr}, Before: {expected}"
        )
        if actual is not None and expected is not None:
            # after ssd debug meeting, it is decided that Bad NAND Block Count (Raw) is
            # allowed for a max difference of 1
            _compare_drive_data_field(
                expected,
                actual,
                drive_serial_no,
                field,
                compare_instr,
                ignore_smart=ignore_smart,
            )


def _validate_smart_value(
    field: str, smart_before: Dict, smart_after: Dict, serial: str
) -> Tuple:
    expected = None
    if "-thresh" in field:
        # For SATA\SAS drives
        field_value = field.split("-")[0] + "-value"
        expected = _find_in_nested_dict(smart_before, field_value)
    if expected is None:
        # For NVME drives
        expected = _find_in_nested_dict(smart_before, field)
    actual = _find_in_nested_dict(smart_after, field)
    if actual is None and field not in smart_after.keys():
        if field in smart_before.keys():
            raise TestError(
                f"key {field} is missing in drive log after test",
                error_type=ErrorType.SMART_COUNTER_ERR,
                component=COMPONENT.STORAGE_DRIVE,
            )
        else:
            raise TestError(
                f"key {field} is missing in drive log before and after test",
                error_type=ErrorType.SMART_COUNTER_ERR,
                component=COMPONENT.STORAGE_DRIVE,
            )
    return actual, expected


def _find_in_nested_dict(nested_dict: dict, key: str) -> Optional[object]:
    """
    Find a value of a given key in a nested dictionary

    Args:
        nested_dict: Dictionary to be used to search the key
        key: Key to be searched

    Returns:
        value: Value of the key if found, None otherwise
    """
    value = None
    for k, v in nested_dict.items():
        if k == key:
            return v
        elif isinstance(v, dict):
            value = _find_in_nested_dict(v, key)
            if value is not None:
                return value


def _compare_drive_data_field(
    before,
    actual: int,
    drive_serial_no: str,
    field: str,
    instr: str,
    ignore_smart: bool = False,
) -> None:
    """
    Parse a validate instruction and perform comparison on before vs. actual
    values of a field. Supported operations:
    '<'-> less than
    '>' -> greater than
    '>='-> greater than equal to
    '<='-> less than equal to
    '=' -> check equality, similar to ==
    '-' -> in-between range (lower_val is required)
    '/' -> multiple options (existence of word in a string)
    '~' -> increment the 'expected' by "increment_by" and compare

    @param string/numeric before, actual:
    @param string instr: e.g. ">80", "=="
    """
    expected = None
    lower = 0
    opr = None
    msg = f"Compare drive {drive_serial_no} {field} before vs. after test."
    out = re.search(r"==|>=|<=|>|<|/|-|~|=", instr)
    if out:
        opr = out.group(0)
        if opr == "-":
            lower, higher = instr.split("-")
            _evaluate_expression(
                actual, int(higher), opr, msg, ignore_smart, lower_val=int(lower)
            )
        elif opr == "~":
            increment = int(instr.strip(opr))
            _evaluate_expression(
                actual, before, opr, msg, ignore_smart, increment_by=increment
            )
        elif opr == "/":
            expected = instr.split("/")
            _evaluate_expression(expected, actual, opr, msg, ignore_smart)
        elif opr == "==":
            _evaluate_expression(actual, before, "=", msg, ignore_smart)
        else:
            operand = instr.strip(opr)
            if operand.isdigit():
                expected = int(operand)
            else:
                expected = before
                if _needs_int_cast(expected):
                    expected = int(expected)
            if _needs_int_cast(actual):
                actual = int(actual)
            _evaluate_expression(actual, expected, opr, msg, ignore_smart)
    else:
        raise TestError(
            f"No matching operator found in {instr}.",
            error_type=ErrorType.INPUT_ERR,
        )


def _needs_int_cast(value) -> bool:
    """
    Checks if the operand/value needs to be converted to an int
    Returns True if the operand/value is a string and all the characters are digits
    Returns False otherwise
    """
    if not (isinstance(value, int) or isinstance(value, float)) and value.isdigit():
        return True
    return False


def _evaluate_expression(
    actual,
    expected,
    opr: str,
    msg,
    ignore_smart: bool,
    lower_val: int = 0,
    increment_by: int = 0,
) -> None:
    opr_match = {
        ">": "gt",
        "<": "lt",
        ">=": "gte",
        "<=": "lte",
        "-": "range",
        "/": "isIn",
        "~": "incrementby",
        "=": "isEqual",
    }
    AutovalUtils.validate_in(
        opr,
        list(opr_match.keys()),
        f"Operator {opr} not supported",
        log_on_pass=False,
        component=COMPONENT.SYSTEM,
        error_type=ErrorType.TEST_SCRIPT_ERR,
    )
    if opr_match[opr] == "range":
        AutovalUtils.validate_greater_equal(
            actual,
            lower_val,
            msg,
            log_on_pass=False,
            raise_on_fail=False,
            warning=ignore_smart,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.SMART_COUNTER_ERR,
        )
        AutovalUtils.validate_less_equal(
            actual,
            expected,
            msg,
            log_on_pass=False,
            raise_on_fail=False,
            warning=ignore_smart,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.SMART_COUNTER_ERR,
        )
    elif opr_match[opr] == "incrementby":
        expected = expected + increment_by
        AutovalUtils.validate_less_equal(
            actual,
            expected,
            msg,
            log_on_pass=False,
            raise_on_fail=False,
            warning=ignore_smart,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.SMART_COUNTER_ERR,
        )
    elif opr_match[opr] == "isIn":
        for each in expected:
            AutovalUtils.validate_in(
                each,
                actual,
                msg,
                log_on_pass=False,
                raise_on_fail=False,
                warning=ignore_smart,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.SMART_COUNTER_ERR,
            )
    elif opr_match[opr] == "isEqual":
        AutovalUtils.validate_equal(
            actual,
            expected,
            msg,
            log_on_pass=False,
            raise_on_fail=False,
            warning=ignore_smart,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.SMART_COUNTER_ERR,
        )
    else:
        AutovalUtils._validate_lt_gt_eq(
            actual,
            expected,
            msg,
            opr_match[opr],
            log_on_pass=False,
            raise_on_fail=False,
            warning=ignore_smart,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.SMART_COUNTER_ERR,
        )
