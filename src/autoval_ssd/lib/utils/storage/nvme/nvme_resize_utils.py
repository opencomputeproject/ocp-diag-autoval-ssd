#!/usr/bin/env python3

# pyre-unsafe
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

from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils

BYTES_PER_TB = 1000**4
CAPACITIES = [int(1.8 * BYTES_PER_TB), int(3.6 * BYTES_PER_TB)]


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
        round_to_usercapacity = {
            "_to_usercapacity": lambda x, max_bytes: CAPACITIES[
                NvmeResizeUtil.get_index_of_closest_capacity(max_bytes)
            ]
        }
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
    def validate_num_bytes_less_equal_max_bytes(num_bytes: int, max_bytes: int) -> None:
        """
        Validate that num_bytes is less than or equal to max_bytes
        """
        AutovalUtils.validate_less_equal(
            num_bytes,
            max_bytes,
            f"{num_bytes} requested, {max_bytes} available",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )

    @staticmethod
    def get_index_of_closest_capacity(max_bytes: int) -> int:
        """
        Utility method to get index of closest capacity to num_bytes
        """
        return min(range(len(CAPACITIES)), key=lambda i: abs(CAPACITIES[i] - max_bytes))

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
        **kwargs: Dict[Any, Any],
    ) -> None:
        """
            Resizes a namespace on an NVMe drive.
            This function derives the requested IDEMA capacity from the sweep parameter value,
            deletes any previous namespaces, creates and attaches a new namespace with the requested size,
            and validates the size of the new namespace. If the sweep parameter value is 0,
            the function restores the namespace to its state before the test using the original ncap and nsze values.
        Args:
            host (Host): The host object representing the DUT.
            nvme_id_ctrls (Dict[str, Any]): A dictionary containing the ID control attributes for the NVMe drive.
            sweep_param_unit (SweepParamUnitEnum): The unit of the sweep parameter value.
            sweep_param_key (SweepParamKeyEnum): The key of the sweep parameter value.
            device (str): The path to the NVMe drive.
            sweep_param_value (Union[int, float]): The value of the sweep parameter.
            kwargs (Dict[Any, Any]): Additional keyword arguments.
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
            if sweep_param_value == 0:
                nsze = nvme_id_ctrls[device]["orig_nsze"]
                ncap = nvme_id_ctrls[device]["orig_ncap"]
                AutovalLog.log_info(
                    f"Cleanup {device} using ns size before test {ncap} & {nsze}"
                )
        except KeyError as exc:
            raise TestError(
                f"{device}: cannot parse id-ctrl attr: {str(exc)}",
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )
        lbads_flag_value = NvmeResizeUtil.get_flag(
            host, device, "lbads", r"lbads:(\d+)"
        )
        flbas_flag = NvmeResizeUtil.get_flag(host, device, "flbas", r"lbaf  (\d+)")
        if lbads_flag_value == 12:
            block_size = 4096
        elif lbads_flag_value == 9:
            block_size = 512
        num_bytes = 0
        if sweep_param_unit:
            num_bytes = sweep_param_unit.to_bytes(sweep_param_value, tnvmcap)
        num_bytes = sweep_param_key.to_usercapacity(num_bytes, tnvmcap)
        NvmeResizeUtil.validate_num_bytes_less_equal_max_bytes(num_bytes, tnvmcap)
        if sweep_param_value != 0:
            lbads_flag_value = NvmeResizeUtil.get_flag(
                host, device, "lbads", r"lbads:(\d+)"
            )
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
            nsze = NvmeResizeUtil.get_idema_lba_counts(num_bytes, block_size)
            ncap = nsze
        nsid = 1
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
        AutovalUtils.validate_no_exception(
            NVMeUtils.create_ns,
            [host, device, nsze, ncap, block_size, flbas_flag],
            f"{device }: create-ns with nsze {nsze}",
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
        # Introducing sleep to avoid Kernel Panic on the DUT which is caused by
        # attach-ns.
        time.sleep(10)
        AutovalUtils.validate_no_exception(
            NVMeUtils.reset, [host, device], f"{device}: reset"
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
    def get_nvmcap(host, drives: List[str]) -> List[int]:
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
        drive_list: List[str],
        sweep_param_key: SweepParamKeyEnum,
        sweep_param_unit: SweepParamUnitEnum,
        sweep_param_value: Union[int, float],
        nvme_id_ctrl_filter: str = "True",
        cycle=1,
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
