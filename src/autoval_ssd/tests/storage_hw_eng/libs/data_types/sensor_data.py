# pyre-unsafe
""" """

import enum
import re
import typing as t

from .data_record.data_record import datarec, DictConstructable, item

from .data_record.data_record_enum import enum_serial


@enum_serial(by_name=False)
class SensorType(enum.Enum):
    """
    Represents the sensor type.
    """

    VOLTAGE = "volts"
    CURRENT = "current"
    POWER = "power"
    FAN_SPEED = ("fan_speed", "rpm")
    TEMPERATURE = ("temp", "temperature")
    AIRFLOW = "airflow"
    UNKNOWN = "unknown"

    @staticmethod
    def units_to_sensor_type(units: str) -> "SensorType":
        """
        Convert units to what sensor type.
        """

        VOLTAGE_CONVERSION_SET = {"V", "Volt", "Volts"}
        CURRENT_CONVERSION_SET = {"A", "Amp", "Amphere", "Amps", "Ampheres"}
        POWER_CONVERSION_SET = {"W", "Watts"}
        FAN_SPEED_CONVERSION_SET = {"RPM"}
        TEMPERATURE_CONVERSION_SET = {"C", "Celcius"}
        AIRFLOW_CONVERSION_SET = {"CFM"}

        if units in VOLTAGE_CONVERSION_SET:
            return SensorType.VOLTAGE
        if units in CURRENT_CONVERSION_SET:
            return SensorType.CURRENT
        if units in POWER_CONVERSION_SET:
            return SensorType.POWER
        if units in FAN_SPEED_CONVERSION_SET:
            return SensorType.FAN_SPEED
        if units in TEMPERATURE_CONVERSION_SET:
            return SensorType.TEMPERATURE
        if units in AIRFLOW_CONVERSION_SET:
            return SensorType.AIRFLOW

        return SensorType.UNKNOWN


@datarec
class SensorData(DictConstructable):
    """
    Represents the data from a sensor.
    """

    name = item(data_type=str, keyword="name", docstr="The name of the sensor.")

    sensor_num = item(
        data_type=t.Optional[int],
        keyword="sensor_number",
        default=None,
        docstr="The number of the sensor.",
    )

    sensor_type = item(
        data_type=t.Optional[SensorType],
        keyword="type",
        default=None,
        docstr="The type of the sensor.",
    )

    value = item(
        data_type=t.Optional[float],
        keyword="value",
        default=None,
        docstr="The value of the sensor.",
    )

    unit = item(
        data_type=t.Optional[str],
        keyword="unit",
        default=None,
        docstr="The unit for the sensor.",
    )

    def __init__(
        self,
        name=name,
        sensor_num=sensor_num,
        sensor_type=sensor_type,
        value=value,
        unit=unit,
    ):
        SensorData.name = name
        SensorData.sensor_num = sensor_num
        SensorData.sensor_type = sensor_type
        SensorData.value = value
        SensorData.unit = unit

    @classmethod
    def parse_from_bmc_sensor_util(cls, bmc_input: str):
        # def parse_from_bmc_sensor_util(cls, bmc_input: str) -> t.Dict[str, "SensorData"]:
        """
        Parse sensor information from the bmc output.

        Params:
        bmc_input (str): The raw sensor output from the bmc.

        Returns:
        A dict mapping sensor names to the corresponding data.
        """
        re_string = r"{}{}\s+:\s+(({})|({})){}".format(
            r"(?P<sensor_name>\w+.*\w)\s+",  # Match the name for the sensor
            r"\((?P<sensor_num>0x[0-9A-Fa-f][0-9A-Fa-f]*)\)",  # Match the sensor number
            r"(?P<value>-?\d+\.*\d*)\s+(?P<units>\w+)",  # Match sensor value/units
            r"NA",  # Match NA
            r"\s+\|\s+\((?P<sensor_status>\w+)\)",  # Match the status
        )

        sensor_dict = {}

        for line in bmc_input.split("\n"):
            # Check if valid sensor
            match = re.search(re_string, line)
            if match:
                sensor_dict[match["sensor_name"]] = SensorData(
                    name=match["sensor_name"],
                    sensor_num=match["sensor_num"],
                    sensor_type=SensorType.units_to_sensor_type(match["units"]),
                    value=match["value"],
                    unit=match["units"],
                )

        return sensor_dict
