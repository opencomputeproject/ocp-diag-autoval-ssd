# pyre-unsafe
"""
.. fb:display_title::
  Data Handling Classes/Functions

Provides functions and classes to easily handle data.
"""

import json
import sys
import typing as t

import attr
import yaml

from .serial_funcs import get_constr_method, get_serialization_method
from .serial_type import Serializable
from .typing_utils import check_none_allowed


def datarec(_cls=None, **kwargs):
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

    def decorator(cls):
        data_record = attr.s(cls, slots=True, kw_only=True, **kwargs)

        extracted_attrs = _construct_attr_docstring(data_record)

        data_record.__doc__ = f"{data_record.__doc__}\n{extracted_attrs}"
        return data_record

    if _cls is None:
        return decorator

    return decorator(_cls)


def _construct_attr_docstring(inst: t.Any):
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
        type_str = (
            str(field.type)[len("<class '") : 0 - len("'>")]
            if "<class" in str(field.type)
            else str(field.type)
        )

        # Get the attribute name and type
        attr_str = f"{field.name} ({type_str}):{docstr}"

        # Check if there is a default value -- if the default is an empty string
        if field.default != attr.NOTHING:
            default = field.default if str(field.default) != "" else "''"
            default_str = f" | Default={default}"
        else:
            default_str = ""

        # Append to the end of the string.
        fields_str = f"{fields_str}\n    {attr_str}{default_str}"

    return fields_str


def item(
    *,
    data_type: type,
    keyword: t.Union[str, t.Tuple],
    serializer: t.Optional[t.Callable] = None,
    do_not_serialize: bool = False,
    docstr: str = "",
    **kwargs,
):
    """
    Creates an item in a data record.

    Note that this uses attr.ib_ in the background. Adds the *keyword*
    metadata tag automatically. Takes all other keywords for
    `attr.ib <https://www.attrs.org/en/stable/api.html#attr.ib>`_.

    """

    # Check that None is allowed.
    if do_not_serialize and not check_none_allowed(data_type):
        raise AttributeError(
            "Any item with do_not_serialize requires its type to accept None."
        )

    # Handle metadata
    metadata = {} if "metadata" not in kwargs else kwargs["metadata"]
    metadata["keyword"] = keyword
    metadata["docstr"] = docstr
    metadata["do_not_serialize"] = do_not_serialize

    # Autogen converters
    if "converter" not in kwargs:
        converter = get_constr_method(data_type, recurse=True)
    else:
        converter = kwargs["converter"]
        del kwargs["converter"]

    def wrapped_converter(x):
        try:
            return converter(x)
        except Exception as e:
            tb = sys.exc_info()[2]
            raise TypeError(
                f'Error when converting field with keyword:: "{keyword}"'
                + f"\n{str(e)}"
            ).with_traceback(tb)

    def _no_serialize(x):
        return None

    # Autogen serializers
    if do_not_serialize:
        metadata["serializer"] = _no_serialize
    elif serializer is not None:
        metadata["serializer"] = serializer
    else:
        metadata["serializer"] = get_serialization_method(data_type, recurse=True)

    return attr.ib(
        type=data_type, metadata=metadata, converter=wrapped_converter, **kwargs
    )


def _construct_dictconstructable(
    t: type, x: t.Any, recurse: bool
) -> "DictConstructable":
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
        raise TypeError(f"Type {type(x)} cannot be made into {t}.")


