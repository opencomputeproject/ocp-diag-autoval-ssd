# pyre-unsafe
"""System utils"""

import re
import time
from os import path
from typing import Collection, List, Optional

from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import (
    CmdError,
    HostException,
    SystemInfoException,
    TestError,
)
from autoval.lib.utils.site_utils import SiteUtils


class SystemUtils:
    """Class for System utils"""

    @staticmethod
    def get_pkg_mgr(host) -> str:
        """Get package manager dnf or yum"""
        pkg_mgrs = ["yum", "dnf"]
        for pkg_mgr in pkg_mgrs:
            ret = host.run_get_result(f"which {pkg_mgr}", ignore_status=True)
            if ret.return_code == 0:
                return pkg_mgr
        raise TestError(f"Unable to find installed package manager {pkg_mgrs}")

    @staticmethod
    def get_current_date_time() -> str:
        """This function will return the current date and time in the below
        format - 2023-04-16 10:02:48

        Returns:
            cur_sys_time: the time and date in string format
        """
        curr_time = time.strptime(time.ctime())
        cur_sys_time = time.strftime("%Y-%m-%d %H:%M:%S", curr_time)
        return cur_sys_time

    @staticmethod
    def install_rpms(
        host,
        rpm_list: Collection[str],
        from_autoval_tool_path: Optional[bool] = False,
        force_install: Optional[bool] = False,
        disable_fava_repo: Optional[bool] = False,
        reinstall: bool = False,
        pkg_mgr=None,
        disable_tools_upgrade=None,
    ) -> None:
        """
        To install the list of the rpms
        Parameters:
            rpm_list    : list of rpms to be installed such as ["fb-attestcli",..]
            from_autoval_tool_path   : rpm is placed under Autoval tools dir
            force_install : bool (True|False) will forcefully install the rpm
            reinstall : bool (True|False) will forcefully reinstall existing package
            disable_fava_repo :  bool (True|False) To install rpms from other available repo(other than fava repo)

        Returns:
            None

        Raises:
            TestError   : On any exception
        """
        if disable_tools_upgrade is None:
            disable_tools_upgrade = []
        if pkg_mgr is None:
            pkg_mgr = SystemUtils.get_pkg_mgr(host)
        else:
            pkg_mgr = pkg_mgr
        for rpm in rpm_list:
            rpm_name = rpm
            if rpm.endswith("rpm"):
                rpm_name = path.splitext(rpm)[0]
            if (
                force_install
                or reinstall
                or "not installed" in SystemUtils.get_rpm_info(host, rpm_name)
            ):
                if from_autoval_tool_path:
                    rpm = host.deploy_tool(rpm)
                    cmd = f"sudo rpm -i {rpm}"
                    if force_install:
                        cmd = f"sudo rpm -i --force {rpm}"
                else:
                    pkgmgr_repo = SiteUtils.get_site_yum_repo_name()
                    # To enable support to install only from fava
                    if pkgmgr_repo and not disable_fava_repo:
                        cmd = f"sudo {pkg_mgr} -y --disablerepo=\\* "
                        if pkg_mgr == "dnf":
                            cmd = f"sudo {pkg_mgr} -y --allowerasing --disablerepo=\\* "
                        cmd += f"--enablerepo={pkgmgr_repo} install {rpm}"
                    # To enable support to install from other available repos (eg., fb-int.repo)
                    elif disable_fava_repo and pkg_mgr == "dnf":
                        cmd = f"sudo {pkg_mgr} -y --allowerasing --disablerepo=fava install {rpm}"
                    else:
                        cmd = f"sudo {pkg_mgr} -y install {rpm}"
                        if pkg_mgr == "dnf":
                            if rpm == "switchtec":
                                cmd = f"sudo {pkg_mgr} -y remove {rpm}"
                                host.run(cmd)
                            cmd = f"sudo {pkg_mgr} -y --allowerasing install {rpm}"
                    if (
                        rpm not in disable_tools_upgrade
                        and pkg_mgr == "dnf"
                        and force_install
                    ):
                        cmd += " -b"
                        if rpm == "tpm2-tools":
                            cmd += " --skip-broken"
                    if (
                        hasattr(host, "product_obj")
                        and SystemUtils.is_property_function_in_obj(
                            host.product_obj, "is_container"
                        )
                        and host.is_container
                    ):
                        version = host.get_os_version()
                        if version.startswith("8"):
                            cmd += " --config /etc/dnf/dnf.conf.8.x"
                    if pkg_mgr == "dnf" and reinstall:
                        cmd = cmd.replace("install", "reinstall")
                try:
                    result = host.run_get_result(cmd=cmd, ignore_status=True)
                    if result.return_code != 0:
                        error_type = ErrorType.RPM_INSTALLATION_FAILED_ERR
                        error_msg = result.stdout + result.stderr
                        if "Unable to find a match" in error_msg:
                            error_type = ErrorType.RPM_NOT_FOUND_ERR
                        raise TestError(
                            f"Failed to install rpm {rpm}, Reason: {error_msg}",
                            error_type=error_type,
                        )
                except HostException as exc:
                    raise TestError(
                        f"FAILED - Failed to install rpm {rpm}, Reason: {str(exc)}",
                        exception=exc,
                    )

    @staticmethod
    def is_property_function_in_obj(obj, func_name) -> bool:
        """
        Return True if a given object has a property function with a given name.

        Args:
            obj: Object to check for property function.

            func_name: Name of the property function to look for.

        Returns:
            Boolean indicating whether the object has a property function
            with the given name.
        """
        return isinstance(getattr(type(obj), func_name, None), property)

    @staticmethod
    def uninstall_rpms(host, rpm_list: List[str], tool_path=None) -> None:
        """Uninstall selected rpms"""
        pkg_mgr = SystemUtils.get_pkg_mgr(host)
        for rpm in rpm_list:
            # Use yum for uninstalling the rpms to take care of dependencies
            cmd = f"sudo {pkg_mgr} remove -y {rpm}"
            host.run(cmd, working_directory=tool_path)

    @staticmethod
    def get_rpm_info(host, rpm: str, field: Optional[str] = None) -> str:
        """Get information about installed RPM package or specified RPM package file.

        Args:
            host (Host): Host object on which we operate with the package.
            rpm (str): Either name of installed RPM package or path to the RPM package file.
            field (str): Specific field name to retrieve information about.

        Returns:
            str: either full name of installed package in case field is None,
                 (or value of the specified field if field is specified)
                 or info about the specified RPM package file.

        Raises:
            CmdError: if command failed to execute.

        Examples:
            >>> SystemUtils.get_rpm_info(host, "agfhc")
            agfhc-1.5.2-1.noarch

            >>> SystemUtils.get_rpm_info(host, "agfhc", "Version")
            1.5.2

            >>> SystemUtils.get_rpm_info(host, "/tmp/agfhc-1.5.2-centos9.el9.noarch.rpm", "Vendor")
            Advanced Micro Devices
        """
        cmd = f"rpm --query {rpm}"
        cmd += " --package" if rpm.endswith(".rpm") else ""
        cmd += " --info" if field else ""
        try:
            out: str = host.run(cmd)
        except CmdError as exc:
            if "not installed" in str(exc):
                # just return as is e.g.
                # package <some package> is not installed
                return str(exc)
            raise exc
        if not field:
            return out.strip()
        # parse the field value
        regex = re.compile(f"{field}\\s+:\\s+(.+)$", re.IGNORECASE | re.MULTILINE)
        match = regex.search(out)
        return match.group(1) if match else ""

    @staticmethod
    def update_permission(host, permission, filename, filepath=None) -> None:
        """Update permission on file"""
        host.run("chmod %s %s" % (permission, filename), working_directory=filepath)

    @staticmethod
    def get_pip_info(host, pip_pkg):
        """Get pip info from package"""
        out = host.run_get_result(
            f"pip show {pip_pkg} | grep Version", ignore_status=True
        )
        if out.return_code != 0:
            return None
        out = out.stdout
        return out.split(" ")[1]


