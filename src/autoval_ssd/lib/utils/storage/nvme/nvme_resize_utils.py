#!/usr/bin/env python3

# pyre-unsafe
import copy
import math
import re
import time
from enum import Enum

from typing import Any, Dict, List, Union

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_exceptions import TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_thread import AutovalThread  # noqa
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval_ssd.lib.utils.storage.drive import Drive

from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils

BYTES_PER_TB = 1000**4
REPORTED_CAPACITIES = [TB_Capacity * BYTES_PER_TB for TB_Capacity in range(1, 25)]


class NvmeResizeUtil:
    """
    Class of NVMe Resizing the drives with namespaces with a variety of sizes
    """

    DEFAULT_OP_PERCENT = 0

    class SweepParamKeyEnum(Enum):
        """
        Allowed values for sweep_param_key input in test_control json.
        This param allows user to specify amount of overprovisioning, or
        amount of user capacity
        """

        usercapacity = {"_to_usercapacity": lambda x, max_bytes: x}
        overprovisioning = {"_to_usercapacity": lambda x, max_bytes: max_bytes - x}

        def to_usercapacity(self, num_bytes: int, max_bytes: int) -> int:
            """
            Utility method to convert sweep_param_key value to usercapacity
            """
            return int(self.value["_to_usercapacity"](num_bytes, max_bytes))

    class SweepParamUnitEnum(Enum):
        """
        Allowed values for sweep_param_unit input in test_control json.
        This param allows user to specify size in bytes, percentage etc
        """

        percent = {"_to_bytes": lambda x, max_bytes: x * max_bytes / 100}
        num_bytes = {"_to_bytes": lambda x, max_bytes: x}
        num_TB = {"_to_bytes": lambda x, max_bytes: x * BYTES_PER_TB}

        def to_bytes(
            self,
            sweep_param_value: Union[int, float],
            max_bytes: int,
        ) -> int:
            """
            Utility method to convert sweep_param_key to number of bytes
            """
            num_bytes = self.value["_to_bytes"](
                sweep_param_value,
                max_bytes,
            )
            return int(num_bytes)

    @staticmethod
    def validate_num_bytes_less_equal_max_bytes(num_bytes: int, max_bytes: int) -> int:
        """
        Validate that num_bytes is less than or equal to max_bytes. If num_bytes exceeds
        max_bytes, log a message and return max_bytes instead.
        Args:
            num_bytes : The number of bytes requested for the operation.
            max_bytes : The maximum number of bytes available for the operation.
                             This value acts as an upper limit for num_bytes.
        Returns:
               Either num_bytes if it is less than or equal to max_bytes, or max_bytes
               if num_bytes exceeds max_bytes.
        """
        AutovalUtils.validate_less_equal(
            num_bytes,
            max_bytes,
            f"{num_bytes} requested, {max_bytes} available",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
            raise_on_fail=False,
            warning=True,
        )
        if num_bytes > max_bytes:
            AutovalLog.log_info(
                f"Resize proceeding with max bytes available: {max_bytes}"
            )
            return max_bytes
        return num_bytes

    @staticmethod
    def get_reported_capacity(max_bytes: int) -> tuple:
        """
        Utility method to find the closest reported capacity value to the given maximum number of bytes.

        Args:
            max_bytes: The maximum number of bytes available for the operation.
                             This value is used to determine the closest reported capacity value.

        Returns:
            A tuple containing two values: Reported capacity and TB capacity index
        """
        TB_Capacity = math.ceil(max_bytes / BYTES_PER_TB)
        return REPORTED_CAPACITIES[TB_Capacity - 1], TB_Capacity

    @staticmethod
    def get_lba_counts(
        num_bytes: int,
        block_size: int,
        sweep_param_value: Union[float, int],
    ) -> int:
        """
        This function converts the requested number of bytes to LBA counts.
        Case 1:
        IDEMA Calulation used for resize during test.
            The IDEMA calucation used is given in the IDEMA Document LBA1-03.
            Ref: IDEMA Document LBA1-03.
        Case 2:
        BASIC LBA calcuation is used for resize during cleanup
            In this case, sweep_param_value = DEFAULT_OP_PERCENT
            The basic LBA calculation is num_bytes / block size
            Ref: IDEMA Document LBA1-03.
        Args:
            num_bytes: The requested number of bytes.
            block_size: The size of each block in bytes.
                              Currently only supports 4096 and 512 block sizes.
        Returns:
            The calculated IDEMA LBA counts.
        """
        if sweep_param_value != NvmeResizeUtil.DEFAULT_OP_PERCENT:
            num_GB = int(num_bytes / (1000**3))
            if block_size == 4096:
                return 12212046 + (244188 * (num_GB - 50))
            return 97696368 + (1953504 * (num_GB - 50))
        return int(num_bytes / block_size)

    @staticmethod
    def get_lbaf_details(host: Host, device: str, nsid: int = 1) -> Dict[str, int]:
        """
        Get the lbaf, ms, and lbads values either for a given lbaf value or the one marked as '(in use)'.
        Args:
            host: The host on which to run the command.
            device: The device to query.
            nsid: The namespace ID. Defaults to 1.
        Returns:
            A dictionary containing 'lbaf', 'ms', and 'lbads' values.
        Raises:
            TestError: If an 'in use' lbaf cannot be found for the specified drive and namespace.
        """
        cmd = f"nvme id-ns -n {nsid} /dev/{device} | grep 'in use'"
        out = host.run(cmd)
        # Pattern to match lbaf lines
        lbaf_pattern = re.compile(r"lbaf\s+(\d+)\s*:\s*ms:(\d+)\s*lbads:(\d+)")

        match = lbaf_pattern.search(out)
        if match:
            return {
                "lbaf": int(match.group(1)),
                "ms": int(match.group(2)),
                "lbads": int(match.group(3)),
            }
        raise TestError(
            f"Failed to find an 'in use' lbaf for drive {device}n{nsid}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )

    @staticmethod
    def get_nsid_list(host: Host, device: str) -> List[int]:
        """
        Get a list of nsid values from the device.

        Args:
            host: The host on which to run the command.
            device: The device to query.

        Returns:
            A list of nsid values.
        """
        cmd = f"nvme list-ns /dev/{device}"
        out = host.run(cmd)

        # Pattern to match nsid values
        nsid_pattern = re.compile(r"\[\s*\d+\]:0x(\d+)")

        nsid_list = []
        for line in out.splitlines():
            match = nsid_pattern.search(line)
            if match:
                nsid = int(match.group(1), 16)  # Convert hex string to integer
                nsid_list.append(nsid)
        nsid_list.sort()
        return nsid_list

    @staticmethod
    def get_idema_lba_counts(num_bytes, block_size: int) -> int:
        """
        Utility method to convert requested number of bytes to IDEMA LBA counts
        Ref: IDEMA Document LBA1-03
        """
        num_GB = num_bytes / (1000**3)
        if block_size == 4096:
            return int(12212046 + (244188 * (num_GB - 50)))
        return int(97696368 + (1953504 * (num_GB - 50)))

    @staticmethod
    def get_flag(host, device: str, flag_name: str, flag_regex: str) -> int:
        """
        Determine lbads by reading from device currently in use lbaf
        Determine flbas by reading from device currently in use lbaf
        @return lbadss_flag
        @return flbas_flag
        """
        cmd = "nvme id-ns -n 1 /dev/%s | grep 'in use'" % device
        out = host.run(cmd)
        match = re.search(flag_regex, out)
        if match:
            return int(match.group(1))
        raise TestError(
            f"Failed to find {flag_name} flag for drive in {device}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )

    @staticmethod
    def ns_resize(
        host: Host,
        nvme_id_ctrls: Dict[str, Any],
        sweep_param_unit: SweepParamUnitEnum,
        sweep_param_key: SweepParamKeyEnum,
        device: str,
        sweep_param_value: Union[int, float],
        **kwargs,
    ) -> None:
        """
            Resizes a namespace on an NVMe drive.
            This function derives the requested IDEMA capacity from the sweep parameter value,
            deletes any previous namespaces, creates and attaches a new namespace with the requested size,
            and validates the size of the new namespace. If the sweep parameter value is 0,
            the function restores the namespace to its state before the test using the original ncap and nsze values.
        Args:
            host: The host object representing the DUT.
            nvme_id_ctrls: A dictionary containing the ID control attributes for the NVMe drive.
            sweep_param_unit: The unit of the sweep parameter value.
            sweep_param_key: The key of the sweep parameter value.
            device: The path to the NVMe drive.
            sweep_param_value: The value of the sweep parameter.
            kwargs : Additional (optional) keyword arguments.
            The following keyword arguments are used for DIX NS RESIZE test cases
                combination: A list of two lbaf values to create namespaces with.
                use_existing_ns: A boolean indicating whether to reuse existing namespace.
                lbaf_to_flbas_map: A dict mapping the LBAF to its value using during namespace
                    creation eg. {512:1, 4096:0, 4096+64:2}
        Returns:
            None
        """

        if sweep_param_value:
            AutovalLog.log_info(
                f"{device}: Running resize with param {sweep_param_value}"
            )
        cntlid = None
        tnvmcap = None
        nsze = None
        ncap = None
        block_size = 0
        try:
            cntlid = nvme_id_ctrls[device]["cntlid"]
            tnvmcap = nvme_id_ctrls[device]["tnvmcap"]
        except KeyError as exc:
            raise TestError(
                f"{device}: cannot parse id-ctrl attr: {str(exc)}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )
        num_bytes = 0
        capacity = tnvmcap
        if sweep_param_value != NvmeResizeUtil.DEFAULT_OP_PERCENT:
            capacity, TB_capacity = NvmeResizeUtil.get_reported_capacity(tnvmcap)
            AutovalLog.log_info(
                f"{device}: resizing with respect to reported capacity: {TB_capacity}TB"
            )
        if sweep_param_unit:
            num_bytes = sweep_param_unit.to_bytes(sweep_param_value, capacity)
        num_bytes = sweep_param_key.to_usercapacity(num_bytes, capacity)
        num_bytes = NvmeResizeUtil.validate_num_bytes_less_equal_max_bytes(
            num_bytes, tnvmcap
        )

        if sweep_param_value == NvmeResizeUtil.DEFAULT_OP_PERCENT:
            flbas_flag = nvme_id_ctrls[device]["original_lbaf_details"]["lbaf"]
            lbads_flag_value = nvme_id_ctrls[device]["original_lbaf_details"]["lbads"]
        else:
            # this needs to be called before deleting the namespace
            # otherwise when we look for the (in-use) lbaf we will always get 0
            current_lbaf_details = NvmeResizeUtil.get_lbaf_details(host, device)

            # Adding a delay to ensure that current LBAF details are properly set
            # before accessing 'flbas_flag' and 'lbads_flag_value'
            time.sleep(10)
            flbas_flag = current_lbaf_details["lbaf"]
            lbads_flag_value = current_lbaf_details["lbads"]
        if lbads_flag_value == 12:
            block_size = 4096
        elif lbads_flag_value == 9:
            block_size = 512
        else:
            raise TestError(
                f"lbads flag received incorrect value: {lbads_flag_value}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )
        nsze = NvmeResizeUtil.get_lba_counts(num_bytes, block_size, sweep_param_value)
        ncap = nsze

        device_combination: List[str] = copy.copy(kwargs.get("combination", []))
        use_existing_ns: bool = kwargs.get("use_existing_ns", False)
        lbaf_to_flbas_map: Dict[str, int] = kwargs.get("lbaf_to_flbas_map", {})
        AutovalLog.log_info(f"use_existing_ns: {use_existing_ns}")

        nsid_values = NvmeResizeUtil.get_nsid_list(host, device)
        if use_existing_ns and device_combination:
            ns_ids = nsid_values
            for nsid in ns_ids:
                ns_lbaf_details = NvmeResizeUtil.get_lbaf_details(
                    host, device, nsid=nsid
                )
                lbaf = str(2 ** (ns_lbaf_details["lbads"]))
                ms = str(ns_lbaf_details["ms"])
                if ms != "0":
                    lbaf = f"{lbaf}+{ms}"
                AutovalLog.log_info(
                    f"{device}n{nsid}, lbaf:{lbaf} combination:{device_combination}"
                )
                if lbaf in device_combination:
                    device_combination.remove(lbaf)
                    nsid_values.remove(nsid)
                    AutovalLog.log_info(f"Using existing namespace: {device}n{nsid}")

        if nsid_values:
            NvmeResizeUtil.detach_delete_ns(host, device, cntlid, nsid_values)

        nsid = nsid_values[0] if nsid_values else 1
        if device_combination:
            for lbaf in device_combination:
                block_size = int(lbaf.split("+")[0])
                flbas_flag = lbaf_to_flbas_map[lbaf]
                dix_size = NvmeResizeUtil.get_lba_counts(
                    num_bytes, block_size, sweep_param_value
                )
                NvmeResizeUtil.create_attach_ns(
                    host,
                    device,
                    nsize=dix_size,
                    ncap=dix_size,
                    block_size=block_size,
                    flbas_flag=flbas_flag,
                    nsid=nsid,
                    cntlid=cntlid,
                )
                nsid += 1

        else:
            NvmeResizeUtil.create_attach_ns(
                host,
                device,
                nsize=nsze,
                ncap=ncap,
                block_size=block_size,
                flbas_flag=flbas_flag,
                nsid=nsid,
                cntlid=cntlid,
            )
            nvme_id_ns = AutovalUtils.validate_no_exception(
                NVMeUtils.get_id_ns,
                [host, device, nsid],
                f"{device}: identify ns",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )
            AutovalUtils.validate_equal(
                nsze,
                nvme_id_ns.get("nsze", -1),
                f"{device}: validating actual nsze",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )

    @staticmethod
    def get_nvmcap(host, drives: list[str]) -> list[int]:
        """
        get NVME capacity

        parameter:
        drive(list): list of drives

        Return:
        list: all drive capacity
        """
        nvmecap = []
        nvme_supported_drives = NVMeUtils.get_namespace_support_drive_list(host, drives)
        nvme_char2block_map = NvmeResizeUtil.get_nvme_with_namespace(
            host, nvme_supported_drives
        )
        for device in nvme_char2block_map:
            id_ns = NVMeUtils.get_id_ns(host, device, nsid=1)
            nvmecap.append(id_ns["nvmcap"])
        return nvmecap

    @staticmethod
    def get_nvme_ctrls(host, drive_list, nvme_id_ctrl_filter="True"):
        """
        Placehold dictionary to store nvme device to id-ctrl mapping
        Getting the drives only which support Namespace management
        Map test_drives to their corresponding device
        Filter out drives based on nvme_id_ctrl_filter eval str
        Display nvme list before and after resize method
        """
        nvme_id_ctrls = {}
        ns_support_drive_list = NVMeUtils.get_namespace_support_drive_list(
            host, drive_list
        )
        AutovalUtils.validate_non_empty_list(
            ns_support_drive_list,
            "Drives supported NS management",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        nvme_char2block_map = NvmeResizeUtil.get_nvme_with_namespace(
            host, ns_support_drive_list
        )
        for device in nvme_char2block_map.keys():
            nvme_id_ctrl = NVMeUtils.get_id_ctrl(host, device)
            id_ns = NVMeUtils.get_id_ns(host, device, nsid=1)
            _locals = {"nvme_id_ctrl": nvme_id_ctrl}
            _globals = {}
            try:
                if eval(nvme_id_ctrl_filter, _locals, _globals):
                    nvme_id_ctrls[device] = nvme_id_ctrl
                    nvme_id_ctrls[device]["original_lbaf_details"] = (
                        NvmeResizeUtil.get_lbaf_details(host, device, nsid=1)
                    )
                    nvme_id_ctrls[device]["orig_ncap"] = id_ns["ncap"]
                    nvme_id_ctrls[device]["orig_nsze"] = id_ns["nsze"]
                    AutovalLog.log_info(
                        "char name {} orig_ncap {} orig_nsze {}".format(
                            device, id_ns["ncap"], id_ns["nsze"]
                        )
                    )
                else:
                    AutovalLog.log_info(f"{device}: filtered out")
            except (KeyError, NameError, SyntaxError, ZeroDivisionError) as e:
                raise TestError(
                    f"Can't eval {nvme_id_ctrl_filter}: {str(e)}",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.NVME_ERR,
                )
        return nvme_id_ctrls

    @staticmethod
    def perform_resize(
        host,
        drive_list: list[str],
        sweep_param_key: SweepParamKeyEnum,
        sweep_param_unit: SweepParamUnitEnum,
        sweep_param_value: Union[int, float],
        nvme_id_ctrl_filter: str = "True",
        cycle=1,
        **kwargs,
    ) -> None:
        """
        This function performs a resize operation on the specified NVMe drives.

        It first gets a list of NVMe controllers and their corresponding devices,
        then filters out any drives that do not support Namespace management.

        The function then resizes each drive in the filtered list using the
        specified sweep parameters. If the `sweep_param_value` parameter is set,
        it will be used as the value for the sweep parameter. Otherwise, the
        'sweep_param_key' parameter will be used as the key for the sweep parameter.

        Args:
            host (Host): The Host object representing the machine where the resize
                operation will be performed.
            drive_list List[str]: A list of NVMe drives to be resized.
            sweep_param_key SweepParamKeyEnum: The key for the sweep parameter.
            sweep_param_unit SweepParamUnitEnum: The unit for the sweep parameter.
            sweep_param_value Union[int, float]: The value for the sweep parameter.
            nvme_id_ctrl_filter:
                Evaluatable string that can be used to add an inclusion
                criterion on nvme_drives for that particular control file, based
                on nvme id-ctrl attribute checks. The condition should be expressed
                assuming id-ctrl json is present in var nvme_id_ctrl.
                e.g. to only include drives > 500G (536870912000 bytes) in tnvmcap,
                we would have the following in test control json
                {
                "nvme_id_ctrl_filter": "nvme_id_ctrl[\"tnvmcap\"] >= 536870912000",
                ...}
                Defaults to "True" to effectively skip using the nvme_id_ctrl_filter
            cycle (int, optional): The number of cycles to perform the resize
                operation. Defaults to 1.

        Returns:
            None
        """
        nvme_id_ctrls = NvmeResizeUtil.get_nvme_ctrls(
            host, drive_list, nvme_id_ctrl_filter=nvme_id_ctrl_filter
        )
        nvme_ctrls = [*nvme_id_ctrls]  # Device List
        AutovalUtils.validate_non_empty_list(
            nvme_ctrls,
            "Usable SSD drives",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        for _cycle in range(1, cycle + 1):
            AutovalLog.log_info(f"Starting cycle {_cycle}")
            if sweep_param_value:
                AutovalLog.log_info(
                    f"Before resizing with sweep param value {sweep_param_value}"
                )
            else:
                AutovalLog.log_info(
                    f"Before resizing with sweep param key {sweep_param_key}"
                )
            AutovalLog.log_info("NVME LIST\n" + host.run("nvme list"))
            ns_validate_queue = []
            for device in nvme_ctrls:
                ns_validate_queue.append(
                    AutovalThread.start_autoval_thread(
                        NvmeResizeUtil.ns_resize,
                        host,
                        nvme_id_ctrls,
                        sweep_param_unit,
                        sweep_param_key,
                        device,
                        sweep_param_value,
                        **kwargs,
                    )
                )
            if len(ns_validate_queue):
                AutovalThread.wait_for_autoval_thread(ns_validate_queue)
            if sweep_param_value:
                AutovalLog.log_info(
                    f"After resizing with sweep param value {sweep_param_value}"
                )
            else:
                AutovalLog.log_info(
                    f"After resizing with sweep param key {sweep_param_key}"
                )
            AutovalLog.log_info("NVME LIST\n" + host.run("nvme list"))

    @staticmethod
    def get_nvme_with_namespace(host, test_drives):
        """
        Map test_drives to corresponding device.
        """
        nvme_drives = {}
        for drive_obj in test_drives:
            nvme_drive = NVMeUtils.get_nvme_ns_map(
                host, drive_obj.block_name, drive_obj.serial_number
            )
            nvme_drives.update(nvme_drive)
        return nvme_drives

    @staticmethod
    def detach_delete_ns(
        host: Host, device: str, cntlid: int, nsid_values: List[int]
    ) -> None:
        """
        This function iterates over a list of namespace identifiers (nsid_values) and performs
        the detachment and deletion of each namespace from the specified NVMe device.

        Args:
            host: The host object where the operations are performed.
            device: The NVMe device identifier from which namespaces will be detached and deleted.
            cntlid: The controller identifier associated with the NVMe device.
            nsid_values: A list of namespace identifiers to be detached and deleted.
        """

        for nsid in nsid_values:
            AutovalUtils.validate_no_exception(
                NVMeUtils.detach_ns,
                [host, device, nsid, cntlid],
                f"{device}: detach-ns to {cntlid}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )
            AutovalUtils.validate_no_exception(
                NVMeUtils.delete_ns,
                [host, device, nsid],
                f"{device}: delete-ns",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )
            device_was_deleted = device + f"n{nsid}" not in host.run("nvme list")
            AutovalUtils.validate_condition(
                device_was_deleted,
                f"{device}: confirm namespace deletion",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )

    @staticmethod
    def create_attach_ns(
        host: Host,
        device: str,
        nsize: int,
        ncap: int,
        flbas_flag: int,
        nsid: int,
        cntlid: int,
        block_size: int = 4096,
    ) -> None:
        """
        This function first creates a namespace with the given parameters and then attaches it to the specified controller.

        Args:
            host: The host object where the operations are performed.
            device: The NVMe device identifier to which the namespace will be attached.
            nsize: The size of the namespace to be created.
            ncap: The capacity of the namespace to be created.
            block_size: The block size for the namespace.
            flbas_flag: The formatted LBA size flag for the namespace.
            nsid: The namespace identifier to be used.
            cntlid: The controller identifier to which the namespace will be attached.
        """
        AutovalUtils.validate_no_exception(
            NVMeUtils.create_ns,
            [host, device, nsize, ncap, block_size, flbas_flag],
            f"{device }: create-ns with nsze {nsize}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        AutovalUtils.validate_no_exception(
            NVMeUtils.attach_ns,
            [host, device, nsid, cntlid],
            f"{device}: attach-ns to {cntlid}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        AutovalUtils.validate_no_exception(
            NVMeUtils.reset, [host, device], f"{device}: reset"
        )

    @staticmethod
    def get_lbaf_to_flbas_map(host: Host, drive: str) -> Dict[str, int]:
        """
        Extracts the supported LBA formats and their corresponding indices for a given drive.

        Args:
            host: The host on which to run the command.
            drive: The drive to check for supported LBA formats.

        Returns:
            A dictionary mapping LBA format strings to their corresponding indices.
        """
        lbaf_to_flbas_map = {}
        patterns = {
            "512": r"(\d)\s+:\s+Metadata Size:\s+0\s+bytes\s+-\s+Data Size:\s+512\s+bytes",
            "4096": r"(\d)\s+:\s+Metadata Size:\s+0\s+bytes\s+-\s+Data Size:\s+4096\s+bytes",
            "4096+64": r"(\d)\s+:\s+Metadata Size:\s+64\s+bytes\s+-\s+Data Size:\s+4096\s+bytes",
        }

        cmd = f"nvme id-ns -H /dev/{drive} | grep 'LBA Format'"
        out = host.run(cmd)

        for lbaf, pattern in patterns.items():
            result = re.search(pattern, out)
            if result:
                lbaf_to_flbas_map[lbaf] = int(result.group(1))
        return lbaf_to_flbas_map

    @staticmethod
    def validate_drives_support_dix_resize_lba_formats(
        host: Host, drive_list: List[Drive]
    ) -> Dict[str, int]:
        """
        Checks the supported LBA formats for each drive in the provided output.
        This function runs a command to identify the namespace of each drive and then checks the output
        for specific patterns that indicate the supported LBA formats.
        Args:
            host: The host on which to run the command.
            drive_list: A list of drives to check for supported LBA formats.
        Returns:
            lbaf_to_flbas_map: A dictionary containing the supported LBA formats for each drive and their
            corresponding values to be used during resize
        """
        required_formats = {"512", "4096", "4096+64"}
        lbaf_to_flbas_map = {}

        for drive in drive_list:
            lbaf_to_flbas_map = NvmeResizeUtil.get_lbaf_to_flbas_map(
                host, drive.block_name
            )

            AutovalUtils.validate_condition(
                required_formats.issubset(lbaf_to_flbas_map.keys()),
                f"{drive.block_name} supports all DIX LBA Formats",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.DRIVE_ERR,
                log_on_pass=True,
            )

        return lbaf_to_flbas_map
