# How to administer RPM hosting in an AutoVal environment

## Background

Some autoval tests require specific tools (RPMs) in order to function correctly and are designed to automatically download and install them to the DUT if they are not available.  RPMs are installed using ``dnf install...`` on DUTs (and ``yum install...`` is used on DUTs running CentOS 7 and older).  The default name of the repo is ``autoval-tools`` (configured using the ``yum_repo`` setting in ``site_settings.json``).

This guide describes how to:

1. Configure the Test Server as a DNF repository host and
2. Configure each DUT as a DNF client

This guide assumes that ``/shared/autoval`` network filesystem is already mounted on all DUTs (see [gluster_configuration.md](gluster_configuration.md) for more info.)

## Overview

DNF configuration requires changes on both the Test Server and the DUTs

On the Test Server:

* Install createrepo utility
* Create a repository directory
* Put RPM files into the repository directory
* Create the repository metadata

On each DUT:

* Create the repository configuration file

## Configuration Steps

### 1. Install ``createrepo`` on the Test Server

To create a DNF repository we need to install the ``createrepo`` software package
Example:

```bash
dnf install createrepo_c
```

### 2. Create a repository directory on the Test Server

We recommend using ``/shared/autoval/pkgs/`` as the directory to contain the RPMs.

Example:
```bash
mkdir -p /shared/autoval/pkgs/
```

### 3. Copy RPM files into the repository directory

Download and copy RPMs into the repository directory based on test requirements.  We recommend the following (at a minimum):

* ``smartmontools``
* ``fb-FioSynthFlash``
* ``fio-engine-libaio``
* ``fio``
* ``hdparm``
* ``libaio``
* ``nvme-cli``
* ``sdparm``

> [!NOTE]
> Specific versions of RPMs (e.g. ``fio`` or ``nvme-cli`` may be needed for specific tests or types of testing).

### 4. Generate the repository metadata

The ``createrepo`` command reads through the repository directory and generates the metadata necessary for it to function as a DNF repository (it creates th ``repodata/`` subdirectoryfor this purpose).

On the Test Server:

```bash
cd /shared/autoval && createrepo --update pkg
```

> [!IMPORTANT]
> Each time RPM package files are added to the repository directory, the metadata must be regenerated.

### 5. Configure DUTs to use the ``autoval-tools`` repository

On each DUT, create a file named ``/etc/yum.repos.d/autoval.repo`` with the following contents:

```toml
[autoval-tools]
name="CentOS9 - tools for autoval support"
baseurl="file:///shared/autoval/pkgs"
enabled=1
gpgcheck=0
```

> [!NOTE]
> A more advanced (and typical) configuration is to use the ``https`` as the DNF protocol but this would require configuration and maintenance of a web server (e.g. ``nginx``) on the Test Server and is out of scope for this guide.
