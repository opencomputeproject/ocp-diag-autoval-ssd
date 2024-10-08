## Overview
This document will be going over some high level descriptions and explanations required for Autoval development in the SSD repository.

They include:
1. NVMe Hierarchy
2. StorageTestBase
3. SSD Utilities
4. Running SSD Tests

## NVMe Hierarchy
The NVMe (Non-Volatile Memory Express) drives are high-speed storage devices connected through the PCIe (Peripheral Component Interconnect Express) interface. It provides a high-performance and low-latency interface for storage devices such as SSDs (Solid-State Drives).

The NVMe hierarchy refers to the structure and organization of how NVMe devices are managed and interacted within software frameworks or repositories. This form of hierarchy helps to efficiently manage the NVMe drives.

The hierarchy consists of three levels:
1. Namespace
2. Controller
3. Device

### Namespace
A namespace represents a logical partition of the storage device. Each namespace can have its own set of attributes like size, capacity, and performance characteristics.

### Controller
A controller is responsible for managing one or more namespaces. It handles commands from the host, manages the flow of data between the host and the namespaces, and performs tasks such as error recovery and wear leveling.

### Device
The device is the physical NVMe storage device that contains one or more controllers and namespaces.

## StorageTestBase
The StorageTestBase is a base class that inherits from TestBase. It was created to test storage drives. It creates drive objects and then compares and validates drive metrics at the end of the test. When inheriting from this class, the user can choose to override the following functions from the StorageTestBase.

### setup()
The StorageTestBase first runs through the setup from the TestBase which it has inherited and then constructs the environment to do the following:

If you have other test-specific setup required, override this method and call super().setup(*args, **kwargs) in your own setup method.

### execute()
While this is part of the TestBase class, users are expected to override this method with the logic they want to run in order to test the drives.

### cleanup()
The cleanup method goes through the StorageTestBase-specific deconstruction before carrying out TestBase deconstruction. When overriding this method, be sure to call super().cleanup(*args, **kwargs) at the very end of the line.

```
def cleanup(self, *args, **kwargs):
	...
	super().cleanup(*args, **kwargs)
```

## SSD Utilities
There are multiple test utilities used by drive-specific tests developed in Autoval OSS SSD. The following will be briefly described and will contain links to the in-line documentations.

