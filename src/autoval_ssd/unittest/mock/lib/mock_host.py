# pyre-unsafe

import os
import unittest.mock as mock  # noqa
from typing import List, Optional

from autoval.lib.connection.connection_abstract import ConnectionAbstract
from autoval.lib.connection.connection_utils import CmdResult
from autoval.lib.host.bmc import BMC
from autoval.lib.host.system import System
from autoval.lib.utils.autoval_exceptions import CmdError
from autoval.lib.utils.file_actions import FileActions
from autoval_ssd.unittest.mock.lib.mock_connection_dispatcher import (
    MOCK_HOSTS,
    MockConnectionDispatcher,
)
from autoval_ssd.unittest.mock.lib.mock_openbmc import MockOpenBMC


MOCK_INPUT_PATH = "autoval_ssd/unittest/mock/util_outputs/"
MOCK_INPUT_RELATIVE_PATH = "autoval_ssd/unittest/mock/util_outputs/"


class MockHost(ConnectionAbstract):
    def __init__(self, cmd_map, run_return_plain_stdout=False):
        self.run_return_plain_stdout = run_return_plain_stdout
        self.cmd_map = cmd_map
        self.bmc_type = "Openbmc"
        self.connection_obj = MockConnectionDispatcher()
        self.hostname = self.connection_obj.hostname
        self.connection = self.connection_obj.host_connection
        self.localhost = self
        self.oob_addr = self.connection_obj.oob_addr
        self.oob_only = self.connection_obj.oob_only
        self.rack_sub_position = self.connection_obj.rack_sub_position
        self.rack_sub_position_slot = self.connection_obj.rack_sub_position_slot
        self.product_obj = self._get_product_obj()
        self.host.product_obj.product_name = "TestPlatform V2"
        self._openbmc_obj = MockOpenBMC(self, self.cmd_map)._get_openbmc()
        self.host_dict = MOCK_HOSTS
        self.oobs = [self.oob]
        # storage for iterator over run() results
        self._iter_result = {}

    @property
    def openbmc_obj(self):
        return self._openbmc_obj

    @openbmc_obj.setter
    def openbmc_obj(self, cls_obj):
        if isinstance(cls_obj, BMC):
            self._openbmc_obj = cls_obj
        else:
            raise Exception("cls_obj is not an openBMC obj")

    # override run just like for sshpass
    def run(
        self,
        cmd: str,
        ignore_status: bool = False,
        timeout: int = 600,
        working_directory: Optional[str] = None,
        custom_logfile: Optional[str] = None,
        get_pty: bool = False,
        sudo: bool = False,
        sudo_options: Optional[List[str]] = None,
        connection_timeout: int = 60,
        background: bool = False,
        keepalive: int = 0,
        forward_ssh_agent=False,
        path_env=None,
    ) -> str:
        if self.run_return_plain_stdout:
            return self.run_get_result(
                cmd,
                ignore_status,
                timeout,
                working_directory,
                custom_logfile,
                get_pty,
                sudo,
                sudo_options,
                connection_timeout,
                background,
                keepalive,
                forward_ssh_agent,
                path_env,
            ).stdout

        return super(MockHost, self).run(
            cmd,
            ignore_status,
            timeout,
            working_directory,
            custom_logfile,
            get_pty,
            sudo,
            sudo_options,
            connection_timeout,
            background,
            keepalive,
            forward_ssh_agent,
            path_env,
        )

    def run_get_result(
        self,
        cmd: str,
        ignore_status: bool = False,
        timeout: int = 600,
        working_directory: Optional[str] = None,
        custom_logfile: Optional[str] = None,
        get_pty: bool = False,
        sudo: bool = False,
        sudo_options: Optional[List[str]] = None,
        connection_timeout: int = 60,
        background: bool = False,
        keepalive: int = 0,
        forward_ssh_agent=False,
        path_env=None,
    ) -> CmdResult:
        # whether to iterate over multiple result values
        iterate = False
        data = None
        return_code = 0
        for c in self.cmd_map:
            if cmd == c["cmd"]:
                if "return_code" in c:
                    return_code = c["return_code"]
                if "result" in c:
                    data = c["result"]
                else:
                    data = self._read_file(c["file"])
                if "iterate" in c and c["iterate"]:
                    iterate = True
                break
        if iterate and type(data) in (list, tuple):
            if cmd not in self._iter_result:
                self._iter_result[cmd] = iter(data)
        if isinstance(data, CmdError):
            raise data
        if not data:
            data = ""
        if cmd in self._iter_result:
            try:
                return next(self._iter_result[cmd])
            except StopIteration:
                return None  # pyre-fixme[7]
        return CmdResult(cmd, str(data), "", return_code, 1)

    @classmethod
    def read_file(cls, file_path, **kwargs):
        return cls._read_file(file_path, **kwargs)

    def get_file(self, file_path, target, **kwargs):
        pass

    def put_file(self, file_path, target, **kwargs):
        pass

    def scp_file(
        self, source_location: str, file_tocopy: str, destination_location: str
    ) -> str:
        pass

    def get_host_arch(self) -> str:
        pass

    def _connect(self):
        pass

    def _get_product_obj(self):
        system = System(self)
        return system

    @staticmethod
    def _read_file(_file, json_file=False):
        _file = os.path.join(MOCK_INPUT_RELATIVE_PATH, _file)
        # file_path = FileActions.get_resource_file_path(_file[14:])
        return FileActions.read_data(path=_file, json_file=json_file)

    def update_cmd_map(
        self,
        cmd: str,
        mock_output: str,
        is_file: bool = False,
        return_code: str = "0",
    ) -> None:
        """This method will update the command map with the cmd values
        in case if the command is already present it would update the file
        or result value of the command."""
        for each_cmd_map in self.cmd_map:
            if each_cmd_map["cmd"] == cmd:
                each_cmd_map["return_code"] = return_code
                if is_file:
                    each_cmd_map["file"] = mock_output
                else:
                    each_cmd_map["result"] = mock_output
                return
        cmd_map_dict = {"cmd": cmd}
        cmd_map_dict["return_code"] = return_code
        if is_file:
            cmd_map_dict["file"] = mock_output
        else:
            cmd_map_dict["result"] = mock_output
        self.cmd_map.append(cmd_map_dict)

    def add_test_start_msg(self, test_name):

        pass

    def add_test_end_msg(self, test_name):
        pass

    def deploy_tool(self, tool) -> str:
        return ""

    def __getattr__(self, attr):
        if attr == "oob":
            _oob = MockOpenBMC(self, self.openbmc_obj)._get_openbmc()
            setattr(self, "oob", _oob)  # noqa
            return _oob
        return getattr(self.product_obj, attr)

    def revert_cmd_map(self, cmd_map: List):
        for each_cmd_map in cmd_map:
            cmd = each_cmd_map["cmd"]
            if "result" in each_cmd_map:
                self.update_cmd_map(cmd, each_cmd_map["result"], is_file=False)
            else:
                self.update_cmd_map(cmd, each_cmd_map["file"], is_file=True)
