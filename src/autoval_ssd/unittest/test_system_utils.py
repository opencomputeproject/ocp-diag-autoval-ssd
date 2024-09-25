# pyre-unsafe
from unittest import mock, TestCase
from unittest.mock import Mock

from autoval.lib.connection.connection_utils import CmdResult
from autoval.lib.utils.autoval_exceptions import (
    CmdError,
    SystemInfoException,
    TestError,
)
from autoval.lib.utils.site_utils import SiteUtils
from autoval_ssd.lib.utils.system_utils import (
    get_acpi_interrupt,
    get_serial_number,
    match_in_dmidecode,
    parse_dmidecode_output,
    SystemUtils,
)
from autoval_ssd.unittest.mock.lib.mock_host import MockHost

CMD_MAP = [
    {"cmd": None, "file": None},
    {"cmd": "rpm --query bash", "result": "bash-5.1.8-6.1.hs+fb.el9.x86_64"},
    {"cmd": "rpm --query bash --info", "file": "rpm_qi_bash"},
    {
        "cmd": "rpm --query /tmp/agfhc-1.5.2-centos9.el9.noarch.rpm --package --info",
        "file": "rpm_qpi_agfhc_rpm",
    },
]


class SystemUtilsUnitTest(TestCase):
    def setUp(self) -> None:
        self.mock_host = MockHost(CMD_MAP)
        self.log = ""

    def mock_log(self, log):
        """Alternative method for AutovalLog.log_info"""
        self.log += log

    @mock.patch.object(MockHost, "run_get_result")
    def test_get_pkg_mgr(self, mock_run):
        """Unittest for get_pkg_mgr."""
        yum_cmd = "which yum"
        dnf_cmd = "which dnf"
        # Valid case
        # in case yum is available and not dnf
        valid_result = [
            CmdResult(yum_cmd, "", "", 0, 1),
            CmdResult(dnf_cmd, "", "", 1, 1),
        ]
        mock_run.side_effect = valid_result
        out = SystemUtils.get_pkg_mgr(self.mock_host)
        self.assertEqual(out, "yum")
        # in case dnf is available and not yum
        valid_result = [
            CmdResult(yum_cmd, "", "", 1, 1),
            CmdResult(dnf_cmd, "", "", 0, 1),
        ]
        mock_run.side_effect = valid_result
        out = SystemUtils.get_pkg_mgr(self.mock_host)
        self.assertEqual(out, "dnf")
        # Invalid case
        # in case both are not available
        invalid_result = [
            CmdResult(yum_cmd, "", "", 1, 1),
            CmdResult(dnf_cmd, "", "", 1, 1),
        ]
        mock_run.side_effect = invalid_result
        with self.assertRaises(TestError) as exp:
            SystemUtils.get_pkg_mgr(self.mock_host)
        self.assertEqual(
            str(exp.exception),
            "[AUTOVAL TEST ERROR] Unable to find installed"
            " package manager ['yum', 'dnf']",
        )

    @mock.patch.object(SiteUtils, "get_site_yum_repo_name")
    @mock.patch.object(SystemUtils, "get_pkg_mgr", autospec=True)
    @mock.patch.object(SystemUtils, "get_rpm_info", autospec=True)
    def test_install_rpms(self, mock_get_rpm_info, mock_get_pkg, mock_pkgmgr):
        """Unittest for install_rpms."""
        mock_rpm_list = ["mock_rpm"]
        mock_get_pkg.return_value = "yum"

        # Tool path: True
        self.mock_host.run_get_result = mock.Mock(
            return_value=CmdResult(
                command="", stdout="success", stderr="", return_code=0, duration=100
            )
        )
        self.mock_host.deploy_tool = mock.Mock(return_value="mock_rpm")
        self.mock_host.is_container = False
        SystemUtils.install_rpms(
            self.mock_host,
            mock_rpm_list,
            from_autoval_tool_path=True,
            force_install=True,
        )
        self.mock_host.run_get_result.assert_called_once_with(
            cmd="sudo rpm -i --force mock_rpm",
            ignore_status=True,
        )
        # general exception
        # self.mock_host.run = mock.Mock(side_effect=Exception("No rpm found"))
        self.mock_host.run_get_result = mock.Mock(
            return_value=CmdResult(
                command="",
                stdout="",
                stderr="Unable to find a match",
                return_code=1,
                duration=100,
            )
        )
        with self.assertRaises(TestError) as e:
            SystemUtils.install_rpms(
                self.mock_host,
                mock_rpm_list,
                from_autoval_tool_path=True,
                force_install=True,
            )
        self.assertIn(
            "Failed to install rpm mock_rpm, Reason: Unable to find a match",
            str(e.exception),
        )
        self.mock_host.run_get_result = mock.Mock(
            return_value=CmdResult(
                command="",
                stdout="",
                stderr="Some error occurred",
                return_code=1,
                duration=100,
            )
        )
        with self.assertRaises(TestError) as e:
            SystemUtils.install_rpms(
                self.mock_host,
                mock_rpm_list,
                from_autoval_tool_path=True,
                force_install=True,
            )
            self.assertIn(
                "Failed to install rpm mock_rpm, Reason: Some error occurred",
                str(e.exception),
            )
        # Tool path: False
        self.mock_host.run_get_result = mock.Mock(
            return_value=CmdResult(
                command="", stdout="", stderr="", return_code=0, duration=100
            )
        )
        mock_pkgmgr.return_value = "mock_repo"
        SystemUtils.install_rpms(self.mock_host, mock_rpm_list, force_install=True)
        self.mock_host.run_get_result.assert_called_once_with(
            cmd="sudo yum -y --disablerepo=\\* --enablerepo=mock_repo install mock_rpm",
            ignore_status=True,
        )

    @mock.patch.object(SystemUtils, "get_pkg_mgr", autospec=True)
    def test_uninstall_rpms(self, mock_get_pkg):
        """Unittest for uninstall_rpms."""
        mock_get_pkg.return_value = "yum"
        mock_rpm_list = ["mock_rpm"]
        SystemUtils.uninstall_rpms(self.mock_host, mock_rpm_list)

    def test_get_current_date_time(self) -> None:
        """Unit test for getting curent date and time"""
        out = SystemUtils.get_current_date_time()
        self.assertTrue(out)

    def test_get_rpm_info(self):
        """Unittest for get_rpm_info."""
        mock_rpm_info = mock.create_autospec(
            SystemUtils.get_rpm_info, return_value="pass"
        )
        mock_rpm = "mock_rpm"
        out = mock_rpm_info(self.mock_host, mock_rpm)
        mock_rpm_info.assert_called_once_with(self.mock_host, mock_rpm)
        self.assertEqual(out, "pass")
        with self.assertRaises(Exception) as exp:
            mock_rpm_info("")
        self.assertIn("missing a required argument", str(exp.exception))

    def test_get_rpm_info_installed_pkg_simple(self):
        """
        Unittest for get_rpm_info.
        Querying for installed package, field=None.
        Must return full package name.
        """
        out = SystemUtils.get_rpm_info(self.mock_host, "bash")
        self.assertEqual(out, "bash-5.1.8-6.1.hs+fb.el9.x86_64")

    def test_get_rpm_info_pkg_not_installed(self):
        """
        Unittest for get_rpm_info.
        Querying for missing package, field=None.
        Must return rpm response saying that package is not installed.
        """
        result_obj = CmdResult(
            command="rpm --query not_installed",
            stdout="package not_installed is not installed",
            stderr="",
            return_code=1,
            duration=1.0,
        )
        cmd_err = CmdError(
            command="rpm --query not_installed",
            result_obj=result_obj,
        )
        self.mock_host.run = Mock(side_effect=cmd_err)
        self.assertIn(
            "package not_installed is not installed",
            SystemUtils.get_rpm_info(self.mock_host, "not_installed"),
        )

    def test_get_rpm_info_installed_pkg_version(self):
        """
        Unittest for get_rpm_info.
        Querying for installed package, field="version".
        Must return package version.
        """
        out = SystemUtils.get_rpm_info(self.mock_host, "bash", field="version")
        self.assertEqual(out, "5.0.11")

    def test_get_rpm_info_custom_rpm_file_version(self):
        """
        Unittest for get_rpm_info.
        Querying custom RPM package, field="version".
        Must return package version.
        """
        out = SystemUtils.get_rpm_info(
            self.mock_host,
            "/tmp/agfhc-1.5.2-centos9.el9.noarch.rpm",
            field="build date",
        )
        self.assertEqual(out, "Fri 16 Feb 2024 08:16:57 AM PST")

    def test_update_permission(self):
        """Unittest for get_rpm_info."""
        mock_update_perm = mock.create_autospec(
            SystemUtils.update_permission, return_value="pass"
        )
        out = mock_update_perm(self.mock_host, "mock_permission", "mock_file_name")
        mock_update_perm.assert_called_once_with(
            self.mock_host, "mock_permission", "mock_file_name"
        )
        self.assertEqual(out, "pass")
        with self.assertRaises(Exception) as exp:
            mock_update_perm("")
        self.assertIn("missing a required argument", str(exp.exception))

    @mock.patch.object(MockHost, "run_get_result")
    def test_get_pip_info_positive_case(self, mock_run):
        mock_run.return_value = CmdResult(
            command="ls",
            stdout="details dummy_pip_info ",
            stderr="",
            return_code=0,
            duration=1.0,
        )
        out = SystemUtils.get_pip_info(self.mock_host, "dummy_pip_packg")
        self.assertEqual(out, "dummy_pip_info")

    @mock.patch.object(MockHost, "run_get_result")
    def test_get_pip_info_negative_case(self, mock_run):
        mock_run.return_value = CmdResult(
            command="ls",
            stdout="bancsi",
            stderr="",
            return_code=1,
            duration=1.0,
        )
        out = SystemUtils.get_pip_info(self.mock_host, "dummy_pip_packg")
        self.assertEqual(out, None)


