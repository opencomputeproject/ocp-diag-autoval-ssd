# pyre-unsafe
import enum
import typing as t

import attr

from . import data_record_enum as en
from .serial_type import Serializable
from .typing_utils import get_args, get_origin

PRINT_LIMIT = 250


def get_constr_method(
    data_type: type, recurse: bool = True
) -> t.Callable[[t.Any], t.Any]:
    """ """

    CONSTR_LUT: t.Dict[t.Any, t.Callable[[t.Any], t.Any]] = {
        None: _create_none_type,
        type(None): _create_none_type,
        int: lambda x: int(x, 0) if isinstance(x, str) else int(x),
        str: lambda x: str(x),
        float: lambda x: float(x),
        bool: lambda x: bool(x),
        dict: lambda x: _constr_dict(data_type, x, recurse),
        list: lambda x: _constr_list(data_type, x, recurse),
        tuple: lambda x: _constr_tuple(data_type, x, recurse),
        set: lambda x: _constr_set(data_type, x, recurse),
        Serializable: lambda x: _constr_serializable(data_type, x),
        enum.EnumMeta: lambda x: _constr_enum(data_type, x),
        t.Any: lambda x: x,
        t.TypeVar: lambda x: x,
        t.Union: lambda x: _constr_union(data_type, x, recurse),
    }

    token = _tokenize(data_type)

    if token in CONSTR_LUT:
        return CONSTR_LUT[token]
    else:
        return lambda x: _create_non_serial(data_type, x)


def _create_non_serial(data_type: type, x: t.Any):
    if isinstance(x, data_type):
        return x
    raise TypeError(f"{x} of type {type(x)} is not an instance of {data_type}!")


def _create_none_type(x):
    if x is None or x is attr.NOTHING:
        return None
    else:
        printout = str(x)
        if len(printout) > PRINT_LIMIT:
            printout = str(x)[:PRINT_LIMIT] + " ..."
        raise TypeError(f"Cannot make {printout} into None")


def _constr_dict(data_type: type, x: t.Any, recurse: bool) -> t.Dict:
    """
    Construction method for a dict given the type signiture t,
    object x, and if we should recurse r.
    """

    if type(x) is attr.Factory:
        x = x.factory()

    if get_args(data_type) is None or len(get_args(data_type)) == 0:
        return dict(x)
    else:
        key_subtype = get_args(data_type)[0]
        val_subtype = get_args(data_type)[1]
        return {
            get_constr_method(key_subtype, recurse=recurse)(k): get_constr_method(
                val_subtype, recurse=recurse
            )(v)
            for k, v in x.items()
        }


def _constr_list(data_type: type, x: t.Any, recurse: bool) -> t.List:
    """
    Construction method for a list given the type signiture t,
    object x, and if we should recurse r.
    """

    if type(x) is attr.Factory:
        x = x.factory()

    if get_args(data_type) is None or len(get_args(data_type)) == 0:
        return list(x)
    else:
        subtype = get_args(data_type)[0]
        return [get_constr_method(subtype, recurse=recurse)(item) for item in x]


def _constr_tuple(data_type: type, x: t.Any, recurse: bool) -> t.Tuple:
    """
    Construction method for a tuple given the type signiture t,
    object x, and if we should recurse r.
    """

    if type(x) is attr.Factory:
        x = x.factory()

    subtypes = get_args(data_type)

    if subtypes is None or len(subtypes) == 0:
        return tuple(x)
    else:
        if len(subtypes) != len(x):
            raise TypeError(
                f"Invalid tuple length. Expected {len(subtypes)} got {len(x)}"
            )

        return tuple(
            get_constr_method(subtypes[i], recurse=recurse)(x[i]) for i in range(len(x))
        )


def _constr_set(data_type: type, x: t.Any, recurse: bool) -> set:
    """
    Construction method for a set given the type signiture t,
    object x, and if we should recurse r.
    """

    if type(x) is attr.Factory:
        x = x.factory()

    if get_args(data_type) is None or len(get_args(data_type)) == 0:
        return set(x)
    else:
        subtype = get_args(data_type)[0]
        return {get_constr_method(subtype, recurse=recurse)(item) for item in x}


def _constr_serializable(data_type: type, x: t.Any) -> "Serializable":
    """
    Construct a serializable object.
    """

    if isinstance(x, data_type):
        return x

    if type(x) in get_args(Serializable.SerialType):
        return data_type.from_serializable(x)

    # Needed for Python3.6 -- fixed in 3.7
    # This is because bool is a subclass of int...
    # See: (https://github.com/python/cpython/pull/6841)
    if type(x) is bool:
        return data_type.from_serializable(x)

    # Otherwise just
    raise TypeError(
        f"Type {type(x)} cannot be made into {data_type} since it is not serializable."
    )


def _constr_enum(data_type: type, x: t.Any) -> enum.Enum:
    """
    Construction method for an enum given the type signiture data_type and
    obj. x
    """

    if type(x) is data_type:
        return x

    return en.enum_from_serial(x, data_type)