@datarec
class DictConstructable(Serializable):
    """
    A class representing datarec that can be constructed from a dictionary.
    Note that this any class extending this one must also have the @datarec
    decorator.
    """

    _DICT_CONSTRUCTABLE = True

    @classmethod
    def get_metadata(cls, field_name: str):
        """ """
        return attr.fields_dict(cls)[field_name].metadata

    @classmethod
    def get_default_val(cls, field_name: str):
        """ """
        field_value = attr.fields_dict(cls)[field_name]
        if not isinstance(field_value.default, attr.Factory):
            return field_value.default
        if hasattr(field_value.default, "takes_self"):
            if field_value.default.takes_self:
                return ValueError(
                    'Cannot get default value of a Factory which "takes_self".'
                )
        return field_value.default()

    @classmethod
    def get_all_field_names(cls):
        return attr.fields_dict(cls).keys()

    @classmethod
    def get_all_valid_keywords(cls):
        """ """
        kws = []
        for f in attr.fields_dict(cls).keys():
            kw = cls.get_metadata(f)["keyword"]
            if isinstance(kw, tuple):
                kws.extend(kw)
            else:
                kws.append(kw)
        return kws

    @classmethod
    def from_JSON_string(cls, json_data: str):
        """
        Create a dict constructable from a JSON string.

        Args:
            json_data:
                The JSON string representing the DictConstructable object.

        Returns:
            An instance of the DictConstructable class from the JSON.

        """

        json_data = json_data[json_data.find("{") : json_data.rfind("}") + 1]

        return cls.from_dict(json.loads(json_data))

    @classmethod
    def from_YAML_string(cls, yaml_data: str):
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
    def from_dict(cls, obj_dict: t.Dict, recurse: bool = True):
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

            # Check if list of keywords
            if isinstance(keyword, tuple) or isinstance(keyword, list):
                kw_list = keyword
            else:
                kw_list = [keyword]

            for kw in kw_list:
                if kw in obj_dict:
                    kwargs[field.name] = obj_dict[kw]
                    break
        return cls(**kwargs)

    def to_JSON_string(self) -> str:
        """
        Returns the dict constructable as a JSON string.

        Return:
            A JSON string representing the DictConstructable object.

        """

        d = self.to_dict(recurse=True, serialize=True)

        return json.dumps(d)

    def to_YAML_string(self, line_break=False) -> str:
        """
        Returns the dict constructable as a YAML string.

        Return:
            A YAML string representing the DictConstructable object.

        """
        d = self.to_dict(recurse=True, serialize=True)

        if line_break:
            return yaml.safe_dump(d, line_break="\n", indent=4)
        else:
            return yaml.safe_dump(d)

    @classmethod
    def from_serializable(
        cls, o: t.Optional[t.Union[str, int, float, list, bool, dict, Serializable]]
    ) -> Serializable:
        """
        Construct from serializable types.
        """

        if isinstance(o, cls):
            return o

        if isinstance(o, dict):
            return cls.from_dict(o, recurse=True)

        if isinstance(o, str):
            try:
                return cls.from_dict(yaml.safe_load(o))
            except Exception:
                raise TypeError(f"String cannot be deserialized into {cls}")
        else:
            raise TypeError(f"Type {type(o)} cannot be made into {cls}.")

    def to_dict(
        self,
        recurse: bool = True,
        serialize: bool = True,
        use_keyword: bool = True,
        remove_val_eq_default: bool = False,
        filter_function: t.Optional[t.Callable] = None,
    ) -> t.Dict:
        """
        To a dictionary.

        Args:
        recurse (bool, optional):
            Recurse through all collection like items and turn into dictionaries.
            Defaults to True.
        serialize (bool, optional):
            Serializes all items if possible. Automatically sets recures to true.
        use_keyword (bool, optional):
            Use the keyword in the dictionary.
        remove_val_eq_default (bool, optional):
            Removes keys where the value is the default value.

        Returns:
        A dictionary representing the DictConstructable object.
        """
        d = {}
        value = None
        for k, v in attr.asdict(self, recurse=False, filter=filter_function).items():
            metadata = self.get_metadata(k)
            if metadata["do_not_serialize"]:
                continue

            serializer = metadata["serializer"]

            try:
                if serialize:
                    value = serializer(v)
                else:
                    value = (
                        self._recurse_items(v, use_keyword=use_keyword)
                        if recurse
                        else v
                    )
            except TypeError:
                pass

            # Check if default value
            if remove_val_eq_default:
                if value == self.get_default_val(k):
                    continue

            if use_keyword:
                kw = metadata["keyword"]
                if isinstance(kw, tuple) or isinstance(kw, list):
                    if len(kw) == 0:
                        raise TypeError(
                            f"Keyword list for field {k} is empty in obj"
                            + f"{self.__class__.__name__}"
                        )
                    # Take the first keyword.
                    kw = kw[0]

                d[kw] = value
            else:
                d[k] = value

        return d

    def _recurse_items(self, v: t.Any, use_keyword=True):
        if isinstance(v, list):
            return [
                (
                    e.to_dict(recurse=True, use_keyword=use_keyword)
                    if self.is_constructable(e)
                    else e
                )
                for e in v
            ]

        if isinstance(v, dict):
            return {
                k: (
                    e.to_dict(recurse=True, use_keyword=use_keyword)
                    if self.is_constructable(e)
                    else e
                )
                for k, e in v.items()
            }

        return v

    def to_dataframe_record(
        self,
        filter_function: t.Optional[t.Callable[[attr.Attribute, t.Any], bool]] = None,
        process_function: t.Optional[t.Callable[[t.Dict], t.Dict]] = None,
        recurse: bool = False,
        use_keyword: bool = False,
        add_self: t.Optional[str] = None,
    ) -> t.Dict:
        """
        Returns a dataframe record representing this Data Record.

        Params:

        Returns:
        A dictionary representing the record.
        """
        d = self.to_dict(
            recurse=recurse,
            serialize=True,
            filter_function=filter_function,
            use_keyword=use_keyword,
        )
        if add_self is not None:
            d[add_self] = self
        return process_function(d) if process_function is not None else d

    def to_serializable(self):
        """
        Returns:
        The object in a serializable form.
        """
        return self.to_dict(recurse=True, use_keyword=True, serialize=True)

    def pretty(self) -> str:
        """
        Returns a prettified version of a data record.
        (YAML for now)

        Returns:
            A pretty string representing the object.
        """
        return self.to_YAML_string(line_break=True)

    def __str__(self) -> str:
        """
        String representation of the data record.

        Returns:
            A string representation of the data record.
        """
        d = self.to_dict(serialize=True, use_keyword=False)
        return "{}({})".format(
            self.__class__.__name__, ", ".join([f"{k}={v}" for k, v in d.items()])
        )

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
