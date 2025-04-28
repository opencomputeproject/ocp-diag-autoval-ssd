# pyre-unsafe
from typing import get_args, get_origin


def check_none_allowed(data_type: type):
    if data_type is None or isinstance(data_type, type(None)):
        return True
    if type(None) in get_args(data_type):
        return True

    return False
