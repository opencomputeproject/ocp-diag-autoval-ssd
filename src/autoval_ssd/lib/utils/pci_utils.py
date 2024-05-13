#!/usr/bin/env python3

# pyre-unsafe
import os
import re
from typing import Dict, TYPE_CHECKING

from autoval.lib.utils.autoval_errors import ErrorType

from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils

if TYPE_CHECKING:
    from autoval.lib.host.host import Host

SYSFS_PCI_BUS_DEVICES = "/sys/bus/pci/devices/"

# Long PCI address format is as follows
# Domain(32bits):Bus(8bits):Device(5bits):Function(3bits)
# Domain is *not* always 0! (ARM systems have multiple ones)
LONG_PCI_ADDR_REGEX = re.compile(
    r"^([0-9a-fA-F]{2,8}):([0-9a-fA-F]{2}):([01][0-9a-fA-F])[:\.]0*([0-7])$"
)

# Short PCI address format is as follows
# Bus(8bits):Device(5bits).Function(3bits)
SHORT_PCI_ADDR_REGEX = re.compile(r"^([0-9a-fA-F]{2}):([01][0-9a-fA-F])\.([0-7])$")


class PciUtils:
    def get_lspci_output(self, host, options="", custom_logfile=None, exclude=None):
        out = ""
        cmd = "lspci %s" % options
        out = host.run(
            cmd=cmd, custom_logfile=custom_logfile, get_pty=True, ignore_status=True
        )
        if exclude is not None:
            filtered = ""
            for line in out.split("\n"):
                if not any(ex in line for ex in exclude):
                    filtered += line + "\n"
            return filtered
        else:
            return out

    def create_lspci_logfile(self, lspci, sys_chk, host, start, custom_logfile):
        """
        Create lspci -vvv / lspci -xxx output log file
        """
        if sys_chk and "BIGSUR" in sys_chk:
            lspci["lspci_v"] = self.get_lspci_output(
                host, options="-v", custom_logfile=custom_logfile
            )
        else:
            lspci["lspci_vvv"] = self.get_lspci_output(
                host,
                options="-vvv",
                custom_logfile=custom_logfile,
                exclude=["DevSta", "Status"],
            )

    def get_lspci_verbose(self, host, start="None") -> Dict[str, str]:
        """
        Returns lspci -vvv / lspci -xxx output as Dict[str, str]
        """
        lspci = {}
        cmd = "ipmitool fru list"
        sys_chk = host.run(cmd, ignore_status=True)
        if start:
            custom_logfile = "lspci_vvv_before.log"
            self.create_lspci_logfile(lspci, sys_chk, host, start, custom_logfile)
        else:
            custom_logfile = "lspci_vvv_after.log"
            self.create_lspci_logfile(lspci, sys_chk, host, start, custom_logfile)
        lspci["lspci_lnksta_lnkcap"] = self.compare_lspci_lnksta_lnkcap(
            list(lspci.values())[0]
        )
        return lspci

    def compare_lspci_lnksta_lnkcap(self, lspci_output) -> str:
        # compare lspci lnksta speed and capacity woth lnkcap only for network
        # and nvme devices
        devices = ["nvm", "ethernet"]
        status = ""

        for dev in devices:
            dev_list = self.get_lnksta_lnkcap(lspci_output, dev)
            for each in dev_list:
                cap_speed = each["cap_speed"]
                sta_speed = each["sta_speed"]
                cap_width = each["cap_width"]
                sta_width = each["sta_width"]
                dev_line = each["dev_line"]

                if dev_line:
                    result_speed = ""
                    result_width = ""
                    st_speed = "\n %s: 'cap_speed' %s compare to 'sta_speed' %s: %s"
                    st_width = "\n %s: 'cap_width' %s compare to 'sta_width' %s: %s"

                    if cap_speed and sta_speed:
                        if cap_speed == sta_speed:
                            result_speed = "PASS"
                        else:
                            result_speed = "FAIL"

                        status += st_speed % (
                            dev_line,
                            cap_speed,
                            sta_speed,
                            result_speed,
                        )

                    else:
                        status += st_speed % (dev_line, cap_speed, sta_speed, "Failed")

                    if cap_width and sta_width:

                        if cap_width == sta_width:
                            result_width = "PASS"
                        else:
                            result_width = "FAIL"

                        status += st_width % (
                            dev_line,
                            cap_width,
                            sta_width,
                            result_width,
                        )

                    else:
                        status += st_width % (dev_line, cap_width, sta_width, "Failed")

        return status

    def get_lnksta_lnkcap(self, lspci_out, device):
        """
        returns a list of dictionary of device information
            for the provided device type.
        Ex device = "NVM"
        """
        new_list = []
        dct = {}
        include = True
        dev_line = ""
        for line in lspci_out.split("\n"):
            if self._is_dev_line(line):
                if self._include_device(line, device):
                    include = True
                    dev_line = line
                    dct["dev_line"] = dev_line
                    AutovalLog.log_debug("Including device: %s" % (line))
                else:
                    include = False
                    dev_line = ""
            else:
                if not include or not dev_line:
                    continue
                if self._is_link_cap_line(line):
                    dct["cap_speed"], dct["cap_width"] = self._get_dev_data(line)
                if self._is_link_sta_line(line):
                    dct["sta_speed"], dct["sta_width"] = self._get_dev_data(line)
                # check if we have device info, LnkCap  and LnkSya data in dct
                if len(dct) > 3:
                    new_list.append(dct)
                    dct = {}
        return new_list

    def get_lnksta_lnkcap_port(self, host, port, device=None):
        """
        retrieves :: "lspci -vvs port" information for the port provided
        parses :: lspci output
        returns :: device-line, LnkSta speed & width, LnkCap speed & width,
        Secondary bus information if present
        """
        result = {}
        options = "-vvs %s" % port
        out = self.get_lspci_output(host, options=options)
        for line in out.splitlines():
            if device:
                if self._include_device(line, device):
                    result["dev"] = line
            if self._is_link_cap_line(line):
                result["cap_speed"], result["cap_width"] = self._get_dev_data(line)
            if self._is_link_sta_line(line):
                result["sta_speed"], result["sta_width"] = self._get_dev_data(line)
            # secondary_bus check is for gpv2 related device
            if self._is_bus_line(line):
                result["secondary_port"] = self._get_secondary_bus_conn(line)

        return result

    def _is_dev_line(self, line):
        if re.match(r"\S", line):
            # Device lines start with a non-whitespace character
            return True
        else:
            return False

    def _include_device(self, line, device):
        if re.search(device, line, re.IGNORECASE):
            return True
        return False

    def _is_link_cap_line(self, line):
        if re.search("LnkCap:", line):
            return True

    def _is_link_sta_line(self, line):
        if re.search("LnkSta:", line):
            return True
        else:
            return False

    def _is_bus_line(self, line):
        if re.search("Bus:", line):
            return True
        else:
            return False

    def _get_dev_data(self, line):
        speed = None
        width = None

        m = re.search(r"Speed (\w+)", line)
        if m:
            speed = m.group(1)
        m = re.search(r"Width (\w+)", line)
        if m:
            width = m.group(1)
        return (speed, width)

    def _get_secondary_bus_conn(self, line):
        """
        retrieves the Bus information for a Bridge port.
        #Bus: primary=5d, secondary=5e, subordinate=5e, sec-latency=0
        """
        buses = re.search(
            r"Bus: primary=([a-fA-F-0-9]+), secondary=([a-fA-F0-9]+)*", line
        )
        if buses is not None:
            return buses[2] + ":00.0"

    def filter_data(self, output=None, filters=None):
        devices = self.get_device_details(output=output)

        if not filters:
            return {}
        for _path, dev_data in devices.items():
            for _filter in filters:
                _dev_name = _filter["device_name"]
                if re.search(_dev_name, dev_data["name"]):
                    if "filter" not in _filter and "delete_line" not in _filter:
                        dev_data.pop("data", None)
                        continue
                    if "data" in dev_data:
                        if "filter" in _filter:
                            if isinstance(_filter["filter"], list):
                                _filter_list = _filter["filter"]
                            else:
                                _filter_list = [_filter["filter"]]

                            # Filters matches for this device
                            for _filter_str in _filter_list:
                                dev_data["data"] = re.sub(
                                    _filter_str, "", dev_data["data"]
                                )

                        if "delete_line" in _filter:
                            if isinstance(_filter["delete_line"], list):
                                _filter_list = _filter["delete_line"]
                            else:
                                _filter_list = [_filter["delete_line"]]

                            # Remove the lines that matches for this device
                            data_list = dev_data["data"].splitlines()
                            pattern = re.compile("|".join(_filter_list))
                            filtered = list(filter(pattern.match, data_list))
                            for line in filtered:
                                data_list.remove(line)
                            dev_data.update({"data": "\n".join(data_list)})

        return self.details_to_str(devices)

    def get_device_details(self, device=None, output=None):
        """
        Returns device details
        @param device: If specified, returns details for this device path (e.g.
            "00:02.0"). If not specified, returns details for all devices in a
            dictionary.
        """
        if not output:
            output = AutovalUtils.run_get_output(
                cmd="lspci -vvv", custom_logfile="lspci_vvv.log"
            )

        devices = {}
        current_device = None
        for line in output.split("\n"):
            match = re.match(r"([a-z0-9]\S+)\s(.*)", line)
            if match:
                current_device = match.group(1)
                devices[current_device] = {}
                devices[current_device]["name"] = match.group(2)
                devices[current_device]["data"] = ""
            elif current_device:
                devices[current_device]["data"] += line + "\n"

        return devices

    def details_to_str(self, devices):
        """
        Reverses the get_device_details method back into a string
        """

        lspci_str = ""

        for path, dev_data in devices.items():
            # Include the device path and name in each line for debugging
            identifier = "[lspci " + path + " " + dev_data["name"] + "]: "
            if "data" in dev_data:
                data = [identifier + _s.strip() for _s in dev_data["data"].split("\n")]
            else:
                data = [identifier]
            lspci_str += "\n".join(data) + "\n"

        return lspci_str

    def get_nvme_drive_pcie_address(self, host: "Host", device: str) -> str:
        """
        This function will return the pcie address mapping for a given nvme drive.

        Parameters
        ---------
        host: Host
           The host object
        device: String
          Name of the drive

        Returns
        pci_addr: String
          The pci address of the drive
        """
        cmd = "ls -l /sys/block/%s" % device
        output = host.run(cmd)
        pattern = r"([\d\w]+:\d+.\d)\/nvme\/(nvme\d+)\/(nvme\d+[a-z]\d+)"
        output = re.search(pattern, output, re.M)
        if output:
            pci_addr = output.group(1)
            return pci_addr
        else:
            raise TestError("Failed to get pcie address for %s device" % device)

    def set_nvme_drive_pcie_completion_timeout(
        self, host: "Host", device: str, timeout_value: str
    ):
        """
        This function will enable the pcie completion timeout for the given nvme drive.

        Parameters
        ----------
        host: Host
           The host object
        device: String
           Name of the drive
        """
        pci_addr = self.get_nvme_drive_pcie_address(host, device)
        # Based on NVME spec 1.5, setting the 4th bit of PCI Express Device Control 2
        # register.
        cmd = "setpci -s %s CAP_EXP+0x28.w=%s" % (pci_addr, timeout_value)
        host.run(cmd)

    def get_nvme_drive_pcie_completion_timeout_value(
        self, host: "Host", device: str
    ) -> str:
        """
        This function will return the pcie completion timeout value

        Parameters
        ----------
        host: Host
          The host object
        device: String
           Name of the drive
        """
        pci_addr = self.get_nvme_drive_pcie_address(host, device)
        # Based on NVME spec 1.5, PCI Express Device Control 2 register
        # value is returned.
        cmd = "setpci -s %s CAP_EXP+0x28.w" % pci_addr
        return host.run(cmd)

    def get_pci_for_devices(self, host, devices):
        pcie_data = ""
        lspci = self.get_lspci_output(host, options="-vvv")
        for device in devices:
            device = self.get_short_pci_addr(device)
            pattern = r"%s(.*(\n\t.*)+\s*\n)" % device
            match = re.search(pattern, lspci)
            if match:
                pcie_data += match.group(0)
        return pcie_data

    def get_short_pci_addr(self, pci_addr):
        m = LONG_PCI_ADDR_REGEX.match(pci_addr)
        if m:
            _, bus, device, func = map(lambda n: int(n, 16), m.groups())
            pci_addr = "{:02x}:{:02x}.{:x}".format(bus, device, func)
        return pci_addr

    def expand_pci_addr(self, pci_addr):
        """
        Convert a possibly shortened PCI address to its expanded form, including
        normalizing the formatting of long addresses
        """

        m1 = LONG_PCI_ADDR_REGEX.match(pci_addr)
        m2 = SHORT_PCI_ADDR_REGEX.match(pci_addr)

        if m1:
            domain, bus, device, func = map(lambda n: int(n, 16), m1.groups())
            return "{:04x}:{:02x}:{:02x}.{:x}".format(domain, bus, device, func)
        if m2:
            bus, device, func = map(lambda n: int(n, 16), m2.groups())
            return "{:04x}:{:02x}:{:02x}.{:x}".format(0, bus, device, func)
        return None

    def get_pcie_devices(self, host, modules):
        """
        This function gets all/specific devices based on the requirement
        specific devices are determined by the list of modules
        """
        devices = host.run("ls %s" % SYSFS_PCI_BUS_DEVICES).split()
        return list(set(devices).intersection(set(modules)))

    def get_pcie_register_type(self, host, device_name, pci_regs=""):
        """
        This function gets the pci registers based on pci_regs type
        """
        out = ""
        dev_path = os.path.join(SYSFS_PCI_BUS_DEVICES, device_name)
        cmd = "cat %s" % os.path.join(dev_path, pci_regs)
        try:
            out = host.run(cmd)  # noqa
        except Exception:
            AutovalLog.log_info(
                "Unable to get {} info for {}".format(pci_regs, device_name)
            )
        return out

    def get_pcie_device_id(self, host, device_name):
        """
        This function gets the pci device id
        """
        return self.get_pcie_register_type(host, device_name, "device")

    def get_pcie_vendor_id(self, host, device_name):
        """
        This function gets the pci vendor id
        """
        return self.get_pcie_register_type(host, device_name, "vendor")

    def get_pcie_class(self, host, device_name):
        """
        This function gets the pci class id
        """
        return self.get_pcie_register_type(host, device_name, "class")

    def get_pcie_subsystem_vendor(self, host, device_name):
        """
        This function gets pci subsystem_vendor
        """
        return self.get_pcie_register_type(host, device_name, "subsystem_vendor")

    def get_pcie_subsystem_device(self, host, device_name):
        """
        This function gets pci subsystem_device
        """
        return self.get_pcie_register_type(host, device_name, "subsystem_device")

    def get_pcie_link_speed(self, host, device_name, level="current"):
        """
        This function gets the pci link speed
        """
        link_speed = "current_link_speed" if level == "current" else "max_link_speed"
        link_speed = self.get_pcie_register_type(host, device_name, link_speed)
        return link_speed

    def get_pcie_link_width(self, host, device_name, level="current"):
        """
        This function gets the pci link width
        """
        link_width = "current_link_width" if level == "current" else "max_link_width"
        link_width = self.get_pcie_register_type(host, device_name, link_width)
        return int(link_width) if link_width else None

    def get_device_pci_registers(self, host, device_name):
        """
        This function gets the pci registers for the device.
        """
        pci_regs = {}
        pci_regs["device_id"] = self.get_pcie_device_id(host, device_name)
        pci_regs["vendor_id"] = self.get_pcie_vendor_id(host, device_name)
        pci_regs["class_id"] = self.get_pcie_class(host, device_name)
        pci_regs["subsystem_vendor_id"] = self.get_pcie_subsystem_vendor(
            host, device_name
        )
        pci_regs["subsystem_device_id"] = self.get_pcie_subsystem_device(
            host, device_name
        )
        pci_regs["current_link_speed"] = self.get_pcie_link_speed(host, device_name)
        pci_regs["max_link_speed"] = self.get_pcie_link_speed(
            host, device_name, level="max"
        )
        pci_regs["current_link_width"] = self.get_pcie_link_width(host, device_name)
        pci_regs["max_link_width"] = self.get_pcie_link_width(
            host, device_name, level="max"
        )
        return pci_regs

    def get_pci_drive_slots(self, host):
        """
        This function will return the pci slots
        when the command is run, its seen as below
        15/  16/  17/  18/  2/
        Returns:
        --------
        slot_info: List
          list of all the slots
        """
        cmd = "ls -F /sys/bus/pci/slots"
        out = host.run(cmd)
        slot_info = out.replace("/", "").split()
        slot_info = list(map(int, slot_info))
        AutovalLog.log_info(" slot  is %s" % slot_info)
        return slot_info

    def get_slot_address(self, host):
        """
        This function will return the slot address mapped as per th slot

        Returns:
        --------
        slot_address: Dictionary
          slot number as key and pci address as value
        {15: '0000:b6:00', 16: '0000:b5:00', 17: '0000:b4:00'}
        """
        slot_info = self.get_pci_drive_slots(host)
        slot_address = {}
        for slot in slot_info:
            address = host.run(f"cat /sys/bus/pci/slots/{slot}/address")
            slot_address[slot] = address
        return slot_address

    def get_slot_power(self, host, slot_no) -> int:
        """
        This function will return the power status  of the pci slot

        Parameters:
        -----------
        slot_no: Integer
          the slot number

        Returns:
        power: Integer
          the power status
        """
        cmd = f"cat /sys/bus/pci/slots/{slot_no}/power"
        power = host.run(cmd)
        return int(power)

    def check_device_pcie_errors(
        self, host, devices, raise_on_fail=False, log_on_pass=False, warning=True
    ):
        cmd = 'cat /sys/bus/pci/devices/%s/aer* | grep -vP " 0|^0$"'
        for device in devices:
            errors = host.run(cmd % device, ignore_status=True)  # noqa
            AutovalUtils.validate_condition(
                not errors,
                f"{device} pcie errors: {str(errors)}",
                raise_on_fail=raise_on_fail,
                log_on_pass=log_on_pass,
                warning=warning,
                error_type=ErrorType.PCIE_ERR,
            )
