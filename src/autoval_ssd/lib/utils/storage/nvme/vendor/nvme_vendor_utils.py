# pyre-unsafe
import numbers
import os
import re
from typing import Dict

from autoval_ssd.lib.utils.storage.nvme.nvme_drive import NVMeDrive
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils

from autoval.lib.utils.generic_utils import GenericUtils
from autoval.lib.utils.result_handler import ResultHandler


class NvmeVendorUtils:
    @staticmethod
    def get_vendor_all_config(
        drive_obj: NVMeDrive, config_file: str, config_dir: str, validate_config: Dict
    ) -> Dict:
        """
        Loads vendor config from NVME vendor config file and return the valid config for smart validation

        Args:
        -----
        drive_obj: drive object
        config_file: vendor config file name
        config_dir: vendor config file path
        validate_config: valid generic config for smart validation of the drive

        Returns:
        -------
        valid_vendor_config: valid vendor config
        Combined generic and vendor specific (if available) config for smart validation
        """
        if not drive_obj.vid:
            return validate_config
        vendor_file = config_file.split(".")[-2] + f"_vid_{drive_obj.vid}.json"
        relative_cfg_file_path = os.path.join(config_dir, vendor_file)
        relative_cfg_file_path = "cfg/" + relative_cfg_file_path
        vendor_config = GenericUtils.read_resource_cfg(file_path=relative_cfg_file_path)
        vendor_config = drive_obj._filter_vendor_config(vendor_config)
        vendor_config = drive_obj._flatten_validate_config_dict(vendor_config)
        valid_vendor_config = {
            key: vendor_config[key]
            for key in drive_obj.smart_log_keys
            if key in vendor_config
        }
        validate_config.update(valid_vendor_config)
        return validate_config

    @staticmethod
    def get_vendor_write_amplification(drive_obj: NVMeDrive, smart_before: Dict[str, Dict], smart_after: Dict[str, Dict]) -> bool:
        """
        Method to calculates the write amplification factor (WAF) for a given drive.
        HOST and NAND write bytes are captured before and after test
        to determine total logical and physical write bytes.
        Args:
            smart_before (dict): Dictionary containing SMART data before a test.
            smart_after (dict): Dictionary containing SMART data after a test.
        Returns:
            bool: True if the calculation was successful, False otherwise.
        """
        host_write_before = smart_before["smart-log"]["data_units_written"]
        host_write_after = smart_after["smart-log"]["data_units_written"]
        host_delta = host_write_after - host_write_before
        if (
            "vs-smart-add-log" not in smart_before
            or "vs-smart-add-log" not in smart_after
        ):
            AutovalLog.log_info(
                "Skipping write amplification calculation for non fb smart drive: %s"
                % drive_obj.model
            )
            return False
        write_amplification = {}
        nand_write_formula = drive_obj.get_nand_write_param()
        nand_write_before = smart_before["vs-smart-add-log"][nand_write_formula["field"]]
        nand_write_after = smart_after["vs-smart-add-log"][nand_write_formula["field"]]
        # Few Vendor specific smart data output contains data in hex
        if not isinstance(
            nand_write_before, numbers.Real
        ) and nand_write_before.startswith("0x"):
            try:
                nand_write_before = float(int(nand_write_before, 16) * 512)
                nand_write_after = float(int(nand_write_after, 16) * 512)
            except Exception:
                pass
        # Few Vendor specific smart data output contains GiB string in it
        if not isinstance(nand_write_before, numbers.Real):
            match = re.search(r"[(\d\.\d)]+", nand_write_before)
            contain_GiB = re.search(r"GiB", nand_write_before)
            if match:
                nand_write_before = float(match.group(0))
            if contain_GiB:
                nand_write_before = nand_write_before * 1024**3
            match = re.search(r"[(\d\.\d)]+", nand_write_after)
            contain_GiB = re.search(r"GiB", nand_write_after)
            if match:
                nand_write_after = float(match.group(0))
            if contain_GiB:
                nand_write_after = nand_write_after * 1024**3
        # converting str instance of nand data to float
        nand_write_before = drive_obj.convert_nand_write(nand_write_before)
        nand_write_after = drive_obj.convert_nand_write(nand_write_after)
        nand_delta = nand_write_after - nand_write_before
        # Calculate lifetime Write amp
        write_amplification["lifetime_write_amplification"] = 0
        if host_write_after and nand_write_after:
            waf, error = drive_obj.calculate_waf(
                host_write_after, nand_write_after, nand_write_formula
            )
            if waf:
                AutovalLog.log_info(
                    "Lifetime WAF for drive %s is %s" % (drive_obj.block_name, waf)
                )
                write_amplification["lifetime_write_amplification"] = waf
                waf = {
                    "name": drive_obj.block_name,
                    "write_amplification": waf,
                    "serial_number": drive_obj.serial_number,
                    "model": drive_obj.manufacturer,
                }
                result_handler = ResultHandler()
                result_handler.update_test_results({drive_obj.block_name: waf})
            if error:
                AutovalLog.log_info(
                    "Cannot calculate WAF for drive %s due to %s"
                    % (drive_obj.block_name, error)
                )
        AutovalUtils.validate_range(
            write_amplification["lifetime_write_amplification"],
            1.0,
            20.0,
            "WAF expected range",
            warning=True,
        )

        # Calculate Write amp for the currently running test
        write_amplification["test_write_amplification"] = 0
        waf, error = drive_obj.calculate_waf(host_delta, nand_delta, nand_write_formula)
        AutovalLog.log_info(
            "WAF during this test for drive %s: %s" % (drive_obj.block_name, waf)
        )
        write_amplification["test_write_amplification"] = waf
        if error:
            AutovalLog.log_info(
                "Cannot calculate WAF for drive %s due to %s"
                % (drive_obj.block_name, error)
            )
        AutovalLog.log_info("Drive %s: %s" % (drive_obj.block_name, write_amplification))
        return True
