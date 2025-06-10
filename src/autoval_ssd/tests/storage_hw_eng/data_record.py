# pyre-unsafe
"""
.. fb:display_title::
  Data Handling Classes/Functions

Provides functions and classes to easily handle data.
"""

import json
import sys
from typing import Any, Callable, Dict, List, Tuple, TypeVar, Union

import attr
import yaml

# Check version for which to use.
# Uncomment after FB goes to Python3.8 -- Commented due to Pyre errors
# if (sys.version_info.major == 3 and sys.version_info.minor >= 8):
#    from typing import get_args, get_origin
if sys.version_info.major == 3 and sys.version_info.minor >= 7:

    def get_args(t):
        return getattr(t, "__args__", [])

    def get_origin(t):
        return getattr(t, "__origin__", t)

else:  # < 3.7

    def get_args(t):
        return getattr(t, "__args__", [])

    def get_origin(t):
        return getattr(t, "__extra__", t)


def datarec(cls, **kwargs):
    """
    Creates a class that contains data.

    Uses `attrs <https://www.attrs.org/en/stable/>`_ in the background except
    that it specifies that the class uses slots and has keyword only parameters.
    Takes in all other
    `attr.s <https://www.attrs.org/en/stable/api.html#attr.s>`_ keywords.
    """

    # Scrub input.
    if "slots" in kwargs:
        del kwargs["slots"]
    if "kw_only" in kwargs:
        del kwargs["kw_only"]

    data_record = attr.s(cls, slots=True, kw_only=True, **kwargs)

    extracted_attrs = _construct_attr_docstring(data_record)

    data_record.__doc__ = f"{data_record.__doc__}\n{extracted_attrs}"
    return data_record


def _construct_attr_docstring(inst: Any) -> str:
    """
    Constructs a docstring automatically for any datarecord.

    Param:
    isnt: an instance of any datarec decorated obj.

    Returns:
    A docstring containing the attributes.
    """

    fields_str = "Attributes:"

    for field in attr.fields(inst):
        # Get the docstr keyword.
        try:
            docstr = field.metadata["docstr"]
        except KeyError:
            raise TypeError(
                "Data Records require a docstr" "field in metadata for each field"
            )

        # Use get rid of the unnecessary decorators in the type string
        t = (
            str(field.type)[len("<class '") : 0 - len("'>")]
            if "<class" in str(field.type)
            else str(field.type)
        )

        # Get the attribute name and type
        attr_str = f"{field.name} ({t}):{docstr}"

        # Check if there is a default value -- if the default is an empty string
        # print ''
        if field.default != attr.NOTHING:
            default = field.default if str(field.default) != "" else "''"
            default_str = f" | Default={default}"
        else:
            default_str = ""

        # Append to the end of the string.
        fields_str = f"{fields_str}\n    {attr_str}{default_str}"

    return fields_str


def item(*, data_type: type, keyword: str, docstr: str = "", **kwargs):
    """
    Creates an item in a data record.

    Note that this uses attr.ib_ in the background. Adds the *keyword*
    metadata tag automatically. Takes all other keywords for
    `attr.ib <https://www.attrs.org/en/stable/api.html#attr.ib>`_.

    """

    metadata = {} if "metadata" not in kwargs else kwargs["metadata"]
    metadata["keyword"] = keyword
    metadata["docstr"] = docstr

    # Autogen converters
    if "converter" not in kwargs:
        converter = _get_construction_method(data_type, True)
    else:
        converter = kwargs["converter"]

    return attr.ib(type=data_type, metadata=metadata, converter=converter, **kwargs)


def _get_construction_method(t: type, recurse: bool) -> Callable[[Any], Any]:
    """

    TODO: make recurse do something!

    Returns the construction function for the object.
    """

    # Check if Any
    if (t is Any) or (t is None):
        return lambda x: x
    # Check if primitive
    elif t is float:
        return lambda x: float(x)
    elif t is int:
        return lambda x: int(x, 0) if isinstance(x, str) else int(x)
    elif t is str:
        return lambda x: str(x)
    elif t is bool:
        return lambda x: bool(x)
    # Check if dict constructable
    elif DictConstructable.is_constructable(t):
        return lambda x: _construct_dictconstructable(t, x, recurse)
    # Check if supported collections type
    elif get_origin(t) is tuple:
        return lambda x: _construct_tuple(t, x, recurse)
    elif get_origin(t) is list:
        return lambda x: _construct_list(t, x, recurse)
    elif get_origin(t) is dict:
        return lambda x: _construct_dict(t, x, recurse)
    elif get_origin(t) is set:
        return lambda x: _construct_set(t, x, recurse)
    # Typevar
    elif type(t) is TypeVar:
        # TODO: Make specific functions to do this type of conversion.
        return lambda x: x
    # Fall through -> invalid type
    else:
        raise TypeError(f"Invalid Type to autogen conversion function: {t}")


