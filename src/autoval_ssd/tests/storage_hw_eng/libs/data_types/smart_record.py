# pyre-unsafe
import re
import typing as t

from .data_record.data_record import datarec, DictConstructable, item


class SmartInfoFactory:
    def create_smart_info(self, smartlog: str):
        if "SATA Version is" in smartlog:
            return SATASmartLog.parse_smart(smartlog)
        if "Transport protocol" in smartlog:
            return SASSmartLog.parse_smart(smartlog)
        else:
            return SmartctlInfo.parse_smart(smartlog)


@datarec
class SmartctlInfo(DictConstructable):
    version = item(
        data_type=t.Optional[t.List[int]],
        keyword="version",
        default=None,
        docstr="smartctl version.",
    )

    svn_revision = item(
        data_type=t.Optional[str],
        keyword="svn_revision",
        default=None,
        docstr="smartctl revision.",
    )

    platform_info = item(
        data_type=t.Optional[str],
        keyword="platform_info",
        default=None,
        docstr="Platform information",
    )

    build_info = item(
        data_type=t.Optional[str],
        keyword="build_info",
        default=None,
        docstr="smartctl build information.",
    )

    args = item(
        data_type=t.Optional[t.List[str]],
        keyword="argv",
        default=None,
        docstr="smartctl arguments.",
    )

    output = item(
        data_type=str, default="", keyword="output", docstr="Raw output lines"
    )

    exit_status = item(
        data_type=t.Optional[int],
        keyword="exit_status",
        default=None,
        docstr="smartctl exit status.",
    )

    interface = item(
        data_type=t.Optional[str],
        keyword="interface",
        default=None,
        docstr="Drive interface.",
    )

    def __init__(
        self,
        version=version,
        svn_revision=svn_revision,
        platform_info=platform_info,
        build_info=build_info,
        args=args,
        output=output,
        exit_status=exit_status,
        interface=interface,
    ):
        SmartctlInfo.version = version
        SmartctlInfo.svn_revision = svn_revision
        SmartctlInfo.platform_info = platform_info
        SmartctlInfo.build_info = build_info
        SmartctlInfo.args = args
        SmartctlInfo.output = output
        SmartctlInfo.exit_status = exit_status
        SmartctlInfo.interface = interface

    @classmethod
    def parse_smart(cls, smartlog: str):
        return cls(output=smartlog)


