=========================
Fio Internal Flush
=========================
* **Test Module** - fio_intenal_flush.fio_internal_flush
* **Test Control file** - Control file differs based on the drive type, file system, cycle count used to run the fio internal flush.

----------------
Test Description
----------------
**The primary purpose of this test case is to maintain data integrity by guaranteeing that all cached data is committed to non-volatile memory before any potential power loss events or system shutdowns occur. This is particularly important for SSDs that use write caching to improve performance because it reduces the risk of data loss or corruption due to incomplete writes in case of unexpected power interruptions.**

---------------------------------------------------------
Test execution and steps involved
---------------------------------------------------------
* Write the data into the drives using basic_write.fio job file
* Do the nvme flush using the below command.

  EX:
  nvme flush dev/nvme0n1
* Do the cycle operation.
* Do the fio read using basic_read.fio job file
* Do the verify using the basic_verify.fio job file
