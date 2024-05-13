#!/usr/bin/env python3

# pyre-unsafe
"""
Test validates the performance of the HDD/SSD
during a fio operation by disabling and enabling the
internal volatile write cache and then comparing the results.
"""
from pprint import pformat

from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase


class DriveCacheCheck(StorageTestBase):
    """
    This script is used to validate the performace of the SSD/HDD drive during a
    fio operation by disabling and enabling the internal volatile write cache
    by running the relavent commands on the drive.
    """

    def __init__(self, *args, **kwargs) -> None:
        """
        Initializes the drive volatile write cache enable disable test.
        This method initializes the basic configuration for logging
        information, load and store the input details gathered from
        input/control(json) file.
        """
        super().__init__(*args, **kwargs)
        self.write_fio = self.test_control["write_fio"]
        self.read_fio = self.test_control["read_fio"]
        self.save_state = self.test_control.get("save_state")
        self.power_trigger = self.test_control.get("power_trigger", True)
        self.power_cycle = self.test_control.get("power_cycle", "warm")
        self.supported_drive_list = []
        self.drive_state = {}
        self.final_result_dict = {
            "cache_disable": {"read": {}, "write": {}},
            "cache_enable": {"read": {}, "write": {}},
        }

    def setup(self, *args, **kwargs) -> None:
        super().setup(*args, **kwargs)
        # Get the drive which support the write cache.
        self.supported_drive_list = self.write_cache_supported_drive_list()
        self.validate_non_empty_list(
            self.supported_drive_list, "Drives supporting cache enable-disable"
        )
        # Setup fio
        self.test_control["drives"] = self.supported_drive_list
        if self.boot_drive:
            self.test_control["boot_drive"] = self.boot_drive
        fio = FioRunner(self.host, self.test_control)
        self.validate_no_exception(fio.test_setup, [], "Fio setup()")

    def execute(self) -> None:
        """
        Test Flow:
        1.Get the write cache state of all the drives.
        2.Enable write cache on all the drives.
        3.Get the drive list which support write cache list.
        4.Call the function with cache_fio_execution with volatile write cache
          as disabled.
        5.Call the function with cache_fio_execution with volatile write cache
          as enabled.
        6.Collect the results and display it.
        7.In the cleanup, again set the write cache state to its original state.
        """
        # Get the state of write cache of the drives.
        self.get_drive_cache_state()
        # Before start of test enable the write cache on the supported drives.
        self.log_info("Enabling cache")
        self.volatile_write_cache_with_fio_execution(write_cache_mode="enable")
        self.log_info("Disabling cache")
        self.volatile_write_cache_with_fio_execution(write_cache_mode="disable")
        self.log_debug("FIO metrics before and after cache enabled/disabled")
        self.log_debug(pformat(self.final_result_dict))
        self.check_errors()
        self.compare_results()

    def get_drive_cache_state(self) -> None:
        """
        This function will get the drives with write cache
        """
        for drive in self.test_drives:
            result_value = drive.get_write_cache()
            self.drive_state[drive] = result_value

    def write_cache_supported_drive_list(self):
        """
        This function will get all the drives which have
        write cache supported.
        @return: list
        """
        for drive in self.test_drives:
            result_value = drive.get_write_cache()
            if result_value is not None:
                self.supported_drive_list.append(drive)
        return self.supported_drive_list

    def volatile_write_cache_with_fio_execution(
        self, write_cache_mode: str = "enable"
    ) -> None:
        """
        1.This function will first set the volatile write cache based
          on the write cache mode.
        2.Next it will set the power trigger to true.
        3.Fio write will be started and based on power trigger it will go for a reboot.
        4.Once the DUT is up, the volatile write cache setting is done again based
          on the write cache mode.
        5.Now do a fio verify and store the results.

        @param: supported drive list : list
        @param: write_cache_mode : String
        """
        self.enable_disable_write_cache(write_cache_mode=write_cache_mode)
        fio_output = self.run_fio(self.write_fio, "write")
        self.fio_parse_result(fio_output, write_cache_mode, "write")
        flag = False
        if self.power_trigger:
            flag = True
            self.power_trigger = False
        self.enable_disable_write_cache(write_cache_mode=write_cache_mode)
        fio_output = self.run_fio(self.read_fio, "read")
        self.fio_parse_result(fio_output, write_cache_mode, "read")
        if flag:
            self.power_trigger = True

    def enable_disable_write_cache(self, write_cache_mode: str = "enable") -> None:
        """
        This function will enable/disable the write cache based on the write_cache
        parameter.
        @param: list :supported_drive_list
        @param: string : write_cache_mode

        To maintian uniformity with SAS drive, using the @param,save_state.
        """
        for drive in self.supported_drive_list:
            if write_cache_mode == "disable":
                drive.disable_write_cache(self.save_state)
            else:
                drive.enable_write_cache(self.save_state)

    def fio_parse_result(self, fio_output, write_cache_mode, operation) -> None:
        """
        This function will get the fio result after fio verify for cache disable
        and cache enabled process, and fio metrics are stored in a dictionary.
        @param: fio output result
        @param: string: condition-cache enabled/disable
        """
        condition = "cache_%s" % write_cache_mode
        self.final_result_dict[condition][operation] = fio_output["result"]

    def run_fio(self, fio_input, fio_name):
        """
        FIO Job of the SSD/HDD volatile write cache enable/disable Test.
        This method executes the FIO start test method where the FIO process:
        is started(creationg FIO job to scheduling it on the DUT).

        @return : fio output result
        """
        self.test_control["job_name"] = fio_name
        self.test_control["power_trigger"] = self.power_trigger
        self.test_control["run_definition"] = fio_input
        fio = FioRunner(self.host, self.test_control)
        fio.start_test()
        out = fio.parse_results()
        return out

    def cleanup(self, *args, **kwargs) -> None:
        """
        This will again set the write cache to its original setting.
        To maintian uniformity with SAS drive, using the @param,save_state.
        """
        if self.drive_state:
            for device in self.test_drives:
                value = self.drive_state[device]
                if value:
                    device.enable_write_cache(self.save_state)
                else:
                    device.disable_write_cache(self.save_state)
        super().cleanup(*args, **kwargs)

    def check_errors(self) -> None:
        """
        Summary:
        Go through each key in dictionary and find if there are any errors.
        If there is error, raise TestError for reporting.
        """
        combined_err = ""
        for key, value in self.final_result_dict.items():
            for key2, value2 in value.items():
                if isinstance(value2, list):
                    for item in value2:
                        if "error" in item and item["error"] != 0:
                            combined_err += "\n".join(str({key: {key2: item}}))
        self.validate_condition(
            combined_err == "",
            "Fio job has warnigns or errors: %s" % combined_err,
            log_on_pass=False,
        )

    def compare_results(self) -> None:
        """
        Compare IOPS between enabled or disabled cache
        """
        disable = self.final_result_dict["cache_disable"]
        enable = self.final_result_dict["cache_enable"]
        for key, value in disable.items():
            for i in range(len(value)):
                if disable[key][i]["opt_filename"] == enable[key][i]["opt_filename"]:
                    for iops in ["read_iops", "write_iops"]:
                        if iops in disable[key][i] and iops in enable[key][i]:
                            if enable[key][i][iops] and disable[key][i][iops]:
                                _max = enable[key][i][iops]
                                _min = disable[key][i][iops]
                                if _min > _max:
                                    # For boot drive
                                    if "autoval" in disable[key][i]["opt_filename"]:
                                        self.log_info(
                                            "Drive %s has %s enabled %s vs disabled cache %s"
                                            % (
                                                disable[key][i]["opt_filename"],
                                                iops,
                                                _max,
                                                _min,
                                            )
                                        )
                                    else:
                                        # Check for diviation in 1%
                                        self.validate_greater_equal(
                                            _max * 0.01,
                                            abs(_max - _min),
                                            "Drive %s %s enabled %s vs disabled cache %s"
                                            % (
                                                disable[key][i]["opt_filename"],
                                                iops,
                                                _max,
                                                _min,
                                            ),
                                            raise_on_fail=False,
                                        )
                                else:
                                    self.validate_greater_equal(
                                        _max,
                                        _min,
                                        "Drive %s %s enabled vs disabled cache"
                                        % (disable[key][i]["opt_filename"], iops),
                                        raise_on_fail=False,
                                    )

    def get_test_params(self) -> str:
        params = "Power-cycle: {}, State save before test: {},".format(
            self.power_cycle, self.save_state
        )
        return params