@datarec
class SASSmartInfoSection(DictConstructable):
    vendor = item(
        data_type=t.Optional[str],
        keyword="vendor",
        default=None,
        docstr="Drive vendor.",
    )

    product = item(
        data_type=t.Optional[str], keyword="product", default=None, docstr="Product id."
    )

    revision = item(
        data_type=t.Optional[str],
        keyword="revision",
        default=None,
        docstr="Revision number",
    )

    compiance = item(
        data_type=t.Optional[str],
        keyword="compiance",
        default=None,
        docstr="The compliance spec.",
    )

    user_capacity = item(
        data_type=t.Optional[int],
        keyword="user_capacity",
        default=None,
        docstr="The user capacity in bytes.",
    )

    user_capacity_TB = item(
        data_type=t.Optional[float],
        keyword="user_capacity_TB",
        default=None,
        docstr="The user capacity in TB.",
    )

    logical_blk_size = item(
        data_type=t.Optional[int],
        keyword="logical_blk_size",
        default=None,
        docstr="The logical block size.",
    )

    rotation_rate = item(
        data_type=t.Optional[int],
        keyword="rotation_rate",
        default=None,
        docstr="The Rotation Rate of the drive.",
    )

    form_factor = item(
        data_type=t.Optional[str],
        keyword="form_factor",
        default=None,
        docstr="The drive form factor.",
    )

    logical_unit_id = item(
        data_type=t.Optional[str],
        keyword="logical_unit_id",
        default=None,
        docstr="The logical unit id.",
    )

    serial_number = item(
        data_type=t.Optional[str],
        keyword="serial_number",
        default=None,
        docstr="The drive serial number.",
    )

    device_type = item(
        data_type=t.Optional[str],
        keyword="device_type",
        default=None,
        docstr="The device type.",
    )

    transport_protocol = item(
        data_type=t.Optional[str],
        keyword="transport_protocol",
        default=None,
        docstr="The transport protocol",
    )

    link_speed = item(
        data_type=float, keyword="link_speed", default=None, docstr="The link speed."
    )

    local_time = item(
        data_type=t.Optional[str],
        keyword="local_time",
        default=None,
        docstr="String representation of local time.",
    )

    smart_support = item(
        data_type=t.Optional[bool],
        keyword="smart_support",
        default=None,
        docstr="If SMART is supported on this device.",
    )

    smart_enabled = item(
        data_type=t.Optional[bool],
        keyword="smart_enabled",
        default=None,
        docstr="If SMART is enabled on this device.",
    )

    temperature_warning = item(
        data_type=t.Optional[bool],
        keyword="temperature_warning",
        default=None,
        docstr="Whether or not temp. warning is enabled.",
    )

    read_cache = item(
        data_type=t.Optional[bool],
        keyword="read_cache",
        default=None,
        docstr="Read cache state.",
    )

    writeback_cache = item(
        data_type=t.Optional[bool],
        keyword="writeback_cache",
        default=None,
        docstr="Writeback cache state.",
    )

    def __init__(
        self,
        vendor=vendor,
        product=product,
        revision=revision,
        compiance=compiance,
        user_capacity=user_capacity,
        user_capacity_TB=user_capacity_TB,
        logical_blk_size=logical_blk_size,
        rotation_rate=rotation_rate,
        form_factor=form_factor,
        logical_unit_id=logical_unit_id,
        serial_number=serial_number,
        device_type=device_type,
        transport_protocol=transport_protocol,
        link_speed=link_speed,
        local_time=local_time,
        smart_support=smart_support,
        smart_enabled=smart_enabled,
        temperature_warning=temperature_warning,
        read_cache=read_cache,
        writeback_cache=writeback_cache,
    ):
        SASSmartInfoSection.vendor = vendor
        SASSmartInfoSection.product = product
        SASSmartInfoSection.revision = revision
        SASSmartInfoSection.compiance = compiance
        SASSmartInfoSection.user_capacity = user_capacity
        SASSmartInfoSection.user_capacity_TB = user_capacity_TB
        SASSmartInfoSection.logical_blk_size = logical_blk_size
        SASSmartInfoSection.rotation_rate = rotation_rate
        SASSmartInfoSection.form_factor = form_factor
        SASSmartInfoSection.logical_unit_id = logical_unit_id
        SASSmartInfoSection.serial_number = serial_number
        SASSmartInfoSection.device_type = device_type
        SASSmartInfoSection.transport_protocol = transport_protocol
        SASSmartInfoSection.link_speed = link_speed
        SASSmartInfoSection.local_time = local_time
        SASSmartInfoSection.smart_support = smart_support
        SASSmartInfoSection.smart_enabled = smart_enabled
        SASSmartInfoSection.temperature_warning = temperature_warning
        SASSmartInfoSection.read_cache = read_cache
        SASSmartInfoSection.writeback_cache = writeback_cache

    @classmethod
    def parse_smart(cls, smartlog: str):
        regex_patterns = {
            "vendor": (r"Vendor: +" + r"(?P<vendor>\w+)[ \t]*\n"),
            "product": (r"Product: +" + r"(?P<product>\w+)[ \t]*\n"),
            "revision": (r"Revision: +" + r"(?P<revision>\w+)[ \t]*\n"),
            "compliance": (r"Compliance: +" + r"(?P<compliance>\S.*\S)[ \t]*\n"),
            "user_capacity": (
                r"User Capacity: +(?P<user_capacity>[,\d]+) +"
                + r"bytes \[(?P<user_capacity_TB>\d+\.\d+) TB\][ \t]*\n"
            ),
            "logical_blk_size": (
                r"Logical block size: +" + r"(?P<logical_blk_size>\d+) bytes.*\n"
            ),
            "rotation_rate": (
                r"Rotation Rate: +" + r"(?P<rotation_rate>\d+) rpm[ \t]*\n"
            ),
            "form_factor": (r"Form Factor: +" + r"(?P<form_factor>\S.*\S)[ \t]*\n"),
            "logical_unit_id": (
                r"Logical Unit id: +" + r"(?P<logical_unit_id>\S.*\S)[ \t]*\n"
            ),
            "serial_number": (r"Serial number: +" + r"(?P<serial_number>\w+)[ \t]*"),
            "device_type": (r"Device type: +" + r"(?P<device_type>\w+)[ \t]*"),
            "transport_protocol": (
                r"Transport protocol: +" + r"(?P<transport_protocol>\S.*\S)[ \t]*"
            ),
            "link_speed": (
                r"negotiated logical link rate.*"
                + r"(?P<link_speed>\d+\.*\d+) Gbps.*\n"
            ),
            "local_time": (r"Local Time is: +" + r"(?P<local_time>\S.*\S)[ \t]*"),
            "smart_support": (
                r"SMART support is: +" + r"(?P<support>(Available)|(Unavailable)).*"
            ),
            "smart_enabled": (
                r"SMART support is: +" + r"(?P<enabled>(Enabled)|(Disabled)).*"
            ),
            "temperature_warning": (
                r"Temperature Warning: +" + r"(?P<support>(Enabled)|(Disabled)).*"
            ),
            "read_cache": (
                r"Read Cache is: +" + r"(?P<enabled>(Enabled)|(Disabled)).*"
            ),
            "writeback_cache": (
                r"Writeback Cache is: +" + r"(?P<enabled>(Enabled)|(Disabled)).*"
            ),
        }

        matches = {k: re.search(patt, smartlog) for k, patt in regex_patterns.items()}

        return cls(
            vendor=get_group(matches["vendor"], "vendor"),
            product=get_group(matches["product"], "product"),
            revision=get_group(matches["revision"], "revision"),
            compiance=get_group(matches["compliance"], "compliance"),
            user_capacity=get_group(matches["user_capacity"], "user_capacity").replace(
                ",", ""
            ),
            user_capacity_TB=get_group(matches["user_capacity"], "user_capacity_TB"),
            logical_blk_size=get_group(matches["logical_blk_size"], "logical_blk_size"),
            rotation_rate=get_group(matches["rotation_rate"], "rotation_rate"),
            form_factor=get_group(matches["form_factor"], "form_factor"),
            logical_unit_id=get_group(matches["logical_unit_id"], "logical_unit_id"),
            serial_number=get_group(matches["serial_number"], "serial_number"),
            device_type=get_group(matches["device_type"], "device_type"),
            transport_protocol=get_group(
                matches["transport_protocol"], "transport_protocol"
            ),
            link_speed=get_group(matches["link_speed"], "link_speed"),
            local_time=get_group(matches["local_time"], "local_time"),
            smart_support=check_string(matches["smart_support"], "Available"),
            smart_enabled=check_string(matches["smart_enabled"], "Enabled"),
            temperature_warning=check_string(matches["temperature_warning"], "Enabled"),
            read_cache=check_string(matches["read_cache"], "Enabled"),
            writeback_cache=check_string(matches["writeback_cache"], "Enabled"),
        )


