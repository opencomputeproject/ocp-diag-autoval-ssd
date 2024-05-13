#!/usr/bin/env python3

# pyre-unsafe
import itertools
import re

from autoval.lib.utils.autoval_exceptions import CmdError, TestError
from autoval.lib.utils.autoval_log import AutovalLog
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval.lib.utils.decorators import retry


class SgUtils:

    ERR_CODES = {"SUCCESS": 0, "UNIT_ATTENTION": 6}

    # TODO: Note that this function was added due to a driver/IOC/expander error on
    # Bryce Canyon systems that would cause the driver to not clear a Unit Attention Status
    # after a drive reset properly. This error causes issues for sg3_utils since it will
    # error with code 6. This fix is taking adv. of the fact that the Unit Attention Status
    # is cleared after being read by the initiator. We only do this fix for functions that
    # are not for verification of the utility and are instead for gathering data from the
    # utility.
    # Tracked on T70461011.

    @staticmethod
    @retry(tries=10, sleep_seconds=30)
    def retry_on_unit_attention(host, sg3_util_cmd):
        """
        Wraps a run on sg3_util command on a host, but checks for unit attention
        and retries.
        """
        ret = host.run_get_result(sg3_util_cmd)
        if ret.stderr and "UNIT_ATTENTION" not in ret.stderr.upper():
            raise TestError(f"'{sg3_util_cmd}' failed with {ret.stderr}")
        return ret.stdout

    @staticmethod
    def get_hdd_lb_length(host, sg_device) -> int:
        cmd = "sg_readcap /dev/%s" % sg_device
        out = SgUtils.retry_on_unit_attention(host, cmd)
        match = re.search(r"Logical block length=(\d+)", out)
        if match:
            return int(match.group(1))
        raise TestError("Failed to get LB length of /dev/%s" % sg_device)

    @staticmethod
    def start_device(host, sg_device) -> None:
        cmd = "sg_start --start /dev/%s" % sg_device
        host.run(cmd)

    @staticmethod
    def stop_device(host, sg_device) -> None:
        cmd = "sg_start --stop /dev/%s" % sg_device
        host.run(cmd)

    @staticmethod
    def get_hdd_last_lba(host, sg_device) -> int:
        """
        Get last logical address block for a drive
        @param string drive: drive name e.g. 'sdb'
        @return int
        """
        cmd = "sg_readcap /dev/%s" % sg_device
        out = SgUtils.retry_on_unit_attention(host, cmd)
        match = re.search(r"Last (logical block address|LBA)=(\d+)", out)
        if match:
            return int(match.group(2))
        raise TestError("Failed to get last LBA of /dev/%s" % sg_device)

    @staticmethod
    def get_hdd_capacity(host, sg_device) -> int:
        """
        Get an HDD drive capacity
        """
        cmd = "sg_readcap /dev/%s" % sg_device
        out = SgUtils.retry_on_unit_attention(host, cmd)
        match = re.search(r"Device size: (\d+)", out)
        if match:
            return int(match.group(1))
        raise TestError("Failed to get drive /dev/%s capacity" % sg_device)

    @staticmethod
    def validate_sg_readcap(host, sg_device) -> None:
        cmd = "sg_readcap %s" % sg_device
        AutovalUtils.validate_no_exception(host.run, [cmd], "Run %s" % cmd)

    @staticmethod
    def validate_sg_readcap_output(host, sg_device) -> None:
        AutovalLog.log_info("sg_readcap output validation for device %s" % sg_device)
        cmd = "sg_readcap %s" % sg_device
        op = SgUtils.retry_on_unit_attention(host, cmd)
        match = re.search(r"Last (logical block address|LBA)=(\d+)", op)
        AutovalUtils.validate_condition(
            match is not None,
            # pyre-fixme[16]: Optional type has no attribute `group`.
            "last_blk_addr=%s" % int(match.group(2)),
        )
        match2 = re.search(r"Number of (logical\s)*blocks=(\d+)", op)
        AutovalUtils.validate_condition(
            match2 is not None, "no_of_blocks=%s" % int(match2.group(2))
        )
        match3 = re.search(r"Logical block length=(\d+)", op)
        AutovalUtils.validate_condition(
            match3 is not None, "blk_len=%s" % int(match3.group(1))
        )

    @staticmethod
    def validate_sg_inq(host, sg_device) -> None:
        cmd = "sg_inq %s" % sg_device
        AutovalUtils.validate_no_exception(host.run, [cmd], "Run %s" % cmd)

    @staticmethod
    def validate_sg_inq_output(host, sg_device) -> None:
        AutovalLog.log_info("sg_inq output validation")
        cmd = "sg_inq %s" % sg_device
        op = host.run(cmd)
        vi = re.search(r"Vendor identification:\s(.*)", op)
        AutovalUtils.validate_condition(vi, "Vendor id is valid")
        pi = re.search(r"Product identification:\s(.*)", op)
        AutovalUtils.validate_condition(pi, "Product id is valid")
        prl = re.search(r"Product revision level:\s(.*)", op)
        AutovalUtils.validate_condition(prl, "Product revision is valid")
        usn = re.search(r"Unit serial number:\s(.*)", op)
        AutovalUtils.validate_condition(usn, "serial num is valid")

    @staticmethod
    def validate_sg_luns(host, sg_device) -> None:
        cmd = "sg_luns %s" % sg_device
        AutovalUtils.validate_no_exception(host.run, [cmd], "Run %s" % cmd)

    @staticmethod
    def validate_sdparm_command_capacity(host, sg_device) -> None:
        cmd = "sdparm --command=capacity %s" % sg_device
        AutovalUtils.validate_no_exception(host.run, [cmd], "Run %s" % cmd)

    @staticmethod
    def validate_sdparm_command_capacity_output(host, sg_device) -> None:
        AutovalLog.log_info("sdparm_command_capacity output validation")
        cmd = "sdparm --command=capacity %s" % sg_device
        op = host.run(cmd)
        blocks = re.search(r"blocks:\s(.*)", op)
        AutovalUtils.validate_condition(blocks, "blocks is valid")
        blk_len = re.search(r"block_length:\s(.*)", op)
        AutovalUtils.validate_condition(blk_len, "blk_len is valid")
        capacity_mib = re.search(r"capacity_mib:\s(.*)", op)
        AutovalUtils.validate_condition(capacity_mib, "capacity_mib is valid")

    @staticmethod
    def validate_sdparm_command_ready(host, sg_device) -> None:
        cmd = "sdparm --command=ready %s" % sg_device
        AutovalUtils.validate_no_exception(host.run, [cmd], "Run %s" % cmd)

    @staticmethod
    def validate_sdparm_command_ready_output(host, sg_device) -> None:
        cmd = "sdparm --command=ready %s" % sg_device
        op = host.run(cmd)
        valid = re.search(r"Ready", op)
        AutovalUtils.validate_condition(valid, "sdparm-command-ready output is valid")

    @staticmethod
    def validate_sdparm_command_sense(host, sg_device) -> None:
        cmd = "sdparm --command=sense %s" % sg_device
        AutovalUtils.validate_no_exception(host.run, [cmd], "Run %s" % cmd)

    @staticmethod
    def validate_sdparm_all(host, sg_device) -> None:
        cmd = "sdparm --all %s" % sg_device
        try:
            host.run(cmd)
        except CmdError as e:
            if e.result_obj.return_code != 5:
                raise TestError("Command failed with exception: {}".format(str(e)))
            else:
                AutovalLog.log_info(
                    "Ignoring sdparm exit code 5 failure for command: %s" % cmd
                )
        else:
            AutovalLog.log_info("Command succeeded: %s" % cmd)

    @staticmethod
    def validate_sdparm_inquiry(host, sg_device) -> None:
        cmd = "sdparm --inquiry %s" % sg_device
        AutovalUtils.validate_no_exception(host.run, [cmd], "Run %s" % cmd)

    @staticmethod
    def validate_sg_test_rwbuf(host, sg_device, times: int = 5) -> None:
        buffer_size = SgUtils.get_scsi_device_buffer_size(host, sg_device)
        cmd = "sg_test_rwbuf --size=%d --times=%d --verbose %s" % (
            buffer_size,
            times,
            sg_device,
        )
        AutovalUtils.validate_no_exception(host.run, [cmd], "Run %s" % cmd)

    @staticmethod
    def validate_sg_test_rwbuf_output(host, sg_device, times: int = 5) -> None:
        buffer_size = SgUtils.get_scsi_device_buffer_size(host, sg_device)
        AutovalLog.log_info("sg_test_rwbuf output validation")
        cmd = "sg_test_rwbuf --size=%d --times=%d --verbose %s" % (
            buffer_size,
            times,
            sg_device,
        )
        op = host.run(cmd)
        valid = re.search(r"Success", op)
        AutovalUtils.validate_condition(valid, "Verified the string success")

    @staticmethod
    def validate_sg_verify(host, sg_device) -> None:
        cmd = "sg_verify -c 0x10000 -l 0 -v %s" % sg_device
        AutovalUtils.validate_no_exception(host.run, [cmd], "Run %s" % cmd)

    @staticmethod
    def validate_sg_verify_output(host, sg_device) -> None:
        AutovalLog.log_info("sg_verify output validation")
        cmd = "sg_verify -c 0x10000 -l 0 -v %s" % sg_device
        op = host.run(cmd)
        m1 = re.search(r"Verified", op)
        AutovalUtils.validate_condition(m1, "verified the string Verified")
        m2 = re.search(r"without error", op)
        AutovalUtils.validate_condition(m2, "verified the string withouterror")

    @staticmethod
    def validate_sg_turs(host, sg_device) -> None:
        cmd = "sg_turs -p -v %s" % sg_device
        AutovalUtils.validate_no_exception(host.run, [cmd], "Run %s" % cmd)

    @staticmethod
    def validate_sg_turs_output(host, sg_device) -> None:
        AutovalLog.log_info("sg_turs output validation")
        cmd = "sg_turs -p -v %s" % sg_device
        op = host.run(cmd)
        valid = re.search(r"test unit ready", op)
        AutovalUtils.validate_condition(valid, "Verified the string testunitready")

    @staticmethod
    def test_scsi_command(host, device):
        cmd = "sg_turs %s" % device
        ret = host.run_get_result(cmd, ignore_status=True)
        if ("Not ready to ready change" in ret.stdout) or (ret.return_code == 0):
            return True
        elif ("device not ready" in ret.stdout) or (
            "Ready to not ready change" in ret.stdout
        ):
            return False
        else:
            return None

    @staticmethod
    def sg_requests(host, device):
        sense_data = []
        if SgUtils.test_scsi_command(host, device):
            cmd = "sg_requests %s --hex" % device
            pattern = re.compile(r"\d+\s*(\w*.*)", re.MULTILINE)
            out = SgUtils.retry_on_unit_attention(host, cmd)
            for match in pattern.finditer(out):
                if match:
                    temp = match.group(1)
                    sense_data.extend(temp.split())
        return sense_data

    @staticmethod
    def get_scsi_inquiry(host, device):
        scsi_inquiry = {}
        cmd = "sg_inq %s" % device
        op = SgUtils.retry_on_unit_attention(host, cmd)
        vi = re.search(r"Vendor identification:\s(.*)", op)
        if vi:
            scsi_inquiry["Vendor identification"] = vi.group(1).strip()
            pi = re.search(r"Product identification:\s(.*)", op)
            if pi:
                scsi_inquiry["Product identification"] = pi.group(1).strip()
                prl = re.search(r"Product revision level:\s(.*)", op)
                if prl:
                    scsi_inquiry["Product revision level"] = prl.group(1).strip()
                    usn = re.search(r"Unit serial number:\s(.*)", op)
                    if usn:
                        scsi_inquiry["Unit serial number"] = usn.group(1).strip()
        return scsi_inquiry

    @staticmethod
    def get_sg_supported_diagnostic_pages(host, device):
        """
        Example output of the command:
          wiwynn    BC4U              0e22
          Supported diagnostic pages:
          Supported Diagnostic Pages [sdp] [0x0]
          Configuration (SES) [cf] [0x1]
        """
        out = host.run("sg_ses %s" % (device))
        return out

    @staticmethod
    def get_sg_code_diagnostic_pages(host, device):
        """
        This command geneartes: --page=PG|-p PG
        diagnostic page code (abbreviation or number)
        (def: 'ssp' [0x0] (supported diagnostic pages))
        """
        out = host.run("sg_ses -p sdp %s" % (device))
        return out

    @staticmethod
    def get_sg_configuration_diagnostic_page(host, device):
        """
        The output of the command gives:
        enclosure descriptor list and type descriptor header and text list
        Eg: Element type: Array device slot, subenclosure id: 0
        number of possible elements: 36
        """
        out = host.run("sg_ses -p cf %s" % (device))
        return out

    @staticmethod
    def get_sg_ec_enclosure_status_page(host, device):
        """
        The output of the command gives:Enclosure diagnostic status page.
        Eg: Element type: Enclosure, subenclosure id: 0 [ti=6]
        Overall descriptor: Predicted failure=0, Disabled=0, Swap=0,
        status: Unsupported Ident=0, Time until power cycle=0,
        Failure indication=0 Warning indication=0, Requested power off duration=0
        """
        out = host.run("sg_ses -p ec %s" % (device))
        return out

    @staticmethod
    def get_sg_es_enclosure_status_page(host, device):
        """
        The output of the command gives:Enclosure diagnostic status page.
        Eg: Element type: SAS expander, subenclosure id: 0 [ti=7]
        Overall descriptor:
        Predicted failure=0, Disabled=0, Swap=0, status: Unsupported
        Ident=0, Fail=0
        """
        out = host.run("sg_ses -p es %s" % (device))
        return out

    @staticmethod
    def get_sg_threshold_dignostic_page(host, device):
        """
        The output of the command gives:Threshold diagnostic status page.
        Element type: Current sensor, subenclosure id: 0 [ti=5]
        Overall descriptor:
        high critical=0.0 %, high warning=0.0 % (above nominal current)
        """
        out = host.run("sg_ses -p th %s" % (device))
        return out

    @staticmethod
    def get_sg_element_dignostic_page(host, device):
        """
        The output of the command gives:element diagnostic status page.
        Element index: 143  eiioe=0
        Transport protocol: SAS
        number of phys: 48 SAS address: 0x570e28404769e0ff
        Attached connector; other_element pairs:
          [0] connector ei: 28; other ei: 28
          [1] connector ei: 29; other ei: 29
        """
        out = host.run("sg_ses -p aes %s" % (device))
        return out

    @staticmethod
    def get_sg_microcode_diagnostic_page(host, device):
        """
        The output of the command gives:Download microcode diagnostic status page.
        Eg: Download microcode status diagnostic page:
        number of secondary subenclosures: 0
        generation code: 0x0
        """
        out = host.run("sg_ses -p dm %s" % (device))
        return out

    @staticmethod
    def get_sg_element_descriptor_page(host, device):
        """
        The output of the command gives:Element descriptor diagnostic page.
        Eg: Element type: Current sensor, subenclosure id: 0 [ti=5]
        Overall descriptor: CurrentSensorsInSubEnclsr0
        Element 0 descriptor: SCC_HSC_Current
        """
        out = host.run("sg_ses -p ed %s" % (device))
        return out

    @staticmethod
    def get_scsi_device_buffer_size(host, sg_device) -> int:
        """
        Buffer size provided by `sg_test_rwbuf --quick` does not always work
        for `sg_test_rwbuf --size`. Limit buffer size to 4096 bytes as a work
        around
        """
        max_buffer_size = 4096  # in bytes
        cmd = "sg_test_rwbuf --quick %s" % sg_device
        output = host.run(cmd)
        match = re.search(r"buffer\sof\s(\d+)\sbytes", output)
        if match:
            buffer_size = int(match.group(1))
        else:
            raise TestError("Fail to get buffer size of SCSI device: %s" % (sg_device))
        if buffer_size < max_buffer_size:
            return buffer_size
        else:
            return max_buffer_size

    @staticmethod
    def get_all_sg_map_devices(host):
        """
        Example Output of command "sg_map -i -x":
        /dev/sg6  6 0 531 0  0  ATA       <vendor_name>  <model_id>  W233
        /dev/sg7  6 0 532 0  13  wiwynn   <vendor_name>  <model_id>  0e20
        """
        cmd = "sg_map -i -x"
        out = host.run(cmd)
        return out

    @staticmethod
    def get_sg_log_pages(host, device, page):
        logs = {}
        cmd = "sg_logs %s --page=%s" % (device, page)
        out = SgUtils.retry_on_unit_attention(host, cmd)
        op = out.split("Logical position of first")[0]
        split = [item.split(",") for item in op.split("\n")]
        output_list = list(itertools.chain.from_iterable(split))
        logs.update(SgUtils._parse_sg_logs(r"^\s*(\w*.*)=\s*(\w*.*)", output_list))
        logs.update(SgUtils._parse_sg_logs(r"^\s*(\w*.*):\s*(\w*.*)", output_list))
        sense_data = []
        pattern = re.compile(r"(\d{2})+\s+(\w*.*)", re.MULTILINE)
        for match in pattern.finditer(out):
            if match:
                temp = match.group(2)
                sense_data.extend(temp.split())
                logs["sense_data"] = " ".join(sense_data)
        return logs

    @staticmethod
    def _parse_sg_logs(pattern, op):
        logs = {}
        for line in op:
            m = re.search(pattern, line)
            if m and m.group(2).strip():
                logs[m.group(1).strip()] = m.group(2).strip()
        return logs

    @staticmethod
    def drive_error_injection(host, device, error_type: str = "uncorrectable") -> None:
        """
        This function performs drive error injection on a single device.
        """
        if error_type == "uncorrectable":
            flag = "--wr_uncor"
        else:
            flag = "--cor_dis"
        host.run(f"sg_write_same -i /dev/zero -n 1 -x 4096 -l 0 /dev/{device}")
        ret = host.run_get_result(f"sg_read bs=4096 count=1 if=/dev/{device}")
        AutovalUtils.validate_condition(
            ret.return_code == 0, f"Write and read successfull on /dev/{device}"
        )
        # Inject error
        AutovalLog.log_info(
            f"Running HDD {error_type} error injection on /dev/{device}"
        )
        host.run(f"sg_write_long {flag} /dev/{device} -x 4096 -l 0")
        # Validate injection
        ret = host.run_get_result(
            f"sg_read bs=4096 count=1 if=/dev/{device}",
            ignore_status=True,
        )
        AutovalUtils.validate_condition(ret.return_code, "Failure Expected in sg_read")
        # Clear injection
        AutovalLog.log_info(f"Clear the error on /dev/{device}")
        host.run(cmd=f"dd if=/dev/zero of=/dev/{device} bs=4096 count=10 seek=0")
        host.run(f"sg_write_same -i /dev/zero -n 1 -x 4096 -l 0 /dev/{device}")
        ret = host.run_get_result(f"sg_read bs=4096 count=1 if=/dev/{device}")
        AutovalUtils.validate_condition(
            ret.return_code == 0, f"Error_injection completed on /dev/{device}"
        )
