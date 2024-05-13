===========================
UBOOTT Workload Loop Stress
===========================
* **Test Module** - fio_synth_flash.fio_synth_flash
* **Test Control file path **
  - autoval_ssd/tests/fio_synth_flash/UBOOTT_Workload_loop.json
  - autoval_ssd/tests/fio_synth_flash/USSDT_Workload_loop.json

-----------------
Test Description
-----------------
*Test measures the drive performance with the specified Workload(UBOOTT_Workload_Loop, USSDT_Workload_loop.json) and compares the basic fio parameters such as bandwidth, latency with the reference values*

------------------------
Test Control parameters
------------------------

``{
  "test_drive_filter": true,
  "drive_type": "ssd",
  "only_boot_drive": true,
  "workload": ["UBOOTT_Workload_loop"],
  "fio_synth_params": {
    "synth_verify": true,
    "ignore_error": true,
    "parallel": true
  }
}``

-----------------------------------------------------------------------------------
Phases of Test execution and steps involved in each phase with UBOOTT_Workload_Loop
-----------------------------------------------------------------------------------

SetUp Phase
-----------

=========================================       ====================================================================================
 Step Description                                Commands
=========================================       ====================================================================================
``Check if DUT is accessible``                   ping6 -c 3 -i 0.2 <ip address>

``Install the rpms required                      sudo dnf -y --allowerasing --disablerepo=\* --enablerepo=fava install <rpm name> -b
  such as fio, fb-FioSynthFlash``

``Identify Boot drive``                          ls -la /sys/block/nvme0n1, file -s /dev/nvme0n1, lsblk -J

``Create SMART log directory``                   NA

``Get list of drives based on                    NA
  type and interface``

``Collect SMART and Config data``                nvme smart-log /dev/nvme0n1 -o json

``Set up the fiosynthflash results directory``   NA
=============================================   ======================================================================================

Execution Phase
---------------

==========================================        ===================================================================================
 Step Description                                 Commands
==========================================        ===================================================================================
``Format the drive if formatting is enabled``     nvme format /dev/<drive_name> -s <secure_erase_option> -r


``Backup workload loop stress json for restore    NA
  at test end``


``Enable latency monitor settings``               NA


``Start precondition workload loop stress         fb-FioSynthFlash -x -w UBOOTT_Workload_loop -f <Result file> -d /dev/<drive_name>
  fiosynth job``


``Collect post latency monitor logs``             NA


``Parse and validate lm_parser results``          NA


``Collect drive performance data``                NA


``Disable latency monitor settings``              NA


``Enable latency monitor settings``               NA


``Start workload loop stress fiosynth job``       fb-FioSynthFlash -x -w UBOOTT_Workload_loop -f <Result file> -d /dev/<drive_name>


``Collect post latency monitor logs``             NA


``Parse and validate lm_parser results``          NA


``Collect drive performance data``                NA


``Disable latency monitor settings``              NA
============================================     =====================================================================================

CleanUp Phase
-------------

==========================================       =============================================================================
 Step Description                                 Commands
==========================================       =============================================================================
``Restore workload stress json file``             NA

``Disable latency monitor settings``              NA

``Change nvme io timeout in cleanup phase``       /sys/module/nvme_core/parameters/io_timeout will be executed as a file script

``Collect SMART and Config data post test``       nvme smart-log /dev/nvme0n1 -o json

``Append storage_test_base config into the        NA
  config_results file from test base``
===========================================      ===============================================================================

----------------
Expected Result
----------------
* The DUT is still accessible at the end of the test.
* The system configuration should not show any changes.
* Fio Synth workload should have been run without error.
* Collect and check fio test result to see if any value out of expected ones.
* Each fio output should meet the target file minimum-maximum values.
* The system log info should not have any error/failure logs.
