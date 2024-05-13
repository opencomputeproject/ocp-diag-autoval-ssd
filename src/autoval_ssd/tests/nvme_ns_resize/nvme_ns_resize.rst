=========================
Nvme_ns_resize
=========================
* **Test Module** - nvme_ns_resize.nvme_ns_resize
* **Test Control file** - op_pct_sweep_control

----------------

Test Description
----------------
**The purpose of the test is to create namespace using NVMe create-ns command with a variety of sizes and
run FIO to ensure IOs can be issued to the new namespace.

---------------------------------------------------------
Test execution and steps involved
---------------------------------------------------------
* Verify the DUT is accessible.
* Collect only the nvme SSD drives on the DUT based on drive type and interface.
* Get the drives which support namespace management.
* For each of drive, different userspace will be created.
* Once the namespace is created, fio is run to ensure that namespace is properly created.
