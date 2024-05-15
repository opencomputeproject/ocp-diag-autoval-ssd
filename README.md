# ocp-diag-autoval-ssd
**ocp-diag-autoval-ssd** is a collection of SSD tests using the **ocp-diag-autoval** test framework.

## Overview
At a high level, the following steps are necessary to install, build, and use autoval
1. [Installation](#installation)
2. [Environment Setup](#environment-setup)
3. [Executing Tests](#executing-tests)

## Installation
This installation steps are a work in progress.  They will be improved/simplified in the future.
1. Clone the following repos:
```
$ git clone https://github.com/opencomputeproject/ocp-diag-autoval.git
$ git clone https://github.com/opencomputeproject/ocp-diag-autoval-ssd.git
```
2. Create a virtual environment:
```
$ python -m venv env
$ source ./env/bin/activate
$ pip install build
```
3. Build and install `ocptv-autoval`
```
$ cd ocp-diag-autoval
$ python -m build
$ pip install ./dist/ocptv_autoval-0.0.1.tar.gz
```
4. Build and install `ocptv-autoval-ssd`
```
$ cd ocp-diag-autoval-ssd
$ python -m build
$ mkdir -p ~/bin/ocp-diag-autoval-ssd/
$ pip install --no-deps ./dist/ocptv_autoval_ssd-0.0.1.tar.gz --target ~/bin/ocp-diag-autoval-ssd
```
## Environment Setup
There are two parts to environment setup:
1. Creating and maintaining a repo to host RPMs and tools needed by autoval tests
2. Creating a `site_settings.json` file.
### Creating and maintaining a repo
Local repo hosting is required because many tests require specific RPMs in order to run (e.g. `fio`, `fio-synth`) and automatically download and install them at test setup time. We strongly recommend naming the repo autoval-tools (as it aligns with default configuration defined in `site_settings.json`).
### Creating a site settings file
Before running tests for the first time, you'll need to create a `site_settings.json` file.
Here is an example with some basic defaults.
``` json
{
  "control_server_logdir": "/autoval/logs/",
  "control_server_tmpdir": "/tmp/autoval/",
  "dut_logdir": "/autoval/logs/",
  "dut_tmpdir": "/tmp/autoval/",
  "resultsdir": "/autoval/results/",
  "ssh_key_path": ["/USERNAME/.ssh/id_rsa"], # Replace contents with a path to your public SSH key
  "plugin_config_path" : "plugins/plugin_config.json",
  "repository_dir": "/autoval/repository/",
  "test_utils_plugin_config_path" : "plugins/test_utils_plugin_config.json",
  "cleanup_dut_logdirs" : false,
  "yum_repo": "autoval-tools"
}
```

See [rpm_repo_hosting.md](rpm_repo_hosting.md) for detailed instructions on how to configure a DNF repo on the test server.
## Executing Tests
### Host configuration file
Before executing tests, you need to create a `hosts.json` file.
The `{-c|--config} CONFIG` autoval option is used to specify DUT configuration in well-formed JSON.  This configuration contains the following information:
* `hostname`:  IP address of the host
* `oob_addr`:  IP address of the BMC
* `username`:  Name of the host user
* `password`:  Password for the host user
* `oob_username`: Name of the OOB user
* `oob_password`: Password for the OOB user

Example:
```JSON
{
"hosts":
  [
   {
    "hostname": "10::CD97:E10F:FE82:9A1C",
    "username": "root",
    "password": "password",
    "oob_addr": "10::CD97:E10F:FE82:9A19",
    "oob_username": "root",
    "oob_password": "password"
   }
   ]
}
```
### Test Execution
Now that you have a `hosts.json` file, you can run a test (e.g. `simple.test`) as follows.
```
$ cd ~/bin/ocp-diag-autoval-ssd
$ export PYTHONPATH=.
$ env SITE_SETTINGS="$(cat path/to/site_settings.json)" \
    python -m autoval.autoval_test_runner autoval_ssd.tests.nvme_cli.nvme_cli \
    --config ./hosts.json \
    --test_control ~/bin/ocp-diag-autoval-ssd/autoval_ssd/tests/nvme_cli/control.json
```
