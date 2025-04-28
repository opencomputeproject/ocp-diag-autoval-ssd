# pyre-unsafe
from autoval_ssd.tests.storage_hw_eng.libs.data_types.dmesg_record.dmesg_checks import (
    DmesgCheck,
)


class DmesgCheckComponent(DmesgCheck):
    """
    Dmesg Checker class
    """

    # regex for dmesg checks
    # TODO: DMESG Checks for general system issues.
    COMMON_DMESG_CHECK = []

    def __init__(self):
        """ """
        super().__init__(DmesgCheckComponent.COMMON_DMESG_CHECK)
