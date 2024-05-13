#!/usr/bin/env python3

# pyre-unsafe
"""utils for manage NMVE drive"""
import json
import re
import time
from enum import auto, Enum
from typing import Dict, List, Optional, TYPE_CHECKING

from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils


if TYPE_CHECKING:
    from autoval.lib.host.host import Host


class NVMeDeviceEnum(Enum):
    """Class for NVME drives enumeration"""

    BLOCK = auto()
    CHARACTER = auto()
    PARTITION = auto()
    INVALID = auto()


class NVMeUtils:
    """Class for NVME drives"""

    @staticmethod
    def get_nvme_device_type(device_name: str) -> NVMeDeviceEnum:
        """
        Determine if nvme dev is a block-dev / char-dev or nvme partition
        @param String block_name: e.g. nvme1n1 or char_name: eg nvme1 or parition
            eg nvme1n1p1
        @return dictionary of id-ctrl output
        """
        # Matches nvme block device (e.g. nvme1), character device (e.g. nvme1n1) or
        # nvme partition (e.g. nvme1n2p1)
        nvme_dev_re = re.compile(
            r"nvme(?P<ctrlnum>\d+)(n(?P<nsid>\d+)(p(?P<partid>\d+)?)?)?$"
        )
        match = nvme_dev_re.match(device_name)
        if match:
            if match.group("nsid") is None:
                return NVMeDeviceEnum.CHARACTER
            if match.group("partid") is None:
                return NVMeDeviceEnum.BLOCK
            return NVMeDeviceEnum.PARTITION
        return NVMeDeviceEnum.INVALID

    @staticmethod
    def get_id_ctrl(host, device_name) -> Dict:
        """
        @param Host : host
        @param String block_name: e.g. nvme1n1 or char_name: eg nvme1
        @return {} dictionary of id-ctrl output
        """
        id_ctrl = {}
        cmd = "nvme id-ctrl /dev/%s" % device_name + " -o json"
        ret = host.run_get_result(cmd)  # noqa
        id_ctrl = AutovalUtils.loads_json(ret.stdout)
        return id_ctrl

    @staticmethod
    def get_id_ctrl_normal_data(host, device_name: str) -> str:
        """This function will give the controller info output in a normal format
           for the given controller.

        Args:
            Host: This is the host object.
            device_name: This is the drive name eg nvme1/nvme1n1

        Returns:
           normal output of the given controller
        """
        cmd = "nvme id-ctrl /dev/%s" % device_name + " -o normal | grep -v fguid"
        out = host.run_get_result(cmd).stdout
        return out

    @staticmethod
    def get_id_ns(host, device_name: str, nsid: Optional[int] = None) -> Dict:
        """
        Return identify namespace json output.
        @param Host : host
        @param str : block_name
        @param int : nsid
        If device_name represents a character device (e.g. nvme1), nsid is mandatory.
        If device_name represents a block device (e.g. nvme1n1, nsid may be skipped.
        @return {} : namespace id
        """
        id_ns = {}
        device_type = NVMeUtils.get_nvme_device_type(device_name)
        if device_type not in (NVMeDeviceEnum.BLOCK, NVMeDeviceEnum.CHARACTER):
            raise TestError(
                f"{device_name} is of type {device_type.value}."
                "Needs to be block or character device"
            )
        if device_type == NVMeDeviceEnum.CHARACTER:
            if nsid is None:
                raise TestError(f"delete_ns: missing NSID for char dev {device_name}")
        cmd = f"nvme id-ns /dev/{device_name} -o json"
        if nsid is not None:
            cmd += f" -n {nsid}"
        ret = host.run_get_result(cmd)
        id_ns = AutovalUtils.loads_json(ret.stdout)
        return id_ns

    @staticmethod
    def get_vendor_id(host, block_name) -> int:
        """
        @param String block_name: e.g. nvme1n1
        @return int: vendor id
        """
        id_ctrl = NVMeUtils.get_id_ctrl(host, block_name)
        try:
            vid = int(id_ctrl["vid"])
        except ValueError:
            int(id_ctrl["vid"], 16)
        # pyre-fixme[61]: `vid` may not be initialized here.
        return vid

    @staticmethod
    def get_nvme_version(host) -> str:
        """Return NVME version"""
        out = host.run("nvme version")
        match = re.search(r"\d+\.\d+.*", out)
        if match:
            return match.group(0)
        raise TestError("nvme version not detected: %s" % out)

    @staticmethod
    def get_nvme_list(host):
        """
        Return list of dictionaries containing NVMe drive info
        [
            { "DevicePath" : "/dev/nvme0n1", "ModelNumber": "...", ... },
            { "DevicePath" : "/dev/nvme1n1", "ModelNumber": "...", ... }
        ]
        """
        ret = host.run_get_result("nvme list -o json")
        nvme_list = json.loads(ret.stdout)
        return nvme_list["Devices"]

    @staticmethod
    def get_from_nvme_list(host, block_name, field):
        """
        @param String block_name: e.g. nvme1n1
        @param String field: field to update
        @return String: value of given field
        """
        nvme_list = NVMeUtils.get_nvme_list(host)
        path = "/dev/%s" % block_name
        try:
            drive_data = [dr for dr in nvme_list if dr["DevicePath"] == path].pop()
        except IndexError:
            raise TestError(
                "Unable to find DevicePath for %s in %s" % (block_name, nvme_list)
            )
        if field not in drive_data:
            raise TestError("Unable to find %s in %s" % (field, drive_data))
        if isinstance(drive_data[field], str):
            return drive_data[field].strip()
        return drive_data[field]

    @staticmethod
    def get_nvme_ns_map(host, blockname, serial_number):
        """
        To get the list of namespace associated with nvme drive.
        This is done by Mapping the NameSpace with the same Serial number.
        @return {'nvme0': ['nvme0n1', 'nvme0n2']}
        """
        nvme_info = {}
        namespaces = []
        drives = NVMeUtils.get_nvme_list(host)
        match = re.search(r"(nvme\d*)", blockname)
        if match:
            nvme_drive = match.group(1)
        else:
            raise TestError("NVME drives not found: %s" % drives)
        for drive in drives:
            match = re.search(r"^/dev/(\w+)", drive["DevicePath"])
            if match:
                n_s = match.group(1)
                if serial_number in drive["SerialNumber"]:
                    namespaces.append(n_s)
        nvme_info = {nvme_drive: namespaces}
        return nvme_info

    @staticmethod
    def format_nvme(
        host, device, secure_erase_option, block_size=None, nvme_format_args=None
    ) -> None:
        """Format nvme drives"""
        cmd = "nvme format /dev/%s -s %s -r" % (device, secure_erase_option)
        # Add the option to set block size during drive format
        if block_size:
            cmd += f" -b {block_size}"
        # Additional commands append to the original command for few SSD models
        if nvme_format_args:
            cmd += nvme_format_args
        # Some drive required more time to erase user data
        timeout = 3610
        if secure_erase_option == 1:
            timeout = 36100  # 10 hours noqa
        AutovalLog.log_info("Running command: %s" % cmd)
        host.run(cmd=cmd, timeout=timeout)  # noqa

    @staticmethod
    def get_nvme_temperature(host, devices):
        """Return NVME temperature"""
        nvme_temp = []
        for nvme in devices:
            temp = NVMeUtils.get_nvmedrive_temperature(host, nvme)
            nvme_temp.append(temp)
        return nvme_temp

    @staticmethod
    def get_write_cache(host, drive):
        """
        Method to get the write cache value on the drive.
        @param: string : drive
        @return integer
        """
        # Remove namespace
        device = drive
        match = re.search(r"(nvme\d+)", str(drive))
        if match:
            device = match.group(1)
        cmd = "nvme get-feature /dev/%s -f 0x6" % device
        output = host.run(cmd, ignore_status=True)
        # For not supported devices
        if "INVALID_FIELD" in output:
            return None
        match = re.search(r"Current value:\s*((0x)?[0-9]+)", output)
        if match:
            return int(match.group(1), 0)
        return None

    @staticmethod
    def enable_write_cache(host, drive, save: bool = False) -> None:
        """
        Method to enable the write cache on nvme drive.
        @param: string : drive
        """
        # Remove namespace
        device = drive
        match = re.search(r"(nvme\d+)", str(drive))
        if match:
            device = match.group(1)
        cmd = "nvme set-feature /dev/%s -f 0x6 -v 1" % device
        out = host.run(cmd, ignore_status=True)
        if "not support" in out:
            AutovalLog.log_info(f"Enable write_cache not supported on {drive}: {out}")

    @staticmethod
    def disable_write_cache(host, drive, save: bool = False) -> None:
        """
        Method to disable write cache on the nvme drive.
        @param: string : drive
        """
        # Remove namespace
        device = drive
        match = re.search(r"(nvme\d+)", str(drive))
        if match:
            device = match.group(1)
        cmd = "nvme set-feature /dev/%s -f 0x6 -v 0" % device
        out = host.run(cmd, ignore_status=True)
        if "not support" in out:
            AutovalLog.log_info(f"Disable write_cache not supported on {drive}: {out}")

    @staticmethod
    def list_ns(host, device_name):
        """List of all namespaces"""
        cmd = f"nvme list-ns /dev/{device_name}"
        out = host.run(cmd)
        _list = re.findall(r"\[\s+\d+\]:(0x.*)", out)
        ns_list = [int(x, 16) for x in _list]
        return ns_list

    @staticmethod
    def delete_ns(host, device_name: str, nsid: Optional[int] = None) -> None:
        """
        Method to delete a namespace.
        If device_name represents a character device (e.g. nvme1), nsid is mandatory.
        If device_name represents a block device (e.g. nvme1n1, nsid may be skipped.
        If nsid is provided for a block device, it overrides the block nsid.
        @param Host : host
        @param str : device_name
        @param int : nsid
        @return int : return_code from command run
        """
        device_type = NVMeUtils.get_nvme_device_type(device_name)
        if device_type not in (NVMeDeviceEnum.BLOCK, NVMeDeviceEnum.CHARACTER):
            raise TestError(
                f"{device_name} is of type {device_type.value}."
                "Needs to be block or character device"
            )
        cmd = f"nvme delete-ns /dev/{device_name}"
        if nsid is None:
            nsid = NVMeUtils.list_ns(host, device_name)
            for i in nsid:
                cmd2 = cmd + f" -n {i}"
                host.run(cmd=cmd2)
        else:
            cmd += f" -n {nsid}"
            host.run(cmd=cmd)

    @staticmethod
    def create_ns(host, char_name: str, nsze, ncap, block_size, flbas_flag) -> int:
        """
        Method to create a namespace on a block device, with a specified size
        and capacity.
        @param Host : host
        @param str : char_name
        @param int : nsze
        @param int: ncap
        @param int: block_size
        @param int: flbas_flag
        @return int : return_code from command run
        """
        device_type = NVMeUtils.get_nvme_device_type(char_name)
        if device_type != NVMeDeviceEnum.CHARACTER:
            raise TestError(
                f"{char_name} is of type {device_type.value}."
                "Needs to be character device"
            )

        return host.run(
            f"nvme create-ns -f {flbas_flag} /dev/{char_name} -s {nsze} -c {ncap}"
        )

    @staticmethod
    def attach_ns(host, char_name: str, nsid, cntlid) -> int:
        """
        Method to create a namespace on a block device, with a specified size
        and capacity.
        @param Host : host
        @param str : char_name
        @param int: cntlid
        @return int : return_code from command run
        """
        device_type = NVMeUtils.get_nvme_device_type(char_name)
        if device_type != NVMeDeviceEnum.CHARACTER:
            raise TestError(
                f"{char_name} is of type {device_type.value}."
                "Needs to be character device"
            )
        return host.run(f"nvme attach-ns /dev/{char_name} -n {nsid} -c {cntlid}")

    @staticmethod
    def detach_ns(host, char_name: str, nsid, cntlid) -> int:
        """Detach namespace from nvme drive"""
        device_type = NVMeUtils.get_nvme_device_type(char_name)
        if device_type != NVMeDeviceEnum.CHARACTER:
            raise TestError(
                f"{char_name} is of type {device_type.value}."
                "Needs to be character device"
            )
        return host.run(f"nvme detach-ns /dev/{char_name} -n {nsid} -c {cntlid}")

    @staticmethod
    def reset(host, char_name: str) -> None:
        """
        Method to create a namespace on a block device, with a specified size
        and capacity.
        @param Host : host
        @param str : char_name
        @return int : return_code from command run
        """
        device_type = NVMeUtils.get_nvme_device_type(char_name)
        if device_type != NVMeDeviceEnum.CHARACTER:
            raise TestError(
                f"{char_name} is of type {device_type.value}."
                "Needs to be character device"
            )
        out = host.run(cmd=f"nvme reset /dev/{char_name}", ignore_status=True)
        if "dropped connection" in out:
            time.sleep(5)

    @staticmethod
    def get_nvmedrive_temperature(host, drive) -> int:
        """
        Method to get the nvme drive temperature.
        @param: string : drive
        """
        nvme_temp = 0
        cmd = "nvme smart-log /dev/%s" % drive
        out = host.run(cmd)
        match = re.search(r"temperature\s+:\s+(\d+)\s+C", out)
        if match:
            nvme_temp = match.group(1)
        return int(nvme_temp)

    @staticmethod
    def is_read_only(host, drive: str) -> bool:
        """Is read only

        Method to check the drive is a readonly device. As per the NVMe
        spec the if the critical_warning value 0x8 (1 << 3). It whould be
        a Read only device.

        Parameters
        ----------
        drive : String
            Drive Block Name.
        """
        cmd = "nvme smart-log /dev/%s -o json" % drive
        ret = host.run_get_result(cmd)
        out_json = AutovalUtils.loads_json(ret.stdout)
        if "critical_warning" in out_json:
            if (out_json["critical_warning"]) & (1 << 3):
                return True
        return False

    @staticmethod
    def drive_error_injection(host, drive, bs: int = 4096) -> None:
        """
        This function performs NVME error injection
        """
        host.run(
            cmd=f"echo 'hello world' | nvme write /dev/{drive} --data-size={bs} --prinfo=1"
        )
        ret = host.run_get_result(
            cmd=f"nvme read /dev/{drive} --data-size=520 --prinfo=1",
        )
        AutovalUtils.validate_in(
            "hello world", ret.stdout, f"Write and read successfull on /dev/{drive}"
        )
        # Inject error
        AutovalLog.log_info(
            f"Running NVME uncorrectable error injection on /dev/{drive}"
        )
        host.run(cmd=f"nvme write-uncor /dev/{drive} --block-count=1")
        # Validate injection
        ret = host.run_get_result(
            f"nvme read /dev/{drive} --data-size={bs} --prinfo=1",
            ignore_status=True,
        )
        AutovalUtils.validate_condition(
            ret.return_code, "Failure expected in 'nvme read'"
        )
        ret = host.run_get_result(
            f"sg_read bs={bs} count=1 if=/dev/{drive}",
            ignore_status=True,
        )
        AutovalUtils.validate_condition(
            ret.return_code, "Failure expected in 'sg_read'"
        )
        # Clear injection
        AutovalLog.log_info(f"Clear the error on /dev/{drive}")
        host.run(cmd=f"dd if=/dev/zero of=/dev/{drive} bs={bs} count=10 seek=0")
        host.run(
            cmd=f"echo 'hello world' | nvme write /dev/{drive} --data-size={bs} --prinfo=1"
        )
        ret = host.run_get_result(
            cmd=f"nvme read /dev/{drive} --data-size={bs} --prinfo=1",
        )
        AutovalUtils.validate_in(
            "hello world", ret.stdout, f"Error_injection completed on /dev/{drive}"
        )

    @staticmethod
    def get_namespace_support_drive_list(
        host: "Host", drive_list: List[str]
    ) -> List[str]:
        """
        Method to check if drive suppors Namespace Management.
        Parametrs
        ---------
        drive_list: List
           List of drives
        Returns
        -------
        supported_ns_drivelist: List
           List of drives
        """
        supported_ns_drivelist = []
        for drive in drive_list:
            cmd = "nvme id-ctrl /dev/%s -H | grep -v fguid" % drive
            out = host.run_get_result(cmd).stdout
            pattern = r"\s+NS Management and Attachment Supported"
            found_obj = re.search(pattern, out)
            if found_obj:
                supported_ns_drivelist.append(drive)
        return supported_ns_drivelist

    @staticmethod
    def run_nvme_security_recv_cmd(host: "Host", block_name: str) -> str:
        """Run Nvme security-recv command.

        Parametrs
        ---------
        host: Host class object.
        block_name: String block_name of the drive

        Returns
        -------
        out: String
            Output of the sec-recv command
        """
        # Pull 256 bytes of data. This should be large enough for all models
        cmd = f"nvme security-recv -p 0x1 -s 0x1 -t 256 -x 256 /dev/{block_name}"
        AutovalLog.log_info(f"Running command: {cmd}")
        out = host.run(cmd)
        return out

    @staticmethod
    def get_thermal_management(host, drive):
        """
        Method to get the tmt value on the drive.
        @param: string : drive
        @return integer
        """
        cmd = "nvme get-feature /dev/%s -f 0x10" % drive
        output = host.run(cmd, ignore_status=True)
        if "INVALID_FIELD" in output:
            return None
        match = re.search(r"Current value:((0x)?[0-9a-f]+)", output)
        if match:
            return int(match.group(1), 0)
        return None

    @staticmethod
    def set_thermal_management(host, drive, updated_tmt) -> bool:
        """
        Method to get the tmt value on the drive.
        @param: string : drive
        @return integer
        """
        cmd = "nvme set-feature /dev/%s -f 0x10 -v %s" % (drive, hex(updated_tmt))
        output = host.run(cmd, ignore_status=True)
        if "INVALID_FIELD" not in output:
            return True
        return False
