# pyre-unsafe
import typing as t


class Serializable:
    """
    A class representing a serial object. This is helpful for creating
    a standard serialization format without needed to play with different
    encoders/decoders for each library.
    """

    _SERIALIZABLE = True
    SerialType = t.Optional[t.Union[str, int, float, list, bool, dict]]

    def to_serializable(self) -> t.Any:
        """
        To a serializable type (defined by SerialType). Note that
        the default inplementation of this function is just to call
        str() on the object. Please override in child classes.

        Returns:
        The object in a serializable form.
        """
        return str(self)

    @classmethod
    def from_serializable(cls, o: t.Union[t.Optional[t.Any], "Serializable"]):
        return cls

    @staticmethod
    def is_serializable(o: t.Any) -> bool:
        if hasattr(o, "_SERIALIZABLE") and o._SERIALIZABLE:
            return True
        return False