def _constr_union(data_type: type, x: t.Any, recurse: bool = True):
    # Special None case since bool(None) is False....
    if (type(None) in get_args(data_type)) and (x is None):
        return x

    # Otherwise try every other type in the union
    error_msgs = ""
    for arg in get_args(data_type):
        try:
            return get_constr_method(arg, recurse=recurse)(x)
        except Exception as e:
            error_msgs = f"{error_msgs}\n{arg} :: {str(e)}"

    printout = str(x)
    if len(printout) > PRINT_LIMIT:
        printout = str(x)[:PRINT_LIMIT] + " ..."
    raise TypeError(
        f"Cannot parse {printout} into any type in Union: {data_type}."
        + f"\nMessages:{error_msgs}"
    )


def get_serialization_method(
    data_type: type,
    error_on_unknown: bool = False,
    recurse: bool = True,
    depth: int = 10,
) -> t.Callable[[t.Any], t.Any]:
    """ """

    # Check if depth is 0
    if depth < 0:
        return lambda x: x

    # If recurse is false -- set depth to 0
    depth = depth if recurse else 0

    SERIAL_LUT: t.Dict[t.Any, t.Callable[[t.Any], t.Any]] = {
        None: lambda x: _serialize_None(x),
        type(None): lambda x: _serialize_None(x),
        int: lambda x: int(x),
        str: lambda x: str(x),
        float: lambda x: float(x),
        bool: lambda x: bool(x),
        dict: lambda x: _serialize_dict(x, depth=depth),
        list: lambda x: _serialize_list(x, depth=depth),
        tuple: lambda x: _serialize_tuple(x, depth=depth),
        set: lambda x: _serialize_set(x, depth=depth),
        Serializable: lambda x: _serialize_serializable(x, data_type),
        enum.EnumMeta: lambda x: en.enum_to_serial(x),
        t.Union: lambda x: _serialize_union(x, data_type, depth=depth),
    }

    token = _tokenize(data_type)

    if token in SERIAL_LUT:
        return SERIAL_LUT[token]
    else:
        if error_on_unknown:
            raise TypeError(f"Invalid Type to find serialization function: {t}")
        else:
            return lambda x: x


def _serialize_serializable(x: t.Any, data_type: type):
    if Serializable.is_serializable(x):
        return x.to_serializable()
    return data_type.from_serializable(x).to_serializable()


def _serialize_None(x: t.Any) -> None:
    if x is not None:
        raise TypeError(f"{type(x)} cannot be made into None Type.")
    return None


def _serialize_dict(collection: t.Dict, depth: int) -> t.Dict:
    serial_dict = {}
    for k, v in collection.items():
        key = get_serialization_method(
            data_type=type(k), recurse=True, depth=(depth - 1)
        )(k)
        value = get_serialization_method(
            data_type=type(v), recurse=True, depth=(depth - 1)
        )(v)

        serial_dict[key] = value

    return serial_dict


def _serialize_list(
    collection: t.Union[t.List, set, t.Tuple], depth: int, recurse: bool = True
) -> t.List:
    primitive_list = []
    for e in collection:
        serial_method = get_serialization_method(
            data_type=type(e), recurse=True, depth=(depth - 1)
        )

        primitive_list.append(serial_method(e))

    return primitive_list


def _serialize_tuple(
    collection: t.Tuple,
    depth: int,
    as_list: bool = True,
) -> t.Union[t.List, t.Tuple]:
    serial_list = _serialize_list(collection, depth=depth)

    if as_list:
        return serial_list
    return tuple(serial_list)


def _serialize_set(
    collection: t.Set,
    depth: int,
    as_list: bool = True,
) -> t.Union[t.List, t.Set]:
    serial_list = _serialize_list(collection, depth=depth)

    if as_list:
        return serial_list
    return set(serial_list)


def _serialize_union(x: t.Any, data_type: type, depth: int) -> t.Any:
    # Special None case since bool(None) is False....
    if (type(None) in get_args(data_type)) and (x is None):
        return x
    elif type(x) in [list, tuple, dict, set] and len(x) == 0:
        return x

    # Otherwise try every other type in the union
    error_msgs = ""
    for arg in get_args(data_type):
        try:
            return get_serialization_method(arg, depth=depth)(x)
        except Exception as e:
            error_msgs = f"{error_msgs}\n{arg} :: {str(e)}"

    raise TypeError(
        f"Cannot serialize {x} into any type in Union: {data_type}."
        + f"\nMessages:{error_msgs}"
    )


def _tokenize(data_type: type):
    # Check if serializable
    if Serializable.is_serializable(data_type):
        return Serializable

    # Check if enum
    if type(data_type) is enum.EnumMeta:
        return enum.EnumMeta

    # Check if TypeVar
    if type(data_type) is t.TypeVar:
        return t.TypeVar

    # Check if has valid origin
    origin_types = [tuple, list, dict, set, t.Union]
    type_origin = get_origin(data_type)
    for origin in origin_types:
        if type_origin is origin:
            return type_origin

    return data_type
