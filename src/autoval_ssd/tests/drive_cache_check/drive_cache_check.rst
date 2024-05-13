=========================
Drive Cache Check
=========================
* **Test Module** - drive_cache_check.drive_cache_check
* **Test Control file** - Control file differs based on the drive type, power trigger and file system used to run the drive cache check.
  - *all drives without power trigger and no file system - /autoval_ssd/tests/drive_cache_check/drive_cache_check.json*
  - *all drives with power and no file system - /autoval_ssd/tests/drive_cache_check/drive_cache_check_warm.json*
  - *all drives without power trigger and include file system - /autoval_ssd/tests/drive_cache_check/drive_cache_check_with_fs.json*
  - *all drives with power trigger of warm cycle and include file system - /autoval_ssd/tests/drive_cache_check/drive_cache_check_with_fs_warm.json*
  - *all drives without power trigger and ext4 file system - /autoval_ssd/tests/drive_cache_check/drive_cache_check_with_fs_ext4.json*
  - *all drives with power trigger of warm cycle and ext4 file system - /autoval_ssd/tests/drive_cache_check/drive_cache_check_with_fs_ext4_warm.json*
  - *only boot drive without power trigger - /autoval_ssd/tests/drive_cache_check/drive_cache_check_boot.json*
  - *only boot drive with power trigger of warm cycle - /autoval_ssd/tests/drive_cache_check/drive_cache_check_boot_warm.json*

----------------
Test Description
----------------
**This test validates the performance of the SSD during a fio operation by disabling and enabling the internal volatile write cache and then comparing the results.**

---------------------------------------------------------
Test execution and steps involved
---------------------------------------------------------
* Validate the drives which are supporting the cache features by using the below command.
  - cmd: nvme get-feature /dev/<block_name> -f 0x6
* Enable the write cache and execute the write fio job along with the power trigger is passed from the input parameter json file.
  - cmd: nvme set-feature /dev/<block_name> -f 0x6 -v 1
* Disable the write cache and execute the write fio job along with the power trigger is passed from the input parameter json file.
  - cmd: nvme set-feature /dev/<block_name> -f 0x6 -v 0
* Validate is there any error present the output files.
* Compare the iops values.
