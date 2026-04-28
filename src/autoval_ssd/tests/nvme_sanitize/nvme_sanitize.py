#!/usr/bin/env python3

# pyre-strict
import time

from autoval.lib.host.component.component import COMPONENT
from autoval.lib.host.host import Host
from autoval.lib.utils.autoval_errors import ErrorType
from autoval.lib.utils.autoval_thread import AutovalThread
from autoval.lib.utils.autoval_utils import AutovalUtils
from autoval_ssd.lib.utils.fio_runner import FioRunner
from autoval_ssd.lib.utils.host_protocol import HostProtocol
from autoval_ssd.lib.utils.storage.nvme.nvme_drive import NVMeDrive
from autoval_ssd.lib.utils.storage.nvme.nvme_utils import NVMeUtils
from autoval_ssd.lib.utils.storage.storage_test_base import StorageTestBase

SANITIZE_ACTION_MAP = {
    "block_erase": 2,
    "overwrite": 3,
    "crypto_erase": 4,
}


class NvmeSanitize(StorageTestBase):
    """
    NVMe Sanitize Test.
    Validates NVMe sanitize commands (Block Erase, Crypto Erase, Overwrite)
    by writing data to drives, running the sanitize operation, polling
    the sanitize log for completion, and verifying the 0x00 pattern.
    Checks SANICAP for drive support before running each sanitize action.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.sanitize_actions = self.test_control.get(
            "sanitize_actions",
            ["block_erase", "crypto_erase"],
        )
        self.sanitize_cycles = self.test_control.get("sanitize_cycles", 1)
        self.verify_pattern = self.test_control.get("verify_pattern", True)
        self.poll_interval = self.test_control.get("poll_interval", 30)
        self.sanitize_timeout = self.test_control.get("sanitize_timeout", 600)

    # @override
    def storage_test_setup(self) -> None:
        super().storage_test_setup()
        self.host_dict = AutovalUtils.get_host_dict(self.host)

    def execute(self) -> None:
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

        for cycle in range(1, self.sanitize_cycles + 1):
            self.log_info(f"Starting sanitize cycle {cycle}")
            for action in self.sanitize_actions:
                if action not in SANITIZE_ACTION_MAP:
                    self.log_info(f"Unknown sanitize action: {action}, skipping")
                    continue
                if not self.check_sanitize_support(action):
                    self.log_info(
                        f"Skipping {action} for cycle {cycle}"
                        " — not all drives support it"
                    )
                    continue

                self.validate_no_exception(
                    fio.clean_previous_fio_session,
                    [],
                    "Clean up existing fio session",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.TOOL_ERR,
                )
                self.log_info(f"Starting FIO write before {action} sanitize")
                self.validate_no_exception(
                    fio.start_test,
                    [],
                    "Fio start_test()",
                    component=COMPONENT.STORAGE_DRIVE,
                    error_type=ErrorType.TOOL_ERR,
                )

                sanitize_queue = []
                for drive_obj in self.test_drives:
                    self.log_info(f"+++Sanitizing {drive_obj.block_name} with {action}")
                    sanitize_queue.append(
                        AutovalThread.start_autoval_thread(
                            self._sanitize_and_verify,
                            drive_obj,
                            action,
                            drive_obj.block_name,
                            drive_obj.serial_number,
                        )
                    )
                if len(sanitize_queue):
                    AutovalThread.wait_for_autoval_thread(sanitize_queue)

    def check_sanitize_support(self, action: str) -> bool:
        """Check if all test drives support the given sanitize action.

        Args:
            action: Sanitize action name ('block_erase', 'crypto_erase', 'overwrite').

        Returns:
            True if all drives support the action, False otherwise.
        """
        for drive in self.test_drives:
            capabilities = drive.get_sanitize_support_status()
            if capabilities.get(action, False):
                continue
            self.log_info(
                f"{drive.block_name} does not support sanitize action {action}"
            )
            return False
        return True

    def _sanitize_and_verify(
        self, drive_obj: NVMeDrive, action: str, block_name: str, serial_number: str
    ) -> None:
        """Run sanitize on a drive, wait for completion, and verify.

        Args:
            drive_obj: NVMeDrive object.
            action: Sanitize action name ('block_erase', 'crypto_erase', 'overwrite').
            block_name: Block device name.
            serial_number: Drive serial number.
        """
        host = Host(self.host_dict)
        action_code = SANITIZE_ACTION_MAP[action]

        self.validate_no_exception(
            drive_obj.sanitize_drive,
            [action_code],
            f"{action} sanitize on {block_name}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )

        self.validate_no_exception(
            self._wait_for_sanitize_completion,
            [drive_obj],
            f"Wait for {action} sanitize completion on {block_name}",
            component=COMPONENT.STORAGE_DRIVE,
            error_type=ErrorType.NVME_ERR,
        )

        if self.verify_pattern:
            pattern = "0x00"
            nvme_drive = NVMeUtils.get_nvme_ns_map(host, block_name, serial_number)
            for _device, namespaces in nvme_drive.items():
                for ns in namespaces:
                    self.validate_no_exception(
                        self._verify_pattern,
                        [host, ns, pattern],
                        f"{pattern} pattern verification on {ns}",
                        component=COMPONENT.STORAGE_DRIVE,
                        error_type=ErrorType.NVME_ERR,
                    )

    def _wait_for_sanitize_completion(self, drive_obj: NVMeDrive) -> None:
        """Poll the sanitize log until the sanitize operation completes.

        Args:
            drive_obj: NVMe Drive object.

        Raises:
            Exception: If sanitize fails or times out.
        """
        block_name = drive_obj.block_name
        elapsed = 0
        while elapsed < self.sanitize_timeout:
            raw_log = drive_obj.get_sanitize_log()
            sanitize_log = self._unwrap_sanitize_log(raw_log)
            status_code = self._parse_sstat(sanitize_log.get("sstat", {}))

            if status_code == 1:
                self.log_info(f"{block_name}: Sanitize completed successfully")
                return
            elif status_code == 3:
                raise Exception(
                    f"{block_name}: Sanitize operation failed (status_code={status_code})"
                )
            elif status_code == 0:
                raise Exception(
                    f"{block_name}: Sanitize status is 0 (NVM subsystem has never "
                    "been sanitized) after issuing sanitize command. "
                    "The command may not have been accepted."
                )

            time.sleep(self.poll_interval)
            elapsed += self.poll_interval

        raise Exception(
            f"{block_name}: Sanitize timed out after {self.sanitize_timeout}s"
        )

    @staticmethod
    def _unwrap_sanitize_log(raw_log: dict) -> dict:
        """Unwrap sanitize log from controller-name nesting.

        Args:
            raw_log: Raw sanitize log dict. nvme sanitize-log returns JSON
                like {"nvme0": {<actual log>}}; this extracts the inner dict.

        Returns:
            The unwrapped sanitize log dict, or empty dict if input is empty.
        """
        if not raw_log:
            return {}
        for _key, value in raw_log.items():
            if isinstance(value, dict):
                return value
        return raw_log

    @staticmethod
    def _parse_sstat(sstat: int | dict) -> int:
        """Parse sstat field from sanitize log.

        Args:
            sstat: Raw sstat value from the sanitize log. Can be an int
                (raw status value) or a dict with a "status" key.

        Returns:
            The integer status code (lowest 3 bits), or -1 on parse failure.
        """
        if isinstance(sstat, int):
            return sstat & 0x7
        if isinstance(sstat, dict):
            status_str = sstat.get("status", "")
            if status_str.startswith("("):
                try:
                    return int(status_str.split(")")[0].strip("("))
                except (ValueError, IndexError):
                    pass
        return -1

    def _verify_pattern(self, host: HostProtocol, device: str, pattern: str) -> None:
        """Run FIO to verify the drive is filled with the expected pattern.

        Args:
            host: Host object.
            device: Namespace device name (e.g. 'nvme0n1').
            pattern: Expected pattern (e.g. '0x00').
        """
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
        return f"Sanitize actions {self.sanitize_actions} for {self.sanitize_cycles} cycle(s)"
