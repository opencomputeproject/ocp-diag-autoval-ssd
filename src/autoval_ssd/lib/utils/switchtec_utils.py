# pyre-unsafe
import json
import re
import time

from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.file_actions import FileActions


class SwitchtecUtils:
    def power_cycle_slots(self, host, slot_address) -> None:
        # Get all the SSD's slot address
        for slot in slot_address:
            slots = self._get_pci_slots(host, slot)
            # Slot Power OFF command
            slot_cmd = "echo 0 > /sys/bus/pci/slots/%s/power" % slots
            try:
                host.run(slot_cmd)
            except Exception:
                pass
            # Sleep between each slot power cycle
            time.sleep(1)

        # Once all the slots are Powered OFF, wait for sometime
        AutovalLog.log_info("Powered OFF all Slots")
        time.sleep(60)

        for slot in slot_address:
            slots = self._get_pci_slots(host, slot)
            # Slot Power ON command
            slot_cmd = "echo 1 > /sys/bus/pci/slots/%s/power" % slots
            try:
                host.run(slot_cmd)
            except Exception:
                pass
            # Sleep between each slot power cycle
            time.sleep(1)

        # Once all the slots are Powered ON, wait for enumeration
        AutovalLog.log_info("Powered ON all Slots")
        time.sleep(60)

    def _get_pci_slots(self, host, slot):
        sys_add = "/sys/bus/pci/slots/*/address"
        cmd = r"grep %s %s | sed 's/\// /g' | awk '{print $5}'" % (slot, sys_add)
        slots = host.run(cmd)
        if slots:
            return slots
        else:
            raise TestError("Getting Slots Failed for - %s" % (slot))

    def get_switchtec_event_counter(self, host, device):
        """
        Get an event counters in JSON from a Switchtec Device.
        Format: {stack_number: {event_key: event_value}}
        """
        cmd = "switchtec evcntr /dev/%s" % device
        event_counter = {}
        out = host.run(cmd)
        for line in out.splitlines():
            m = re.search(r"Stack\s+(\d+):", line)
            if m:
                stack = int(m.group(1))
            else:
                try:
                    line_list = line.split()
                    value = int(line_list[-1])
                    key = line_list[-2]
                    _dict = {stack: {key: value}}
                    event_counter.update(_dict)
                    if value != 0:
                        AutovalLog.log_info("WARNING: Stack %s" % str(_dict))
                except Exception:
                    pass
        return event_counter

    def get_switchtec_devices(self, host):
        cmd = "switchtec list"
        out = host.run(cmd, ignore_status=True)
        device_list = re.findall(r"(switchtec\d+)\s+", out)
        return device_list

    def check_if_switchtec_installed(self, host) -> None:
        cmd = "rpm -qa | grep switchtec | tr '\n' ' '"
        out = host.run_get_result(cmd, ignore_status=True)  # noqa
        if out.return_code != 0:
            self.install_switchtec(host)

    def install_switchtec(self, host) -> None:
        cmd = "dnf install switchtec"
        host.run(cmd, ignore_status=True)  # noqa

    def collect_switchtec_throughput(self, host, file_name: str, switchtech) -> None:
        out = host.run(f"switchtec bw {switchtech}")
        return_json = {switchtech: self.convert_switchtech_output_to_json(out)}
        with FileActions.file_open(file_name, "a") as f:
            #  `Union[IO[bytes], IO[str]]`.
            json.dump(return_json, f, indent=4, sort_keys=False)

    def convert_switchtech_output_to_json(self, out):
        lines = out.splitlines()
        line_num = 0
        key_dict = {}
        while line_num < len(lines) and "Partition" in lines[line_num]:
            key, _ = lines[line_num].split(":")
            line_num += 1
            level1 = {}
            while line_num < len(lines) and "Logical" in lines[line_num]:
                key1, _ = lines[line_num].split(":")
                line_num += 1
                level2 = {}
                while line_num < len(lines) and (
                    "Out" in lines[line_num] or "In" in lines[line_num]
                ):
                    key2, value = lines[line_num].split(":")
                    level2.update({key2.lstrip(): value.lstrip()})
                    line_num += 1
                level1.update({key1.lstrip(): level2})
            key_dict.update({key: level1})
        return key_dict

