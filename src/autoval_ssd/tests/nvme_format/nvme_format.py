#!/usr/bin/env python3

# pyre-unsafe
from autoval.lib.host.component.component import COMPONENT
from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval_ssd.lib.utils.filesystem_utils import FilesystemUtils
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase


class NvmeFormat(StorageTestBase):
    """
    Run Fio on SSD drives.
    Does NVME formating on mounted drives
    Verify the 0x00 pattern on drives by running FIO verify
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fstype = self.test_control.get("fstype", "ext4")
        self.secure_erase_option = self.test_control.get("secure_erase_option", [0])
        self.format_cycles = self.test_control.get("format_cycles", 1)
        self.stop_on_error = self.test_control.get("stop_on_error", False)
        self.ignore_smart = self.test_control.get("ignore_smart", False)

    # @override
    def storage_test_setup(self) -> None:
        super().storage_test_setup()
        self.host_dict = AutovalUtils.get_host_dict(self.host)
        self.mnt = "/mnt/havoc"

    def execute(self) -> None:
        # fio job file creation and fio installation on DUT if not installed
        if self.test_drives:
            self.test_control["drives"] = self.test_drives
        if self.boot_drive:
            self.test_control["boot_drive"] = self.boot_drive
        fio = FioRunner(self.host, self.test_control)
        self.validate_no_exception(
            fio.test_setup,
            [],
            "Fio setup()",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.TOOL_ERR,
        )

        for cycle in range(1, self.format_cycles + 1):
            self.log_info("Starting cycle %s " % cycle)
            for ses in self.secure_erase_option:
                if ses == 2:
                    crypto_erase_check = self.check_crypto_erase_support()
                    if crypto_erase_check:
                        self.log_info("Drives support crypto erase,test will continue")
                    else:
                        self.log_info(
                            "Some drives on DUT dont support crypto erase,skipping"
                            " format with SES option {} for cycle {}".format(ses, cycle)
                        )
                        continue
                self.validate_no_exception(
                    fio.clean_previous_fio_session,
                    [],
                    "Clean up existing fio session",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.TOOL_ERR,
                )
                self.log_info("Starting fio with secure erase %s" % ses)
                self.validate_no_exception(
                    fio.start_test,
                    [],
                    "Fio start_test()",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.TOOL_ERR,
                )
                format_queue = []
                # Formating the drives in parallel
                for drive_obj in self.test_drives:
                    self.log_info(f"+++Formatting {drive_obj.block_name}")
                    format_queue.append(
                        AutovalThread.start_autoval_thread(
                            self.format_nvme,
                            drive_obj,
                            ses,
                            drive_obj.block_name,
                            drive_obj.serial_number,
                        )
                    )
                if len(format_queue):
                    AutovalThread.wait_for_autoval_thread(format_queue)

    def check_crypto_erase_support(self):
        """
        check for crypto erase support in the test drives and
        if it is supported in all the drives
        do nvme format with cryto erase secure option
        Returns
        -------
        bool
        """
        support = True
        for drive in self.test_drives:
            out = drive.get_crypto_erase_support_status()
            if not out:
                support = False
                return support
        if support:
            return True

    def format_nvme(
        self, drive_obj, ses: int, block_name: str, serial_number: str
    ) -> None:
        """Format Nvme Drives
        This function would format the device and its respective namespaces.

        Parameters
        ----------
        ses: Integer
            Value of Secure Erase Settings(SES).
        block_name: String
            Block name of the drive on which format has to be performed.
        serial_number: String
            Serial number of the drive on which format has to be performed.
        """
        pattern = "0x00"
        host = Host(self.host_dict)
        nvme_drive = NVMeUtils.get_nvme_ns_map(host, block_name, serial_number)
        for _device, namespaces in nvme_drive.items():
            # formatting the namespaces
            for ns in namespaces:
                self._format_nvme(drive_obj, host, ns, self.fstype, ses)
                self.validate_no_exception(
                    self._verify_pattern,
                    [host, ns, pattern],
                    "%s pattern verification on device %s" % (pattern, ns),
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.NVME_ERR,
                )

    def _format_nvme(
        self,
        drive_obj,
        host: "Host",
        device: str,
        fstype: str,
        secure_erase_option,
        verify: bool = True,
    ) -> None:
        if verify:
            self._mount_drive(device, fstype)

        self.validate_no_exception(
            drive_obj.format_drive,
            [secure_erase_option],
            "NVME Formatting on device %s" % device,
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )
        # Mount must fail, as the FS has been erased by nvme format.
        if verify:
            is_formatted = False
            try:
                mnt = self.mnt + "_" + device
                FilesystemUtils.mount(host, device, mnt, force_mount=False)
            except Exception:
                is_formatted = True
            self.validate_condition(
                is_formatted,
                "Formatting verified on device %s" % device,
                component=COMPONENT.STORAGE_DRIVE,
                error_type=ErrorType.NVME_ERR,
            )

    def _mount_drive(self, device: str, fstype: str) -> None:
        # Make sure to unmount device if it is mounted.
        # Otherwise file system creation will fail.
        mnt = self.mnt + "_" + device
        mount = FilesystemUtils.is_mounted(self.host, mnt)
        if mount:
            FilesystemUtils.unmount(self.host, mnt)
        FilesystemUtils.create_filesystem(self.host, device, fstype, "")
        FilesystemUtils.mount(self.host, device, mnt, force_mount=False)
        df = FilesystemUtils.get_df_info(self.host, device)
        self.validate_condition(
            df["type"] == fstype,
            "Mounted %s at %s" % (device, mnt),
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.SYSTEM_ERR,
        )
        FilesystemUtils.unmount(self.host, mnt)

    def _verify_pattern(self, host: "Host", device: str, pattern: str) -> None:
        cmd = (
            "fio --name=verify --rw=read --verify=pattern --verify_pattern="
            + pattern
            + " --filename=/dev/"
            + device
            + " --time_based --runtime=5m"
            + " --offset=0 --direct=1"
        )
        host.run(cmd, timeout=2400)  # noqa

    def get_test_params(self) -> str:
        params = (
            "Filesystem type {} with secure erase option"
            " {} for format cycle(s) {}".format(
                self.fstype, self.secure_erase_option, self.format_cycles
            )
        )
        return params