def get_acpi_interrupt(host):
    """
    Return acpi interupts
    """
    acpi_difference = {}
    cmd = "grep acpi /proc/interrupts"
    sys_chk_before = host.run(cmd)
    time.sleep(1)
    sys_chk_after = host.run(cmd)
    sys_chk_before = sys_chk_before.split()
    sys_chk_after = sys_chk_after.split()
    diff = list(set(sys_chk_after) - set(sys_chk_before))
    if len(diff) != 0:
        sys_chk_before = [int(s) for s in sys_chk_before if s.isdigit()]
        sys_chk_after = [int(s) for s in sys_chk_after if s.isdigit()]
        for val1, val2 in zip(sys_chk_before, sys_chk_after):
            diff = val2 - val1
            if diff > 1000:
                raise SystemInfoException("larger acpi interrupts hit %d" % (diff))
    acpi_difference = {str(i): sys_chk_after[i] for i in range(0, len(sys_chk_after))}
    return acpi_difference


def match_in_dmidecode(_type, host):
    """
    Returns a dictionary of matched values in dmidecode
    @param type: dmidecode -t option (bios, system, baseboard, chassis,
                 processor, memory, cache, connector, slot)
    """
    if _type not in (
        "bios",
        "system",
        "baseboard",
        "chassis",
        "processor",
        "memory",
        "cache",
        "connector",
        "slot",
    ):
        raise SystemInfoException("match_in_dmidecode: Invalid type")
    cmd = "dmidecode -t %s" % _type
    dmidecode_output = host.run(cmd)
    return parse_dmidecode_output(dmidecode_output)


