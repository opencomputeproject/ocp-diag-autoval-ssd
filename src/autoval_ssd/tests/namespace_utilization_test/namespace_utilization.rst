=========================
Namespace Utilization Test
=========================
* **Test Module** - namespace_utilization_test.namespace_utilization_test
* **Test Control file**

  *expected_nuse_size is 2621440 - /autoval_ssd/tests/namespace_utilization_test/namespace_utilization.json*

----------------
Test Description
----------------
**This test validates the namespace utilization size by running fio job and check the size using the 'nvme id-ns /dev/nvmex' command.**

---------------------------------------------------------
Test execution and steps involved
---------------------------------------------------------
* Filter the drives with crypto erase supported options
* Filter the drives with nuse supported drives
* Format the drive with secure erase option
* Read nuse from id-ns and check that it == 0
* Sequentially Write 10GB of data to the drive
* Read nuse from id-ns and check that it equals 2621440(0x280000)
      - indicating 10GB of namespace has been used
* Format the drive with crypto-erase option
* Repeat the steps 3-5 for the given cycle_count
