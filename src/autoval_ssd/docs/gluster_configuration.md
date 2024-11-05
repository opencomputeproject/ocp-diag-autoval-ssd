# How to configure and administer glusterfs on an AutoVal test environment

This guide provides instructions on how to configure a Test Server to export a shared filesystem to host logs, tools, and other data for use by DUTs in an AutoVal test environment.

## Create and mount a logical volume on the Test Server

> [!NOTE]
> Before proceeding, ensure that RPMs to support LVM are installed on your system.  (e.g. `pvcreate`, `vgcreate`, `lvcreate` will need to be available)

1. Create physical volume
```bash
pvcreate /dev/nvme1n1
```

2. Create volume group for the physical volume
```bash
vgcreate gluster /dev/nvme1n1
```

3. Use the full size of the partition to create a logical volume
```bash
lvcreate -l 100%FREE -n shared gluster
```

4. Create file system on the logical volume
```bash
mkfs.xfs /dev/gluster/shared
```

5. Mount logical volume on ``/shared``

Create mountpoint
```bash
mkdir -p /shared
```
Add the following entry to the `/etc/fstab` file
```
/dev/gluster/shared /shared xfs defaults 0 0
```

Mount the filesystem
```bash
mount /shared
```

## Create gluster volume and mount on `/shared/autoval` for all hosts

> [!NOTE]
> Before proceeding, ensure that RPMs to support GlusterFS are installed on your system.
> On systems we tested, the following RPMs needed to be installed, but your results may vary:
> * glusterfs
> * glusterfs-api
> * glusterfs-cli
> * glusterfs-client-xlators
> * glusterfs-fuse
> * glusterfs-libs
> * qemu-kvm-block-gluster

2. Start the Gluster service
```bash
systemctl start glusterd
```

3. Create Gluster volume using a single node.
```bash
gluster volume create autoval HOSTNAME:/shared/.brick force
```
Where ``HOSTNAME`` is substituted with name of the host being tested.

4. Start the Gluster volume

```bash
gluster volume status autoval
gluster volume start autoval
```

5. Set various configuration parameters on the Gluster volume

These performance parameters are known to perform well in our own ``AutoVal`` tests and deployments.
```bash
gluster volume set autoval performance.io-thread-count 32
gluster volume set autoval performance.cache-size 1GB
gluster volume set autoval server.event-threads 4
```

6. Ensure `volume management --> transport.address-family` option is set to `inet6`

Ensure the following line is present and uncommented in ``/etc/glusterfs/glusterd.vol``:
```
option transport.address-family inet6
```

## Mount glusterfs volume on Test Server and all DUTs
We recommend using ``/shared/autoval`` as the mount point because multiple configuration settings in [site_settings_vendor.json](../../havoc/autoval/cfg/site_settings/site_settings_vendor.json) depend on it.

1. Create a mountpoint
On Test Server and all DUTs:
```bash
mkdir -p /shared/autoval
```

2. Add entry to ``/etc/fstab``
On Test Server and all DUTs add the following entry to ``/etc/fstab``:
```bash
controller:autoval /shared/autoval glusterfs xlator-option=transport.address-family=inet6,defaults,_netdev 0 0
```

3. Regenerate systemd configuration
On Test Server and all DUTs
```bash
systemctl daemon-reload
```

4. Mount ``/shared/autoval`` and verify that it is correctly mounted
On Test Server and all DUTs and examine output
```bash
mount /shared/autoval
df /shared/autoval
```

> [!IMPORTANT]
> On CentOS 9, there is a known issue where glusterfs ``/etc/fstab`` entries aren't always automatically mounted at boot time.  This happens because of an ordering depending where the `/etc/fstab` file is processed **before** gluterfsd has a change to start up.  In order to work around this issue, install the script [install_glusterfs_automounter.sh](../../scripts/install_glusterfs_automounter.sh) after step 2.