def get_serial_number(_type, host):
    """Get host serial number"""
    dmidecode = []
    dmidecode = match_in_dmidecode(_type, host)
    serial_number = ""
    for handle in dmidecode:
        if "Serial_Number" in handle:
            serial_number = handle["Serial_Number"]
            break
    if not serial_number:
        raise Exception("No Serial number found in dmidecode")
    return serial_number


def parse_dmidecode_output(output):
    """Parse dmidecode output"""
    main_dict = {}
    mainlist = []
    info_type = None
    flagnext_line = None
    multi_line_val = None
    current_handle = None
    for line in output.splitlines():
        line = line.strip()
        match = re.match(r"Handle\s+(\w+), DMI type (\w+), (\d+) bytes", line)
        if match:
            if main_dict:
                mainlist.append(main_dict)
            current_handle = match.group(1)
            main_dict = {}
            main_dict["dmi_type"] = match.group(2)
            main_dict["no_of_bytes"] = match.group(3)
            main_dict["handle"] = current_handle
            flagnext_line = True
            multi_line_val = False
            continue
        if not current_handle:
            continue
        if flagnext_line:
            info_type = line
            main_dict["device_type"] = info_type.strip().replace(" ", "_")
            flagnext_line = False
            continue
        if not info_type:
            continue
        match = re.match(r"(.*):\s+(.*)", line)
        if match:
            key = match.group(1).strip().replace(" ", "_")
            val = match.group(2).strip().replace(" ", "_")
            main_dict[key] = val
            multi_line_val = False
            multival_key = False
            continue
        match = re.match("(.*):", line)
        if match:
            multival_key = match.group(1).replace(" ", "-")
            multi_line_val = True
            main_dict[multival_key] = []
            continue
        if multi_line_val and multival_key:
            line = line.strip().replace(" ", "_")
            main_dict[multival_key].append(line)
    if main_dict:
        mainlist.append(main_dict)
    return mainlist
