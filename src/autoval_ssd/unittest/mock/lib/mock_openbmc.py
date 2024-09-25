# pyre-unsafe

import os
import unittest.mock as mock

from autoval.lib.host.bmc import BMC
from autoval.lib.utils.file_actions import FileActions


MOCK_INPUT_PATH = "autoval_ssd/unittest/mock/util_outputs/"


class MockOpenBMC:
    def __init__(self, host, cmd_map):
        self.host = host
        self.cmd_map = cmd_map
        self.bmc_host = host

    def run(self, cmd, ignore_status=True):
        data = None
        for c in self.cmd_map:
            if cmd == c["cmd"]:
                data = self._read_file(c["file"])
                break
        return data

    def _get_openbmc(self):
        with mock.patch.object(BMC, "__init__", lambda a, b, c, d: None):
            openbmc = BMC(None, None, None)
            openbmc.slot_info = "slot4"
            openbmc.host = self.host
            openbmc.bmc_host = self.host
            openbmc.config_filter = {}
            return openbmc

    def _read_file(self, _file):
        _file = os.path.join(MOCK_INPUT_PATH, _file)
        file_path = FileActions.get_resource_file_path(_file)
        return FileActions.read_data(file_path)
