===============
Nvme Format Test
===============
This test runs Fio on SSD drives, performs NVME formatting on mounted drives, and verifies the 0x00 pattern on drives by running FIO verify.

* **Test Module** - nvme_format.nvme_format

* **Test Control file**
-------------
* `control_nvme_crypto_erase`: Control file for NVMe crypto erase test.
* `no_secure_erase`: Control file for formatting without secure erase.
* `sanity_check`: Control file for sanity checking the test environment.
* `user_data_erase`: Control file for erasing user data from the drives.
* `control_nvme`: Control file for controlling NVMe operations.

---------------
Test Description:
---------------

The NVMe format test case is designed to evaluate the drive's capability of being securely erased and formatted.
This is achieved by utilizing three distinct options for erasing data on the drive:

No secure erase option - This choice will only format the drive without implementing
any additional security measures.
User Data Erase - This choice is used for formatting the drive with option 2 for user data erase,
without implementing additional security measures.
Cryptographic Erase - This choice removes all user data from the drive and also implements
additional security measures to guarantee that the data is completely unrecoverable.

By testing these various options, the test case can help confirm that the drive is able to be securely formatted and meets the required security standards for use in a business setting.
---------------------------------------------------------
Test execution and steps involved
---------------------------------------------------------

* In the storage_test_setup method, the host dictionary and mount point are set up.
 Then, the execute method is called, which performs the following steps:
* If test drives are available, they are used; otherwise, Fio installation is checked and performed if necessary.
* For each format cycle, secure erase options are iterated upon.
If the secure erase option is 2 (crypto erase), the script checks whether all drives support crypto erase; if not, this option is skipped for the current cycle.
* Previous Fio sessions are cleaned up.
* Fio starts the test.
* Drives are formatted in parallel using the format_nvme function, which takes care of
formatting namespaces for each drive.
* After formatting, the verify_pattern function is called to check if the pattern on the drives is 0x00.
* Additional functions included in the script are:
* check_crypto_erase_support: Checks whether all test drives support crypto erase.
* format_nvme: Formats an NVMe drive based on the provided secure erase option, file system type, and block name. It also verifies the pattern on the drive after formatting.
* _format_nvme: A private function to format the NVMe drive with the given secure erase option, file system type, and device. It also verifies the pattern on the drive after formatting.
* _mount_drive: Mounts the drive with the specified file system type.
* _verify_pattern: Verifies the pattern on the drive.
* get_test_params: Returns a string containing the test parameters for this run.
