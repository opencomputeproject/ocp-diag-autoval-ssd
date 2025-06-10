# pyre-unsafe
"""
.. fb:display_title::
  Constructable Enum

Provides functions to create enums from strings/integers.
"""

import enum
from typing import Optional


def _normalize_str(s: str):
    """
    Normalize the string.
    """
    return s.upper().strip()


def enum_serial(
    _cls=None,
    *,
    by_name: bool = True,
    strict: bool = True,
    default: Optional[str] = None,
):
    """
    Decorator to add enum customizations
    """

    def decorator(cls=enum.EnumMeta):
        try:
            default_val = cls[default] if default is not None else None
        except KeyError:
            raise KeyError(f"Unknown default enum value '{default}'.")

        cls._serialization_params = {
            "by_name": by_name,
            "strict": strict,
            "default": default_val,
        }

        return cls

    if _cls is None:
        return decorator

    return decorator(_cls)


def enum_to_serial(e_type=enum.Enum):
    """
    Makes an Enum serialization friendly. Note that
    this can include the serialization parameters from the enum_serial
    decorator.

    Params:
    e_type (enum.Enum): The enum to make serialization friendly.

    Returns:
    The serialization friendly version of the enum
    """
    metaclass = type(e_type)

    # Check if we have the decorator options
    if hasattr(metaclass, "_serialization_params"):
        return _enum_to_serial(
            e_type, by_name=metaclass._serialization_params["by_name"]
        )

    return _enum_to_serial(e_type)


def enum_from_serial(value, e_type=enum.EnumMeta, **kwargs):
    """
    Deserializes Enum. Note that
    this can include the serialization parameters from the enum_serial
    decorator.

    Params:
    e_type (enum.EnumMeta): The enum meta type which contains the enums that should
    be converted into.
    value: The value to convert into the proper enum.

    Raises:
    TypeError: Error in conversion.

    Returns:
    The Enum that was parsed from the value.
    """

    # Check if we have the decorator options
    if hasattr(e_type, "_serialization_params"):
        return _enum_from_serial(
            e_type,
            value,
            by_name=e_type._serialization_params["by_name"],
            strict=e_type._serialization_params["strict"],
            default=e_type._serialization_params["default"],
        )

    return _enum_from_serial(e_type, value, **kwargs)


def _enum_to_serial(e_type: enum.Enum, by_name: bool = True):
    """
    Makes an Enum serialization friendly.

    Params:
    e_type (enum.Enum): The enum to make serialization friendly
    by_name (bool, optional): If True, returns the string version of the name,
    else returns the value. Note that if the value is a tuple, returns the
    first element. Defaults to True.

    Raises:
    TypeError: If cannot convert due to an empty tuple.

    Returns:
    The serialization friendly version of the enum
    """
    if by_name:
        return e_type.name
    else:
        if type(e_type.value) is tuple:
            if len(e_type.value) == 0:
                raise TypeError(f"Cannot convert {e_type} since value tuple is empty.")
            return e_type.value[0]

        else:
            return str(e_type.value)


def _enum_from_serial(
    e_type: enum.EnumMeta,
    value,
    default=None,
    strict: bool = True,
    by_name: bool = True,
):
    """
    Deserializes Enum

    Params:
    e_type (enum.EnumMeta): The enum meta type which contains the enums that should
    be converted into.
    value: The value to convert into the proper enum.
    default: The default value to return. Defaults to None.
    strict (bool): If true, returns an error if cannot find proper parse value.
    Otherwise will return the default in that that case.Defaults to True.
    by_name (bool): Convert by the name of the enum rather than the value. Defaults
    to True.

    Raises:
    TypeError: Error in conversion.

    Returns:
    The Enum that was parsed from the value.
    """

    norm_val = _normalize_str(str(value))

    if by_name:
        for item in e_type:
            if _normalize_str(item.name) == norm_val:
                return item
    else:
        for item in e_type:
            if type(item.value) is tuple:
                for parse_value in item.value:
                    if _normalize_str(str(parse_value)) == norm_val:
                        return item
            else:
                if _normalize_str(str(item.value)) == norm_val:
                    return item

    if strict:
        raise TypeError(f"Failure to convert {value} to {e_type}")

    return default