def _construct_dictconstructable(t: type, x: Any, recurse: bool) -> "DictConstructable":
    """
    Construction method for a dict constructable given the type signiture t,
    object x, and if we should recurse r.
    """
    if isinstance(x, dict):
        return t.from_dict(x, recurse=recurse)
    elif isinstance(x, t):
        return x
    elif isinstance(x, str):
        try:
            return t.from_dict(yaml.safe_load(x))
        except Exception:
            raise TypeError(f"String cannot be deserialized into {t}")
    else:
        raise TypeError(f"Type {type(x)} cannot be made into {t}")


def _construct_dict(t, x, recurse: bool) -> Dict:
    """
    Construction method for a dict given the type signiture t,
    object x, and if we should recurse r.
    """

    if type(x) is attr.Factory:
        x = x.factory()

    if len(get_args(t)) == 0:
        return dict(x)
    else:
        key_subtype = get_args(t)[0]
        val_subtype = get_args(t)[1]
        return {
            _get_construction_method(key_subtype, recurse=recurse)(
                k
            ): _get_construction_method(val_subtype, recurse=recurse)(v)
            for k, v in x.items()
        }


def _construct_list(t, x, recurse: bool) -> List:
    """
    Construction method for a list given the type signiture t,
    object x, and if we should recurse r.
    """

    if type(x) is attr.Factory:
        x = x.factory()

    if len(get_args(t)) == 0:
        return list(x)
    else:
        subtype = get_args(t)[0]
        return [_get_construction_method(subtype, recurse=recurse)(item) for item in x]


def _construct_tuple(t, x, recurse: bool) -> Tuple:
    """
    Construction method for a tuple given the type signiture t,
    object x, and if we should recurse r.
    """

    if type(x) is attr.Factory:
        x = x.factory()

    if len(get_args(t)) == 0:
        return tuple(x)
    else:
        subtype = get_args(t)[0]
        return tuple(
            _get_construction_method(subtype, recurse=recurse)(item) for item in x
        )


def _construct_set(t, x, recurse: bool) -> set:
    """
    Construction method for a set given the type signiture t,
    object x, and if we should recurse r.
    """

    if type(x) is attr.Factory:
        x = x.factory()

    if len(get_args(t)) == 0:
        return set(x)
    else:
        subtype = get_args(t)[0]
        return {_get_construction_method(subtype, recurse=recurse)(item) for item in x}


