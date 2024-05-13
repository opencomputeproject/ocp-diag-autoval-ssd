=========================
Flash Fio Readines
=========================
* **Test Module** - drive_md5_verify.drive_md5_verify
* **Test Control file** - Control file differs based on the drive type, file system, run time that you want to stress the drives.

----------------
Test Description
----------------
**This test uses the Fio tool which is a public domain tool for testing drives and NVME's. This test validates performance by stressing the drives by creating and running the fio jobs.**

---------------------------------------------------------
Test execution and steps involved
---------------------------------------------------------
* Pass the fio templates from the test control files.
    *Example:*
      rootfs_template.job

      boot_sert.job

      filesystem_template.job

      sequential_job.fio

      stress_fio.fio

      flash_fio_readiness.job

      ssd_health_counter.job
* Validate the provided FIO job file or creating the workload file if needed.
* Run the FIO workloads on the target storage devices.
* Validate the FIO result and removing temporary files created during the test