@datarec
class SASSmartDataSection(DictConstructable):
    """ """

    heath_status = item(
        data_type=t.Optional[str],
        keyword="heath_status",
        default=None,
        docstr="Health Status of the drive.",
    )

    current_drive_temp = item(
        data_type=t.Optional[int],
        keyword="current_drive_temp",
        default=None,
        docstr="The current drive temp.",
    )

    drive_trip_temp = item(
        data_type=t.Optional[int],
        keyword="drive_trip_temp",
        default=None,
        docstr="The trip temp. of the drive.",
    )

    manufacture_date = item(
        data_type=t.Optional[str],
        keyword="manufacture_date",
        default=None,
        docstr="Manufacture date.",
    )

    lifetime_cycle_count = item(
        data_type=t.Optional[int],
        keyword="lifetime_cycle_count",
        default=None,
        docstr="The lifetime cycle count.",
    )

    accum_start_stop_cycles = item(
        data_type=t.Optional[int],
        keyword="accum_start_stop_cycles",
        default=None,
        docstr="The accumulated start and stop cycles.",
    )

    lifetime_load_unload = item(
        data_type=t.Optional[int],
        keyword="lifetime_load_unload",
        default=None,
        docstr="The specified lifetime load unload cycles.",
    )

    accum_load_unload_cycles = item(
        data_type=t.Optional[int],
        keyword="accum_load_unload_cycles",
        default=None,
        docstr="The accumulated load and unload cycles.",
    )

    grown_defect_list = item(
        data_type=t.Optional[int],
        keyword="grown_defect_list",
        default=None,
        docstr="The number of elements in the g-list.",
    )


