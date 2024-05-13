=========================
Drive Data Integrity Test
=========================
* **Test Module** - drive_data_integrity.drive_data_integrity
* **Test Control file** - Control file differs based on the cycle_type used to run the drive data integrity test
  - *AC Cycle - autoval_ssd/tests/drive_data_integrity/di_1_ac_local.json*
  - *DC Cycle - autoval_ssd/tests/drive_data_integrity/di_1_dc_cycle_notified_local.json*
  - *Reboot - autoval_ssd/tests/drive_data_integrity/di_1_inband_warm_reboot.json*
  - The above is an example of the numerous test control files available. There are also multiple test control files for checking sled cycle, on boot drive, ungraceful shutdown, reboots, and other options.


----------------
Test Description
----------------
**This test is used to determine the data integrity of the system consisting data drives under the circumstances of performing different cycle operations like AC cycle, DC cycle, Warm cycle, Reboot etc.,**

------------------------------------------------------------
Different types of power cycles and their control parameters
------------------------------------------------------------

Common Objective of drive_data_integrity test
---------------------------------------------
Verify that a DUT with SSD can reboot reliably from a shutdown, offload the data in DRAM (if present) and recover without errors upon power on.
The data written on the SSD before power down should have integrity after the system is rebooted.

* **Drive Data Integrity - Warm Cycle**
  - Definition
    + Executes the test with the graceful (warm) shutdown with respect to the *Common Objective*
  - Control parameters
    + ``{
          "cycle_type": "warm",
          "drive_type": "ssd",
          "remote_fio": false,
          "cycle_count": 1,
          "config_components": [
          "BMC",
          "DUT",
          "BIOS",
          "CPU"]
          }``


* **Drive Data Integrity - AC Cycle**
  - Definition
   + Executes the test with the AC Cycle with respect to the *Common Objective*
  - Control parameters
   + ``{
          "cycle_type": "ac",
          "drive_type": "ssd",
          "remote_fio": false,
          "cycle_count": 1,
          "config_components": [
          "BMC",
          "DUT",
          "BIOS",
          "CPU"]
          }``


* **Drive Data Integrity - DC Cycle**
  - Definition
   + Executes the test with the DC Cycle with respect to the *Common Objective*
  - Control parameters
   + ``{
          "cycle_type": "dc",
          "drive_type": "ssd",
          "remote_fio": false,
          "cycle_count": 1,
          "config_components": [
          "BMC",
          "DUT",
          "BIOS",
          "CPU"]
          }``

* **Drive Data Integrity - Graceful 30s Cycle**
  - Definition
   + Executes the test with the Graceful shutdown with respect to the *Common Objective*
  - Control parameters
   + ``{
          "cycle_type": "graceful_30s_cycle",
          "drive_type": "ssd",
          "remote_fio": false,
          "cycle_count": 1,
          "config_components": [
          "BMC",
          "DUT",
          "BIOS",
          "CPU"]
          }``

* **Drive Data Integrity - Reboot Cycle**
  - Definition
   + Executes the test with the system reboot with respect to the *Common Objective*
  - Control parameters
   + ``{
          "cycle_type": "reboot",
          "drive_type": "ssd",
          "remote_fio": false,
          "cycle_count": 1,
          "config_components": [
          "BMC",
          "DUT",
          "BIOS",
          "CPU"]
          }``

---------------------------------------------------------
Phases of Test execution and steps involved in each phase
---------------------------------------------------------

SetUp Phase
-----------

=========================================     ====================================================================================
Step Description                                      Commands
=========================================     ====================================================================================
``Check if DUT is accessible``                 ping6 -c 3 -i 0.2 <ip address>

``Install the rpms required                    sudo dnf -y --allowerasing --disablerepo=\* --enablerepo=fava install <rpm name> -b
  such as fio, sshpass``

``Identify Boot drive``                        ls -la /sys/block/nvme0n1, file -s /dev/nvme0n1, lsblk -J

``Create SMART log directory``                 NA

``Get list of drives based on                  NA
  type and interface``

``Collect SMART and Config data``              nvme smart-log /dev/nvme0n1 -o json

``Check fio version compatibilty               NA
  between DUT and controller``

``Frame the skeleton of the power              sshpass -p 0penBmc ssh -o StrictHostKeyChecking=no root@<hostname>
  cycle command required for trigger``
==========================================    ======================================================================================

Execution Phase
---------------

==========================================                    =====================================================================================================
Step Description                                               Commands
==========================================                    =====================================================================================================
``Save the drive logs in SMART folder                              NA
  under results directory asynchronously``

``Sets a random trigger timeout``                                  NA

``Runs the fio write command with trigger option``                 fio seq_write.fio --output-format=json --output=write.json --trigger-timeout=90 --trigger='sshpass -p 0penBmc ssh -o StrictHostKeyChecking=no root@<hostname> "(<cycle_type>)" &'


``Parse fio error in the fio write job``                           NA

``Runs the fio read command                                        fio seq_read.fio --output-format=json --output=read.json
  to avoid MPECC error``

``Remove the Boot drive for verify job                             NA
  if cycle type is "ac", "dc", "warm"``

``Runs the fio verify command                                      fio seq_verify.fio --output-format=json --output=verify.json
  for the available list of drives``
============================================                    =====================================================================================================

CleanUp Phase
-------------

==========================================       =============================================================================
Step Description                                           Commands
==========================================       =============================================================================
``Cleanup the test file``                         rm -f /root/autoval_fio_file

``Cleanup the cache``                             sync; echo 3>/proc/sys/vm/drop_caches; swapoff -a; swapon -a

``Check for the host's power status``             power-util <slot_number> status

``Power on the host``                             power-util <slot_number> on

``Collect SMART and Config data post test``       nvme smart-log /dev/nvme0n1 -o json

``Append storage_test_base config into the        NA
  config_results file from test base``
===========================================      ===============================================================================

---------------
Expected Result
---------------
* The DUT is still accessible at the end of the test.
* The fio info should not have any error/failure logs.
* Install fio and sshpass successfully.
* Collect drive list and returned list is valid.
* The fio write ,read and verify operations should be successful without any issues for specified iterations.
* The system should reconnect and there shouldn't be any fio read and verify issues post cycle operation.
* The system configuration before and after test should not show any differences.
