# pyre-unsafe
"""
.. fb:display_title::
  Data Size

This file defines the DataSize type.
"""

import re

from .data_record.data_record import Serializable


class DataSize(int, Serializable):
    """
    Class representing the size of Data
    """

    _PREFIX_LUT_1024 = {
        "": 1,
        "k": 1000**1,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
        "P": 1000**5,
        "ki": 1024**1,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "Pi": 1024**5,
    }

    _PREFIX_LUT_1000 = {
        "": 1,
        "k": 1024**1,
        "M": 1024**2,
        "G": 1024**3,
        "T": 1024**4,
        "P": 1024**5,
        "ki": 1000**1,
        "Mi": 1000**2,
        "Gi": 1000**3,
        "Ti": 1000**4,
        "Pi": 1000**5,
    }

    _PREFIX_LUT_1000_CAP = {k.upper(): v for k, v in _PREFIX_LUT_1000.items()}

    _PREFIX_LUT_1024_CAP = {k.upper(): v for k, v in _PREFIX_LUT_1024.items()}

    def __init__(self, i, kb_base=1000):
        """Constructor for a size int"""

        self.kb_base = kb_base

        if isinstance(i, str):
            i = DataSize._str_to_data_size(i, kb_base)

        int.__init__(i)

    @staticmethod
    def _str_to_data_size(i: str, kb_base: int):
        """
        Converts a string into a DataSize obj.
        """
        i = i.upper().strip()
        # Remove trailing B if it exists
        i = i[:-1] if i[-1] == "B" else i
        base = 16 if i[0:2] == "0X" else 10
        p = re.match(r"(0X)?(\d*)\.?(\d*)\s*(\S*)", str(i))
        if p:
            (b, man, dec, exp) = p.groups()
            lut = None
            if kb_base == 1000:
                lut = DataSize._PREFIX_LUT_1000_CAP
            elif kb_base == 1024:
                lut = DataSize._PREFIX_LUT_1024_CAP

            if dec != "":
                if exp not in lut:
                    raise TypeError(f"Cannot Parse {i} into Data Size")
                return int(float(f"{man}.{dec}") * lut[exp])

            return int(man, base) * lut[exp]
        return None

    def __new__(cls, i, kb_base: int = 1000):
        val = DataSize._str_to_data_size(i, kb_base) if isinstance(i, str) else i
        n = int.__new__(cls, val)
        n.kb_base = kb_base

        return n

    def __add__(self, other):
        res = super(DataSize, self).__add__(other)
        return type(self)(res)

    def __sub__(self, other):
        res = super(DataSize, self).__sub__(other)
        return type(self)(res)

    def __mul__(self, other):
        res = super(DataSize, self).__mul__(other)
        return type(self)(res)

    def __div__(self, other):
        res = super(DataSize, self).__div__(other)
        return type(self)(res)

    def __mod__(self, other):
        res = super(DataSize, self).__mod__(other)
        return type(self)(res)

    def __repr__(self):
        return str(int(self))

    def __str__(self):
        if self.kb_base == 1000:
            lut = DataSize._PREFIX_LUT_1000
        elif self.kb_base == 1024:
            lut = DataSize._PREFIX_LUT_1024

        # Create the reverse lookup table
        lut = {v: k for k, v in lut.items()}

        # Find the best-fit suffix for the number
        m = 1
        for k, _ in lut.items():
            if self % k == 0 and k > m:
                m = k

        return "{}{}B".format(repr(self // m), lut[m])

    def to_data_base(self, base: str) -> str:
        """
        To a certain base
        """
        lut = None
        if self.kb_base == 1000:
            lut = DataSize._PREFIX_LUT_1000_CAP
        elif self.kb_base == 1024:
            lut = DataSize._PREFIX_LUT_1024_CAP

        base = base[:-1] if base[-1] == "B" else base
        base = base.upper().strip()

        if base not in lut:
            raise KeyError(f"Unknown base {base}")

        return f"{self / lut[base]}{base}B"

    def to_serializable(self):
        return self.__repr__()

    @classmethod
    def from_serializable(cls, o=Serializable.SerialType):
        return cls(o)