@datarec
class SASSmartLog(SmartctlInfo):
    """ """

    info_section = item(
        data_type=t.Optional[SASSmartInfoSection],
        keyword="info_section",
        docstr="Smartlog info Section",
    )

    data_section = item(
        data_type=t.Optional[SASSmartDataSection],
        keyword="data_section",
        default=None,
        docstr="Smartlog data Section",
    )

    output = item(
        data_type=str, default="", keyword="output", docstr="Raw output lines"
    )

    interface = item(
        data_type=t.Optional[str],
        keyword="interface",
        default=None,
        docstr="Drive interface.",
    )

    def __init__(
        self,
        info_section=info_section,
        data_section=data_section,
        output=output,
        interface=interface,
    ):
        SASSmartLog.info_section = info_section
        SASSmartLog.data_section = data_section
        SASSmartLog.output = output
        SASSmartLog.interface = interface

    @classmethod
    def parse_smart(cls, smartlog: str):
        return cls(
            output=smartlog,
            interface="SAS",
            info_section=SASSmartInfoSection.parse_smart(smartlog),
        )


@datarec
class SATASmartInfoSection(DictConstructable):
    device_model = item(
        data_type=t.Optional[str],
        keyword="device_model",
        default=None,
        docstr="Drive model.",
    )

    device_vendor = item(
        data_type=t.Optional[str],
        keyword="device_vendor",
        default=None,
        docstr="Drive vendor.",
    )

    lu_wwn_device_id = item(
        data_type=t.Optional[str],
        keyword="lu_wwn_device_id",
        default=None,
        docstr="LU WWN Device ID.",
    )

    device_sn = item(
        data_type=t.Optional[str],
        keyword="device_serial_number",
        default=None,
        docstr="Drive serial number.",
    )

    fw_version = item(
        data_type=t.Optional[str],
        keyword="firmware_version",
        default=None,
        docstr="Drive Firmware Version.",
    )

    user_capacity = item(
        data_type=t.Optional[int],
        keyword="user_capacity",
        default=None,
        docstr="The user capacity in bytes.",
    )

    user_capacity_TB = item(
        data_type=t.Optional[float],
        keyword="user_capacity_TB",
        default=None,
        docstr="The user capacity in TB.",
    )

    sector_size = item(
        data_type=t.Optional[int],
        keyword="sector_size",
        default=None,
        docstr="The sector size in bytes.",
    )

    rotation_rate = item(
        data_type=t.Optional[int],
        keyword="rotation_rate",
        default=None,
        docstr="The rotation rate of the drive.",
    )

    form_factor = item(
        data_type=t.Optional[str],
        keyword="form_factor",
        default=None,
        docstr="Drive form factor.",
    )

    ata_version = item(
        data_type=t.Optional[str],
        keyword="ata_version",
        default=None,
        docstr="ATA version.",
    )

    sata_version = item(
        data_type=t.Optional[str],
        keyword="sata_version",
        default=None,
        docstr="SATA version.",
    )

    link_speed = item(
        data_type=t.Optional[float],
        keyword="link_speed",
        default=None,
        docstr="The link speed.",
    )

    local_time = item(
        data_type=t.Optional[str],
        keyword="local_time",
        default=None,
        docstr="String representation of local time.",
    )

    smart_support = item(
        data_type=t.Optional[bool],
        keyword="smart_support",
        default=None,
        docstr="If SMART is supported on this device.",
    )

    smart_enabled = item(
        data_type=t.Optional[bool],
        keyword="smart_enabled",
        default=None,
        docstr="If SMART is enabled on this device.",
    )

    aam_feature = item(
        data_type=t.Optional[str],
        keyword="aam_feature",
        default=None,
        docstr="AAM feature on the drive.",
    )

    apm_feature = item(
        data_type=t.Optional[str],
        keyword="apm_feature",
        default=None,
        docstr="APM feature on the drive.",
    )

    rd_look_ahead = item(
        data_type=t.Optional[bool],
        keyword="read_look_ahead",
        default=None,
        docstr="If read look ahead cache is enabled.",
    )

    write_cache = item(
        data_type=t.Optional[bool],
        keyword="write_cache",
        default=None,
        docstr="If write cache is enabled.",
    )

    ata_security = item(
        data_type=t.Optional[str],
        keyword="ata_security",
        default=None,
        docstr="ATA security status.",
    )

    write_sct_feature_ctrl_cmd = item(
        data_type=t.Optional[str],
        keyword="write_sct_feature_ctrl_cmd",
        default=None,
        docstr="...",
    )

    write_cache_reorder = item(
        data_type=t.Optional[str],
        keyword="write_cache_reorder",
        default=None,
        docstr="If write cache reordering is enabled.",
    )

    def __init__(
        self,
        device_model=device_model,
        device_vendor=device_vendor,
        lu_wwn_device_id=lu_wwn_device_id,
        device_sn=device_sn,
        fw_version=fw_version,
        user_capacity=user_capacity,
        user_capacity_TB=user_capacity_TB,
        sector_size=sector_size,
        rotation_rate=rotation_rate,
        form_factor=form_factor,
        ata_version=ata_version,
        sata_version=sata_version,
        link_speed=link_speed,
        local_time=local_time,
        smart_support=smart_support,
        smart_enabled=smart_enabled,
        aam_feature=aam_feature,
        apm_feature=apm_feature,
        rd_look_ahead=rd_look_ahead,
        write_cache=write_cache,
        ata_security=ata_security,
        write_sct_feature_ctrl_cmd=write_sct_feature_ctrl_cmd,
        write_cache_reorder=write_cache_reorder,
    ):
        SATASmartInfoSection.device_model = device_model
        SATASmartInfoSection.device_vendor = device_vendor
        SATASmartInfoSection.lu_wwn_device_id = lu_wwn_device_id
        SATASmartInfoSection.device_sn = device_sn
        SATASmartInfoSection.fw_version = fw_version
        SATASmartInfoSection.user_capacity = user_capacity
        SATASmartInfoSection.user_capacity_TB = user_capacity_TB
        SATASmartInfoSection.sector_size = sector_size
        SATASmartInfoSection.rotation_rate = rotation_rate
        SATASmartInfoSection.form_factor = form_factor
        SATASmartInfoSection.ata_version = ata_version
        SATASmartInfoSection.sata_version = sata_version
        SATASmartInfoSection.link_speed = link_speed
        SATASmartInfoSection.local_time = local_time
        SATASmartInfoSection.smart_support = smart_support
        SATASmartInfoSection.smart_enabled = smart_enabled
        SATASmartInfoSection.aam_feature = aam_feature
        SATASmartInfoSection.apm_feature = apm_feature
        SATASmartInfoSection.rd_look_ahead = rd_look_ahead
        SATASmartInfoSection.write_cache = write_cache
        SATASmartInfoSection.ata_security = ata_security
        SATASmartInfoSection.write_sct_feature_ctrl_cmd = write_sct_feature_ctrl_cmd
        SATASmartInfoSection.write_cache_reorder = write_cache_reorder

    @classmethod
    def parse_smart(cls, smartlog: str) -> "SATASmartInfoSection":
        regex_patterns = {
            "device_model": (
                r"Device Model: +"
                + r"(?P<device_vendor>\w+) +(?P<device_model>\w+)[ \t]*\n"
            ),
            "serial_number": (r"Serial Number: +" + r"(?P<device_sn>\w+)[ \t]*\n"),
            "lu_wwn_number": (
                r"LU WWN Device Id: +" + r"(?P<lu_wwn_device_id>[\w ]+)[ \t]*\n"
            ),
            "fw_version": (r"Firmware Version: +" + r"(?P<fw_version>\w+)[ \t]*\n"),
            "user_capacity": (
                r"User Capacity: +(?P<user_capacity>[,\d]+) +"
                + r"bytes \[(?P<user_capacity_TB>\d+\.\d+) TB\][ \t]*\n"
            ),
            "sector_size": (r"Sector Size: +" + r"(?P<sector_size>\d+) bytes.*\n"),
            "rotation_rate": (
                r"Rotation Rate: +" + r"(?P<rotation_rate>\d+) rpm[ \t]*\n"
            ),
            "form_factor": (r"Form Factor: +" + r"(?P<form_factor>\S.*\S)[ \t]*\n"),
            "device_is": (r"Device is: +" + r"(?P<device>\S.*\S)[ \t]*\n"),
            "ata_version": (r"ATA Version is: +" + r"(?P<ata_version>\S.*\S)[ \t]*"),
            "sata_version": (r"SATA Version is: +" + r"(?P<sata_version>\S.*\S)[ \t]*"),
            "link_speed": (
                r"SATA Version is:.*current:.*" + r"(?P<link_speed>\d+\.\d+) Gb/s.*"
            ),
            "local_time": (r"Local Time is: +" + r"(?P<local_time>\S.*\S)[ \t]*"),
            "smart_support": (
                r"SMART support is: +" + r"(?P<support>(Available)|(Unavailable)).*"
            ),
            "smart_enabled": (
                r"SMART support is: +" + r"(?P<enabled>(Enabled)|(Disabled)).*"
            ),
            "AAM_feature": (
                r"AAM feature is: +" + r"(?P<support>(Available)|(Unavailable)).*"
            ),
            "APM_feature": (
                r"APM feature is: +" + r"(?P<enabled>(Enabled)|(Disabled)).*"
            ),
            "rd_look_ahead": (
                r"Rd look-ahead is: +" + r"(?P<enabled>(Enabled)|(Disabled)).*"
            ),
            "write_cache": (
                r"Write cache is: +" + r"(?P<enabled>(Enabled)|(Disabled)).*"
            ),
            "ata_security": (
                r"ATA Security is: +" + r"(?P<enabled>(Enabled)|(Disabled)).*"
            ),
            "write_cache_reorder": (
                r"Wt Cache Reorder: +" + r"(?P<enabled>(Enabled)|(Disabled)).*"
            ),
        }

        matches = {k: re.search(patt, smartlog) for k, patt in regex_patterns.items()}

        return cls(
            device_model=get_group(matches["device_model"], "device_model"),
            device_vendor=get_group(matches["device_model"], "device_vendor"),
            device_sn=get_group(matches["serial_number"], "device_sn"),
            lu_wwn_device_id=get_group(matches["lu_wwn_number"], "lu_wwn_device_id"),
            fw_version=get_group(matches["fw_version"], "fw_version"),
            user_capacity=get_group(matches["user_capacity"], "user_capacity").replace(
                ",", ""
            ),
            user_capacity_TB=get_group(matches["user_capacity"], "user_capacity_TB"),
            sector_size=get_group(matches["sector_size"], "sector_size"),
            rotation_rate=get_group(matches["rotation_rate"], "rotation_rate"),
            form_factor=get_group(matches["form_factor"], "form_factor"),
            ata_version=get_group(matches["ata_version"], "ata_version"),
            sata_version=get_group(matches["sata_version"], "sata_version"),
            link_speed=get_group(matches["link_speed"], "link_speed"),
            local_time=get_group(matches["local_time"], "local_time"),
            smart_support=check_string(matches["smart_support"], "Available"),
            smart_enabled=check_string(matches["smart_enabled"], "Enabled"),
            aam_feature=check_string(matches["AAM_feature"], "Available"),
            apm_feature=check_string(matches["APM_feature"], "Enabled"),
            rd_look_ahead=check_string(matches["rd_look_ahead"], "Enabled"),
            write_cache=check_string(matches["write_cache"], "Enabled"),
            ata_security=check_string(matches["ata_security"], "Enabled"),
            write_cache_reorder=check_string(matches["write_cache_reorder"], "Enabled"),
        )


