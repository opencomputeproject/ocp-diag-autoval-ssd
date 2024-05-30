=========================
Nvme Cli
=========================
* **Test Module** - nvme_cli.nvme_cli
* **Test Control file**
  - *all drives - /autoval_ssd/tests/nvme_cli/control.json*
  - *only data drives - /autoval_ssd/tests/nvme_cli/control_disable_boot_drive.json*
  - *disable crypto_erase check - /autoval_ssd/tests/nvme_cli/control_no_crypto_erase.json*
  - *nvme version - /autoval_ssd/tests/nvme_cli/nvme_cli_with_nvme_version.json*

----------------
Test Description
----------------
**    Test to validate if NVMe spec commands are supported by the NVMe Drives.
        Get the controller properties,
        Get the Firmware Log,
        Check Crypto Erase Support,
        Get Error Log Entries,
        Log the properties of the specified namespace,
        Get the operating parameters of the specified controller,
        identified by the Feature Identifier,
        Get Vendor Specific Internal Logs,
        Retrieve Command Effects Log.
        Get Vendor Specific drive up time,
        Get Smart log,
        Get/Set Power mode.
        validate capacity
  **

Common Objective of nvme_cli test
---------------------------------------------
Verify that a DUT with SSD NVMe can support the NVMe Spec commands.
