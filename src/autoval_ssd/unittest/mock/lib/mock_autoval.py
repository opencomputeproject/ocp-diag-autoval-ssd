# pyre-unsafe

import csv
import logging
import unittest.mock as mock

from autoval.lib.transport.ssh import SSHConn
from autoval.lib.utils.autoval_exceptions import CmdError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils, CmdResult
from autoval.lib.utils.file_actions import FileActions
from autoval_ssd.unittest.mock.lib.mock_host import MockHost

MOCK_INPUT_PATH = "autoval_ssd/unittest/mock/util_outputs/"
MOCK_COMMAND_MAP_PATH = "autoval_ssd/unittest/mock/testbed/cmd_map"


class MockAutovalUtils(MockHost):
    def __init__(self, cmd_map=None):
        self.autovalLog = AutovalLog._init_logs()
        self.logger = logging.getLogger("cmdlog")
        self.cmd_output_dict = None
        self.get_result_obj_rc = 0
        if cmd_map:
            self.cmd_map = cmd_map
        else:
            self.cmd_map = self.generate_cmp_map()
        super(MockAutovalUtils, self).__init__(self.cmd_map)

    @staticmethod
    def generate_cmp_map():
        """This function will convert the cmd_map file into the list of
        dict with in format [{"cmd"="cmd","file"="file_path"},..]"""
        try:
            file_path = FileActions.get_resource_file_path(MOCK_COMMAND_MAP_PATH[14:])
            with open(file_path, "r") as file_context:
                cmd_map_reader = csv.reader(
                    file_context, delimiter=":", quoting=csv.QUOTE_ALL
                )
                """in case cmd has the delimiter part of it, csv reader
                 will consider the last element as "file" and will join
                 the rest of elements to command"""
                cmd_map = [
                    {
                        "cmd": ":".join(each_cmd_map[0:-1]).strip(),
                        "file": each_cmd_map[-1].strip(),
                    }
                    for each_cmd_map in cmd_map_reader
                ]
                return cmd_map
        except Exception:
            raise Exception(
                f"Failed to generate the cmd_map from file {MOCK_COMMAND_MAP_PATH}"
            )

    def run(self, *params, **kparams):
        """Function is side effect of mocking run method and
        will be give a mock output based on the cmd_map
        *params will contain values of cmd from run method
        **kparams will contain the key argument values of get_result_obj,
        ignore_status,custom_logfile cmd_output_dict is used
        in case cmd_map is not to be referred  which would be and optimised way
        in case we have single line output instead of creating file
        get_result_obj_rc return code of command run by default set to 0
        """
        data = None
        cmd = params[0]
        get_result_obj = kparams.get("get_result_obj")
        ignore_status = kparams.get("ignore_status")
        if self.cmd_output_dict and cmd in self.cmd_output_dict:
            data = self.cmd_output_dict[cmd]
            if isinstance(data, Exception):
                raise data
        else:
            if get_result_obj:
                data = self.run_get_result(cmd, ignore_status)
            else:
                data = super(MockAutovalUtils, self).run(cmd, ignore_status)
        if get_result_obj:
            data = CmdResult(cmd, data, "", self.get_result_obj_rc)
            if self.get_result_obj_rc and not ignore_status:
                raise CmdError(cmd, data, "command failed")
        return data

    def get_mock_data(self, funct, *args, **kwargs):
        """Function will mock the methods which should run on Dut
        such as run"""
        self.cmd_output_dict = kwargs.pop("cmd_output_dict", None)
        self.get_result_obj_rc = kwargs.pop("get_result_obj_rc", 0)
        with mock.patch.object(
            SSHConn, "scp_file", return_value="pass"
        ), mock.patch.object(SSHConn, "run", side_effect=self.run), mock.patch.object(
            AutovalUtils, "run_get_output", side_effect=self.run
        ), mock.patch.object(
            AutovalLog,
            "log_info",
            side_effect=self.logger.info,
        ):
            return funct(*args, **kwargs)