@datarec
class DictConstructable:
    """
    A class representing datarec that can be constructed from a dictionary.
    Note that this any class extending this one must also have the @datarec
    decorator.
    """

    _DICT_CONSTRUCTABLE = True

    @classmethod
    def from_JSON_string(cls, json_data: str) -> "DictConstructable":
        """
        Create a dict constructable from a JSON string.

        Args:
            json_data:
                The JSON string representing the DictConstructable object.

        Returns:
            An instance of the DictConstructable class from the JSON.

        """
        return cls.from_dict(json.loads(json_data))

    @classmethod
    def from_YAML_string(cls, yaml_data: str) -> "DictConstructable":
        """
        Create a dict constructable from a YAML string.

        Args:
            yaml_data:
                The YAML string representing the DictConstructable object.

        Returns:
            An instance of the DictConstructable class from the YAML.
        """
        return cls.from_dict(yaml.safe_load(yaml_data))

    @classmethod
    def from_dict(cls, obj_dict: Dict, recurse: bool = True) -> "DictConstructable":
        """
        Create a dict constructable from a dictionary representing the object

        Args:
            obj_dict:
                The dictionary representing the DictConstructable object.
            recurse:
                [Optional] Recurse through collection-type data structures.
                Defaults to True.

        Returns:
            An instance of the DictConstructable class from the dictionary.
        """

        kwargs = {}

        for field in attr.fields(cls):
            # Get the dict keyword.
            try:
                keyword = field.metadata["keyword"]
            except KeyError:
                raise TypeError(
                    "Data Records require a keyword" "field in metadata for each field"
                )

            # Check that the field's keyword is in the dict.
            if keyword not in obj_dict:
                # If no default, raise an error
                if field.default is None:
                    raise TypeError(
                        "Required keyword:{} Not in object dictionary.".format(keyword)
                    )
                # Otherwise use the default.
                else:
                    data = field.default
            # Otherwise load from the dict.
            else:
                data = obj_dict[keyword]

            kwargs[field.name] = data

        return cls(**kwargs)

    def to_JSON_string(self) -> str:
        """
        Returns the dict constructable as a JSON string.

        Return:
            A JSON string representing the DictConstructable object.

        """
        return json.dumps(self, cls=self._DictConstructableEncoder)

    def to_YAML_string(self, line_break: bool = False) -> str:
        """
        Returns the dict constructable as a YAML string.

        Return:
            A YAML string representing the DictConstructable object.

        """
        if line_break:
            # pyre-fixme[6]: For 2nd param expected `Optional[str]` but got `bool`.
            return yaml.safe_dump(self.to_dict(recurse=True), line_break=True, indent=4)
        else:
            return yaml.safe_dump(self.to_dict(recurse=True))

    def get_name_map(self):
        """
        Maps the field name to the serialize keyword

        Returns:
            Mapping of field name to serialization keyword.
        """
        return {f.name: f.metadata["keyword"] for f in attr.fields(type(self))}

    def to_dict(self, recurse: bool = True) -> Dict:
        """
        To a dictionary.

        Args:
            recurse:
                [Optional] Recurse through all collection like items and turn into
                dictionaries. Defaults to True.

        Returns:
            A dictionary representing the DictConstructable object.
        """
        name_map = self.get_name_map()
        d = {name_map[k]: v for k, v in attr.asdict(self, recurse=False).items()}
        if recurse:
            for name, value in d.items():
                # Check if DictConstructable
                if DictConstructable.is_constructable(value):
                    d[name] = value.to_dict()
                # Else check if is a collections type
                elif isinstance(value, list):
                    d[name] = DictConstructable._to_primitive_list(value)
                elif isinstance(value, set):
                    d[name] = DictConstructable._to_primitive_set(value)
                elif isinstance(value, tuple):
                    d[name] = DictConstructable._to_primitive_tuple(value)
                elif isinstance(value, dict):
                    d[name] = DictConstructable._to_primitive_dict(value)

        return d

    @staticmethod
    def _to_primitive_list(collection: Union[List, set, Tuple]) -> List:
        return [
            e.to_dict() if DictConstructable.is_constructable(e) else e
            for e in collection
        ]

    @staticmethod
    def _to_primitive_set(collection: set) -> set:
        return set(DictConstructable._to_primitive_list(collection))

    @staticmethod
    def _to_primitive_tuple(collection: Tuple) -> Tuple:
        return tuple(DictConstructable._to_primitive_list(collection))

    @staticmethod
    def _to_primitive_dict(collection: Dict) -> Dict:
        return {
            k: (v.to_dict() if DictConstructable.is_constructable(v) else v)
            for k, v in collection.items()
        }

    def pretty(self) -> str:
        """
        Returns a prettified version of a data record.
        (YAML for now)

        Returns:
            A pretty string representing the object.
        """
        return self.to_YAML_string(line_break=True)

    class _DictConstructableEncoder(json.JSONEncoder):
        """
        JSON encoder for dict constructable.
        """

        def default(self, o: Any):
            # Check if Dict Constructable
            if DictConstructable.is_constructable(o):
                return o.to_dict()
            if isinstance(o, set):
                return list(o)
            return json.JSONEncoder.default(self, o)

    @staticmethod
    def is_constructable(t: type) -> bool:
        """
        Checks if something is dict constructable. Note that this uses a
        private attribute.

        Args:
            t:
                The class to check if is DictConstructable.

        Return:
            True if the class is DictConstructable, False otherwise.
        """
        if getattr(t, "_DICT_CONSTRUCTABLE", None) is not None:
            return True
        return False