class SUUnitTest(TestCase):
    dmidecode_output = (
        "Getting SMBIOS data from sysfs.\n"
        "SMBIOS 3.0.0 present.\n"
        "\n"
        "Handle 0x0069, DMI type 9, 17 bytes\n"
        "System Slot Information\n"
        "        Designation: OCP_MEZZ_CONN\n"
        "        Type: x16 Proprietary\n"
        "        Current Usage: In Use\n"
        "        Length: Short\n"
        "        Characteristics:\n"
        "                3.3 V is provided\n"
        "                PME signal is supported\n"
        "                SMBus signal is supported\n"
        "        Bus Address: 0000:5d:00.0\n"
        "\n"
        "Handle 0x006A, DMI type 9, 17 bytes\n"
        "System Slot Information\n"
        "        Designation: PCIE_SLOT2\n"
        "        Type: x16 PCI Express 3 x16\n"
        "        Current Usage: In Use\n"
        "        Length: Long\n"
        "        ID: 2\n"
        "        Characteristics:\n"
        "                3.3 V is provided\n"
        "                PME signal is supported\n"
        "                SMBus signal is supported\n"
        "        Bus Address: 0000:17:02.0\n"
        "\n"
        "Handle 0x0001, DMI type 1, 27 bytes\n"
        "System Information\n"
        "        Manufacturer: OCP\n"
        "        Product Name: Autoval_OSS 29F0EMA0160\n"
        "        Version: OSS456\n"
        "        Serial Number: QCFF0ES205200F7\n"
        "        UUID: 000e1333-fdc0-1fb1-4292-595804500503\n"
        "        Wake-up Type: Reserved\n"
        "        SKU Number: Default string\n"
        "        Family: Family\n"
        "\n"
    )
    mock_output = [
        {"dmi_type": "9", "no_of_bytes": "17", "handle": "0x0069"},
        {"dmi_type": "9", "no_of_bytes": "17", "handle": "0x006A"},
        {"dmi_type": "1", "no_of_bytes": "27", "handle": "0x0001"},
    ]

    def setUp(self) -> None:
        self.mock_host = MockHost(CMD_MAP)

    def test_parse_dmidecode_output(self):
        """Unittest for parse_dmidecode_output."""
        out = parse_dmidecode_output(self.dmidecode_output)
        self.assertListEqual(out, self.mock_output)
        out = parse_dmidecode_output("")
        self.assertListEqual(out, [])

    @mock.patch(
        "autoval_ssd.lib.utils.system_utils.parse_dmidecode_output",
        autospec=True,
    )
    def test_match_in_dmidecode(self, mock_parse):
        """Unittest for match_in_dmidecode."""
        mock_parse.return_value = self.mock_output
        out = match_in_dmidecode("slot", self.mock_host)
        self.assertListEqual(out, mock_parse.return_value)
        # Exception scenario
        with self.assertRaises(SystemInfoException) as exp:
            match_in_dmidecode("lot", self.mock_host)
        self.assertEqual(
            str(exp.exception),
            "[SYSTEM INFO ERROR] match_in_dmidecode: Invalid type",
        )

    @mock.patch("autoval_ssd.lib.utils.system_utils.match_in_dmidecode", autospec=True)
    def test_get_serial_number(self, mock_match):
        """Unittest for get_serial_number."""
        mock_match.return_value = [
            {"Bus_Address": "0000:17:02.0", "Serial_Number": "mock_serial_no01"}
        ]
        out = get_serial_number("slot", self.mock_host)
        self.assertEqual(out, "mock_serial_no01")
        mock_match.return_value = [{"Bus_Address": "0000:17:02.0"}]
        with self.assertRaises(Exception) as exp:
            get_serial_number("slot", self.mock_host)
        self.assertEqual(str(exp.exception), "No Serial number found in dmidecode")

    @mock.patch.object(MockHost, "run")
    def test_get_acpi_interrupt(self, mock_run):
        """Unit test for get_acpi_interrupt."""
        valid_output = "9:  27   0   0   0   IR-IO-APIC-fasteoi   acpi"
        mock_run.return_value = valid_output
        out = get_acpi_interrupt(self.mock_host)
        self.assertDictEqual(
            out,
            {
                "0": "9:",
                "1": "27",
                "2": "0",
                "3": "0",
                "4": "0",
                "5": "IR-IO-APIC-fasteoi",
                "6": "acpi",
            },
        )
        # Exception scenario
        invalid_output = "9:  270000   0   0   0   IR-IO-APIC-fasteoi   acpi"
        mock_run.side_effect = [valid_output, invalid_output]
        with self.assertRaises(SystemInfoException) as exp:
            get_acpi_interrupt(self.mock_host)
        self.assertEqual(
            str(exp.exception),
            "[SYSTEM INFO ERROR] larger acpi interrupts hit 269973",
        )
