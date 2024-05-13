=========================
Drive MD5 Verify/Data Retention Test
=========================
* **Test Module** - drive_md5_verify.drive_md5_verify
* **Test Control file** - Control file differs based on the drive type, file system, run time and cycle_type used to run the drive md5 veriry.

----------------
Test Description
----------------
**The purpose of the drive_md5_verify test case is to validate the data integrity of storage devices (drives) after a power cycle event. This test ensures that the stored data remains uncorrupted during an unexpected power loss or reboot scenario, which is crucial for mission-critical applications and systems where data consistency and reliability are paramount. By comparing the MD5 checksum values before and after the power cycle, this test helps identify any potential issues with the drive's ability to maintain data integrity under these conditions.**

---------------------------------------------------------
Test execution and steps involved
---------------------------------------------------------
* Check if the drive is a filesystem type; if so, create a file on the mounted drive, otherwise, write directly to the device.
* Perform an FIO write operation on the specified drives.
* Calculate the MD5 checksum value for the written data.
* Perform a power cycle (reboot) of the DUT (Device Under Test).
* After the DUT boots back up, calculate the MD5 checksum value again for the written data.
* Compare the pre- and post-reboot MD5 checksum values to ensure they match. If they don't, it indicates data corruption due to the power cycle event.
* Clean up by unmounting any mounted directories.