def check_string(match, positive_strs):
    if match is None:
        return None

    if isinstance(positive_strs, str):
        positive_strs = [positive_strs]

    for s in positive_strs:
        if s in match[0]:
            return True

    else:
        return False


def get_group(match, group):
    if match is None:
        return None

    return match[group]


@datarec
class SATASmartAttributes(DictConstructable):
    id_num = item(data_type=int, keyword="id_num", docstr="Atrribute ID number.")

    name = item(data_type=str, keyword="name", docstr="Name of the attribute.")

    flags = item(data_type=str, keyword="flags", docstr="Attribute Flags.")

    value = item(data_type=str, keyword="value", docstr="Attribute Value.")

    worst = item(data_type=int, keyword="worst", docstr="Worst value ever assigned.")

    threshold = item(data_type=int, keyword="threshold", docstr="Value threshold.")

    fail = item(data_type=bool, keyword="fail", docstr="Attribute Failure.")

    raw_value = item(data_type=str, keyword="raw_value", docstr="Raw value.")


@datarec
class SATAPhyEventCtrs(DictConstructable):
    evt_id = item(data_type=str, keyword="evt_id", docstr="Event ID.")

    size = item(data_type=int, keyword="size", docstr="Counter size.")

    value = item(data_type=int, keyword="value", docstr="Counter value.")

    description = item(
        data_type=str, keyword="description", docstr="Event Description."
    )


