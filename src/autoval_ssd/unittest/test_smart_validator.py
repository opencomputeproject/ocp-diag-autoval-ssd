#!/usr/bin/env python3
# pyre-unsafe

import unittest
from unittest import mock

import autoval_ssd.lib.utils.storage.smart_validator as smart_validator
from autoval.lib.utils.autoval_exceptions import TestError, TestStepError
from autoval.lib.utils.autoval_log import AutovalLog


class SmartValidatorUnitTest(unittest.TestCase):
    def test_compare_drive_data(self):
        drive_serial_no = "ZHZ2PKKR0000C9381T89"
        validate_config = {
            "element_in_grown_defect": "==",
            "health": "==",
            "read_uncorrected_errors": "==",
            "write_uncorrected_errors": "==",
        }
        smart_before = {
            "health": "OK",
            "element_in_grown_defect": 0,
            "read_uncorrected_errors": 0,
            "write_uncorrected_errors": 0,
            "Invalid DWORD count": 0,
            "Running disparity error count": 0,
            "Loss of DWORD synchronization": 212,
            "Phy reset problem": 0,
            "Invalid word count": 0,
            "Loss of dword synchronization count": 212,
            "Phy reset problem count": 0,
        }
        smart_after = {
            "health": "OK",
            "element_in_grown_defect": 0,
            "read_uncorrected_errors": 0,
            "write_uncorrected_errors": 0,
            "Invalid DWORD count": 0,
            "Running disparity error count": 0,
            "Loss of DWORD synchronization": 215,
            "Phy reset problem": 0,
            "Invalid word count": 0,
            "Loss of dword synchronization count": 215,
            "Phy reset problem count": 0,
        }
        smart_validator.compare_drive_data(
            drive_serial_no, validate_config, smart_before, smart_after
        )
        # Exceptional case where smart_after is empty
        with self.assertRaises(TestError) as exp:
            smart_validator.compare_drive_data(
                drive_serial_no, validate_config, smart_before, {}
            )
        self.assertEqual(
            "[AUTOVAL TEST ERROR] smart_after is empty", str(exp.exception)
        )
        # Exceptional case where smart_before is empty
        with self.assertRaises(TestError) as exp:
            smart_validator.compare_drive_data(
                drive_serial_no, validate_config, {}, smart_after
            )
        self.assertEqual(
            "[AUTOVAL TEST ERROR] smart_before is empty", str(exp.exception)
        )
        # Exceptional case where smart_after and smart_before is empty
        with self.assertRaises(TestError) as exp:
            smart_validator.compare_drive_data(drive_serial_no, validate_config, {}, {})
        self.assertEqual(
            "[AUTOVAL TEST ERROR] smart_before is empty", str(exp.exception)
        )

    @mock.patch.object(AutovalLog, "log_test_result")
    def test_validate_smart_value(self, mock_log):
        # case 1: field has '-'
        # before and after are equal
        field = "Reallocated_Sector_Ct-thresh"
        smart_before = {"Reallocated_Sector_Ct-thresh": 0}
        serial = "19208A800929"
        self.assertEqual(
            smart_validator._validate_smart_value(
                field, smart_before, smart_before, serial
            ),
            (0, 0),
        )

        # case 2: field has '-'
        # before and after are not equal
        smart_after = {"Reallocated_Sector_Ct-thresh": 2}
        self.assertEqual(
            smart_validator._validate_smart_value(
                field, smart_before, smart_after, serial
            ),
            (2, 0),
        )

        # case 3: field doesn't has '-'
        # before and after are equal
        field = "Command failed due to ICRC error"
        self.assertEqual(
            smart_validator._validate_smart_value(
                field, {field: 0}, {field: 0}, serial
            ),
            (0, 0),
        )

        # case 4: field doesn't has '-'
        # before and after are not equal
        self.assertEqual(
            smart_validator._validate_smart_value(
                field, {field: 4}, {field: 0}, serial
            ),
            (0, 4),
        )

        # case 5: field in before_test is None
        smart_validator._validate_smart_value(field, {}, {field: 0}, serial)

        # case 6: field in after_test is None
        with self.assertRaises(TestError):
            smart_validator._validate_smart_value(
                field,
                {field: 0},
                {},
                serial,
            )

        # case 7: field in before_test and after_test is None
        with self.assertRaises(TestError):
            smart_validator._validate_smart_value(
                field,
                {},
                {},
                serial,
            )

    def test_compare_drive_data_field(self):
        # checking operator ==
        smart_validator._compare_drive_data_field(
            "PASSED", "PASSED", "19208A800929", "health", "=="
        )
        # Exceptional case where unsupported operator is passed
        with self.assertRaises(TestError) as exp:
            smart_validator._compare_drive_data_field(
                0, 4, "1928", "element_in_grown_defect", "|"
            )
        self.assertEqual(
            "[AUTOVAL TEST ERROR] No matching operator found in |.", str(exp.exception)
        )
        # checking operator >
        smart_validator._compare_drive_data_field(
            100, 100, "ZHZ2MPND0000C9383C2N", "avail_spare", ">80"
        )
        # checking operator <
        smart_validator._compare_drive_data_field(
            307, 308, "ZHZ2MPND0000C9383C2N", "temperature", "<348"
        )
        # checking operator ~
        smart_validator._compare_drive_data_field(
            1, 2, "ZHZ2MPND0000C9383C2N", "Soft ECC Error Count", "~10"
        )
        # checking range
        smart_validator._compare_drive_data_field(
            307, 308, "ZHZ2MPND0000C9383C2N", "temperature", "300-348"
        )
        # checking if it is present in string
        smart_validator._compare_drive_data_field(
            "f", "f", "ZHZ2MPND0000C9383C2N", "temperature_status", "e/f/c"
        )
        smart_validator._compare_drive_data_field(
            "30", "34", "ZHZ2MPND0000C9383C2N", "Phy reset problem", "<40"
        )

    def test_evaluate_expression(self):
        msg = "Compare drive ZHZ2MPND0000C9383C2N temperature before vs. after test."
        with self.assertRaisesRegex(TestStepError, r"Operator \? not supported"):
            smart_validator._evaluate_expression(0, 4, "?", msg, False)
        smart_validator._evaluate_expression(308, 348, "-", msg, 300, False)
        smart_validator._evaluate_expression(0, 0, "~", msg, 10, False)
        smart_validator._evaluate_expression(10, 10, "=", msg, False)
        smart_validator._evaluate_expression(100, 100, ">", msg, False)
        smart_validator._evaluate_expression(["E", "F", "W", "N"], "N", "/", msg, False)
