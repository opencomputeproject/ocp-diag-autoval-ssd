# pyre-unsafe

from autoval.lib.transport.ssh import SSHConn

MOCK_HOSTS = {
    "hostname": "using.fake.host",
    "ipv6": "abcd:db00:0012:700e:face:0000:0023:0000",
    "oob_addr": "using-oob.fake.host",
    "rack_sub_position_slot": 1,
    "is_container": False,
}


class MockConnectionDispatcher:
    def __init__(self):
        self.oob_only = None
        self.host_connection = SSHConn(None)
        self.bmc_connections = [SSHConn(None)]
        self._bmc_connections = [SSHConn(None)]
        self.oob_addr = MOCK_HOSTS.get("oob_addr")
        self.rack_sub_position = MOCK_HOSTS.get("rack_sub_position")
        self.rack_sub_position_slot = MOCK_HOSTS.get("rack_sub_position_slot")
        self.hostname = MOCK_HOSTS.get("hostname")
        self.localhost = None
        self.host_dict = MOCK_HOSTS