### Disk utils
This module provides utility functions for working with disks on Linux systems. It allows you to run commands to manage and monitor disks, including setting and getting disk parameters, and performing operations such as partitioning and formatting disks.
[Link to in-line documentation](https://github.com/opencomputeproject/ocp-diag-autoval-ssd/blob/main/src/autoval_ssd/lib/utils/disk_utils.py)

### Filesystem utils
This module provides utility functions for working with file systems on Linux systems. It allows you to run commands to manage and monitor file systems, including setting and getting file system parameters, and performing operations such as formatting and mounting file systems.
[Link to in-line documentation](https://github.com/opencomputeproject/ocp-diag-autoval-ssd/blob/main/src/autoval_ssd/lib/utils/filesystem_utils.py)

### FIO runner
This module provides utility functions for running FIO (Flexible I/O Tester) jobs on Linux systems. It allows you to run commands to manage and monitor FIO jobs, including setting and getting job parameters, and performing operations such as starting and stopping jobs.
[Link to in-line documentation](https://github.com/opencomputeproject/ocp-diag-autoval-ssd/blob/main/src/autoval_ssd/lib/utils/fio_runner.py)

### hdparm utils
This module provides utility functions for working with hard disk drives on Linux systems using the hdparm command. It allows you to run commands to manage and monitor hard disk drives, including setting and getting device parameters, and performing operations such as secure erase and drive locking.
[Link to in-line documentation](https://github.com/opencomputeproject/ocp-diag-autoval-ssd/blob/main/src/autoval_ssd/lib/utils/hdparm_utils.py)

### LSI utils
This module provides utility functions for working with LSI (Luminous Storage Interface) devices on Linux systems. It allows you to run commands to manage and monitor LSI devices, including setting and getting device parameters, and performing operations such as firmware updates.
[Link to in-line documentation](https://github.com/opencomputeproject/ocp-diag-autoval-ssd/blob/main/src/autoval_ssd/lib/utils/lsi_utils.py)

### MD utils
This module provides utility functions for working with MD (Multiple Devices) RAID (Redundant Array of Independent Disks) arrays on Linux systems. It allows you to run commands to create, manage, and monitor MD arrays, as well as perform operations such as adding or removing devices from an array.
[Link to in-line documentation](https://github.com/opencomputeproject/ocp-diag-autoval-ssd/blob/main/src/autoval_ssd/lib/utils/md_utils.py)

### PCI utils
This module provides utility functions for working with PCI (Peripheral Component Interconnect) devices on Linux systems. It allows you to run commands to scan for PCI devices, get device information, and manage device settings.
[Link to in-line documentation](https://github.com/opencomputeproject/ocp-diag-autoval-ssd/blob/main/src/autoval_ssd/lib/utils/pci_utils.py)

### scrtnycli utils
This module provides utility functions for controlling ownership and querying output of NVMe drives on Linux systems using scrtnycli. It allows you to run commands to manage drive security, such as setting and getting passwords, and performing secure erase operations.
[Link to in-line documentation](https://github.com/opencomputeproject/ocp-diag-autoval-ssd/blob/main/src/autoval_ssd/lib/utils/scrtnycli_utils.py)

### sdparm utils
This module provides utility functions for controlling ownership and querying output of SCSI (Small Computer System Interface) devices on Linux systems using sdparm. It allows you to run commands to set and get device parameters, such as write cache and security settings.
[Link to in-line documentation](https://github.com/opencomputeproject/ocp-diag-autoval-ssd/blob/main/src/autoval_ssd/lib/utils/sdparm_utils.py)

### sed util
This module provides utility functions for controlling ownership and querying output of Self-Encrypting Drives (SEDs) on Linux systems using sed-util or sedutil-cli. It allows you to run commands to scan for Opal supported drives, check status, and get MSID (Master Security ID)
[Link to in-line documentation](https://github.com/opencomputeproject/ocp-diag-autoval-ssd/blob/main/src/autoval_ssd/lib/utils/sed_util.py)

### SG utils
This module provides utility functions for controlling ownership and querying output of SG (SCSI Generic) devices on Linux systems using sg3_utils. It allows you to run commands to scan for SG devices, check status, and get device information.
[Link to in-line documentation](https://github.com/opencomputeproject/ocp-diag-autoval-ssd/blob/main/src/autoval_ssd/lib/utils/sg_utils.py)

### System utils
This module provides a collection of static methods for performing various system-related tasks, such as managing packages, retrieving system information, and updating file permissions. Additionally, there are standalone functions for working with ACPI (Advanced Configuration and Power Interface) interrupts, parsing dmidecode output, and retrieving the host's serial number.
[Link to in-line documentation](https://github.com/opencomputeproject/ocp-diag-autoval-ssd/blob/main/src/autoval_ssd/lib/utils/system_utils.py)

## Running SSD tests
To help you guide through how to run SSD tests in this repository, I will be showcasing how to run one of the tests we have.

Let’s say that we are planning on using the nvme_ns_resize test and op_pct_sweep_control.json as the test control. Before running the test, you have to configure the site settings and the host. In order to do so, you will have to create two separate json files.

```markdown
```json
{
    "control_server_logdir": "/autoval/logs/",
    "control_server_tmpdir": "/tmp/autoval/",
    "dut_logdir": "/autoval/logs/",
    "dut_tmpdir": "/tmp/autoval/",
    "resultsdir": "/autoval/results/",
    "ssh_key_path": ["/USERNAME/.ssh/id_rsa"],
    "plugin_config_path" : "plugins/plugin_config.json",
    "repository_dir": "/autoval/repository/",
    "test_utils_plugin_config_path" : "plugins/test_utils_plugin_config.json",
    "cleanup_dut_logdirs" : false,
    "yum_repo": "autoval_tools"
}
```

* **control_server_logdir**: the directory where logs from the control server will be stored
* **control_server_tmpdir**: the directory where temporary files from the control server will be stored
* **dut_logdir**: the directory where the logs from the DUTs will be stored
* **resultsdir**: the directory where test results will be stored
* **ssh_key_path**: the path to the SSH key used to connect to the DUT
* **plugin_config_path**: the path to the plugin configuration file
* **repository_dir**: the directory where the Autoval repository is located
* **test_utils_plugin_config_path**: the path to the test utils plugin configuration file
* **cleanup_dut_logdirs**: a boolean value that decides whether to cleanup logdirs from DUT during the cleanup phase after running the test
* **yum_repo**: a custom repository for hosting RPMs (Red Hat Package Managers) used by the tests in autoval SSD repository

In order to make use of the yum repository, follow this guide to install yum repository: https://www.redhat.com/sysadmin/add-yum-repository

After creating the site_settings.json, take note of the file path and use it to run the export command in the command line.

```markdown
```bash
export SITE_SETTINGS = /path/to/site_settings.json
```

Then, for the host configuration, you can use the below structure.

```markdown
```json
{
    "hosts": [
        {
            "hostname": "10::CD97:E10F:FE82:9A1C",
            "username": "root",
            "password": "password",
            "oob_addr": "10::CD97:E10F:FE82:9A19",
            "oob_username": "root",
            "oob_password": "password"
        }
    ]
}
```

Take note of the file path of the host.json.

Then, we have to find out the structure to refer to the nvme_ns_resize test from the repository. This is because the autoval test runner expects a certain format for the autoval SSD test file to be referenced.

Currently, the test resides inside the nvme_ns_resize folder which is located with the rest of the tests in the tests folder. When calling the test through the autoval_test_runner, we have to refer to it as nvme_ns_resize.nvme_ns_resize. This follows the <test_folder>.<test_name> structure needed for the autoval test runner.

Now that we have done the pre-test command setup, we can run the test in the command line using the following:

```markdown
```bash
python -m autoval.autoval_test_runner nvme_ns_resize.nvme_ns_resize --config /path/to/host.json --test_control ocp-diag-autoval-ssd/src/autoval_ssd/tests/nvme_ns_resize/op_pct_sweep_control.json
```
