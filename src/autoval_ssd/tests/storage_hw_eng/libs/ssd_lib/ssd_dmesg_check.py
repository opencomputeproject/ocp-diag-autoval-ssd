# pyre-unsafe
from autoval_ssd.tests.storage_hw_eng.libs.data_types.dmesg_record.dmesg_checks import (
    DmesgCheck,
)


class DmesgCheckSSD(DmesgCheck):
    """
    Dmesg Checker class
    """

    # regex for dmesg checks
    SSD_DMESG_CHECK = [
        r"I\/O error, dev ([a-z0-9\/]+)",
    ]

    def __init__(self):
        """ """
        super().__init__(DmesgCheckSSD.SSD_DMESG_CHECK)