@datarec
class SATASmartDataSection(DictConstructable):
    smart_heath = item(
        data_type=t.Optional[str],
        keyword="smart_overall_health_assessment",
        default=None,
        docstr="Health assessment of the drive.",
    )

    offline_data_collection_status = item(
        data_type=t.Optional[str],
        keyword="offline_data_collection_status",
        default=None,
        docstr="Offline data collection status.",
    )

    self_test_status = item(
        data_type=t.Optional[str],
        keyword="self_test_status",
        default=None,
        docstr="Self test status.",
    )

    tot_time_offline_data_collection = item(
        data_type=t.Optional[int],
        keyword="tot_time_offline_data_collection",
        default=None,
        docstr="Total time to complete offline data collection.",
    )

    offline_data_collection_capabilities = item(
        data_type=t.Optional[str],
        keyword="offline_data_collection_capabilities",
        default=None,
        docstr="Offline data collection capabilities.",
    )

    smart_capabilities = item(
        data_type=t.Optional[str],
        keyword="smart_capabilities",
        default=None,
        docstr="Smart capabilities.",
    )

    error_log_capabilities = item(
        data_type=t.Optional[str],
        keyword="error_log_capabilities",
        default=None,
        docstr="Error log capabilities.",
    )

    short_self_test_rec_poll_time = item(
        data_type=t.Optional[int],
        keyword="short_self_test_rec_poll_time",
        default=None,
        docstr="Recommended time for short self-test polling",
    )

    ext_self_test_rec_poll_time = item(
        data_type=t.Optional[int],
        keyword="ext_self_test_rec_poll_time",
        default=None,
        docstr="Recommended time for extended self-test polling",
    )

    conv_self_test_rec_poll_time = item(
        data_type=t.Optional[int],
        keyword="conv_self_test_rec_poll_time",
        default=None,
        docstr="Recommended time for conveyance self-test polling",
    )

    sct_capabilities = item(
        data_type=t.Optional[str],
        keyword="sct_capabilities",
        default=None,
        docstr="SCT capabilities.",
    )

    smart_attr_rev = item(
        data_type=t.Optional[str],
        keyword="smart_attr_rev",
        default=None,
        docstr="Smart Atrributes Data Struction revision number.",
    )

    smart_attrs = item(
        data_type=t.Optional[t.Dict[str, SATASmartAttributes]],
        keyword="smart_attrs",
        default=None,
        docstr="Dictionary of Smart attr names to their infomation.",
    )

    sct_status_ver = item(
        data_type=t.Optional[str],
        keyword="sct_status_ver",
        default=None,
        docstr="SCT status version.",
    )

    sct_ver = item(
        data_type=t.Optional[str],
        keyword="sct_ver",
        default=None,
        docstr="SCT version.",
    )

    sct_support_level = item(
        data_type=t.Optional[str],
        keyword="sct_support_level",
        default=None,
        docstr="SCT support level.",
    )

    device_sate = item(
        data_type=t.Optional[str],
        keyword="device_sate",
        default=None,
        docstr="Current device state.",
    )

    current_temp = item(
        data_type=t.Optional[int],
        keyword="current_temp",
        default=None,
        docstr="Current device temperature.",
    )

    power_cycle_min_temp = item(
        data_type=t.Optional[int],
        keyword="power_cycle_min_temp",
        default=None,
        docstr="Minimum temp during this power cycle.",
    )

    power_cycle_max_temp = item(
        data_type=t.Optional[int],
        keyword="power_cycle_max_temp",
        default=None,
        docstr="Maximum temp during this power cycle.",
    )

    lifetime_min_temp = item(
        data_type=t.Optional[int],
        keyword="lifetime_min_temp",
        default=None,
        docstr="Minimum temp during entire lifetime.",
    )

    lifetime_max_temp = item(
        data_type=t.Optional[int],
        keyword="lifetime_max_temp",
        default=None,
        docstr="Maximum temp during entire lifetime.",
    )

    under_temp_limit_cnt = item(
        data_type=t.Optional[int],
        keyword="lifetime_max_temp",
        default=None,
        docstr="Number of time under temp.",
    )

    over_temp_limit_cnt = item(
        data_type=t.Optional[int],
        keyword="lifetime_max_temp",
        default=None,
        docstr="Number of times over temp.",
    )

    sct_smart_status = item(
        data_type=t.Optional[str],
        keyword="sct_smart_status",
        default=None,
        docstr="SCT Smart Status.",
    )

    sct_temp_hist_ver = item(
        data_type=t.Optional[str],
        keyword="sct_temp_hist_ver",
        default=None,
        docstr="SCT history version.",
    )

    temp_sample_period = item(
        data_type=t.Optional[str],
        keyword="temp_sample_period",
        default=None,
        docstr="Temp. sampling period.",
    )

    temp_log_interval = item(
        data_type=t.Optional[str],
        keyword="temp_log_interval",
        default=None,
        docstr="Temp log interval.",
    )

    min_rec_temp = item(
        data_type=t.Optional[int],
        keyword="min_rec_temp",
        default=None,
        docstr="Minimum recorded temp.",
    )

    max_rec_temp = item(
        data_type=t.Optional[int],
        keyword="max_rec_temp",
        default=None,
        docstr="Maximum recorded temp.",
    )

    min_temp_limit = item(
        data_type=t.Optional[int],
        keyword="min_temp_limit",
        default=None,
        docstr="Minimum temperature limit.",
    )

    max_temp_limit = item(
        data_type=t.Optional[int],
        keyword="max_temp_limit",
        default=None,
        docstr="Maximum temperture limit.",
    )

    temp_hist_size = item(
        data_type=t.Optional[int],
        keyword="temp_hist_size",
        default=None,
        docstr="Temperature history size.",
    )

    sct_recovery_rd = item(
        data_type=t.Optional[int],
        keyword="sct_recovery_rd",
        default=None,
        docstr="SCT error recovery control read.",
    )

    sct_recovery_wr = item(
        data_type=t.Optional[int],
        keyword="sct_recovery_wr",
        default=None,
        docstr="SCT error recovery control write.",
    )

    sata_phy_event_ctrs = item(
        data_type=t.Optional[t.Dict[str, SATAPhyEventCtrs]],
        keyword="sata_phy_event_ctrs",
        default=None,
        docstr="Dictionary of phy event ctr descriptions to their infomation.",
    )


@datarec
class SATASmartLog(SmartctlInfo):
    """ """

    info_section = item(
        data_type=t.Optional[SATASmartInfoSection],
        keyword="info_section",
        docstr="Smartlog info Section",
    )

    data_section = item(
        data_type=t.Optional[SATASmartDataSection],
        keyword="data_section",
        default=None,
        docstr="Smartlog data Section",
    )
    output = item(
        data_type=str, default="", keyword="output", docstr="Raw output lines"
    )

    interface = item(
        data_type=t.Optional[str],
        keyword="interface",
        default=None,
        docstr="Drive interface.",
    )

    def __init__(
        self,
        info_section=info_section,
        data_section=data_section,
        output=output,
        interface=interface,
    ):
        SATASmartLog.info_section = info_section
        SATASmartLog.data_section = data_section
        SATASmartLog.output = output
        SATASmartLog.interface = interface

    @classmethod
    def parse_smart(cls, smartlog: str):
        return cls(
            output=smartlog,
            interface="SATA",
            info_section=SATASmartInfoSection.parse_smart(smartlog),
        )

    @staticmethod
    def smart_cmd(devname: str):
        return f"smartctl -x {devname} --json"
