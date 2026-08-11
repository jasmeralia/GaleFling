# Windows 11 WebView test VM

This directory contains the reusable libvirt/KVM harness for GaleFling's Windows
functional-test VM. Machine-specific paths, credentials, installers, generated
answer files, and VM disks stay outside Git.

The default VM has 16 GiB RAM, 4 vCPUs, a 120 GiB sparse disk, UEFI Secure Boot,
TPM 2.0, VirtIO storage/network/balloon devices, a QEMU guest agent, OpenSSH, and
a VirtIO-FS mount of this repository at `Z:`.

## Configure local paths

Copy the example configuration and edit the copy:

```bash
cp tools/windows-vm/vm.env.example tools/windows-vm/vm.env
chmod 600 tools/windows-vm/vm.env
```

`vm.env` is gitignored. Keep the actual SSH keypair in `~/.ssh` and set
`SSH_PRIVATE_KEY` and `SSH_PUBLIC_KEY` to those paths. Do not copy private keys,
Windows product keys, passwords, installers, ISOs, or generated answer files into
this directory.

`DATA_DIR` controls the external artifact directory. Place these files at the paths
configured in `vm.env`:

- A Windows 11 consumer ISO containing Windows 11 Pro.
- The `virtio-win` driver ISO.
- The Python 3.12 Windows installer.
- The WinFsp MSI (needed only by VirtIO-FS to expose the host repository as `Z:`).
- A text file containing the Windows product key.

If `VM_PASSWORD_FILE` does not exist, `create-vm.sh` generates it with mode `0600`.
Optional SHA-256 settings verify the pinned support installers before use.

## Host prerequisites

On Ubuntu, the required packages are:

```bash
sudo apt install qemu-system-x86 qemu-utils libvirt-daemon-system libvirt-clients \
  virt-manager virtinst ovmf swtpm swtpm-tools virtiofsd dnsmasq-base virt-viewer \
  libosinfo-bin osinfo-db-tools guestfs-tools wimtools genisoimage jq acl
sudo osinfo-db-import --system --latest
```

The invoking user must belong to the `libvirt` and `kvm` groups. A fresh login may
be required after changing group membership.

## Create and manage the VM

```bash
tools/windows-vm/create-vm.sh
tools/windows-vm/start-vm.sh
tools/windows-vm/stop-vm.sh
tools/windows-vm/snapshot-vm.sh list
tools/windows-vm/snapshot-vm.sh create before-experiment
tools/windows-vm/snapshot-vm.sh revert clean-loggedout
```

`create-vm.sh` refuses to overwrite an existing libvirt domain or disk. It builds a
private answer-file ISO in `DATA_DIR`, installs Windows without libosinfo's
`--unattended` profiles, finishes guest provisioning, verifies the credential-free
media-processing tests, converts storage and networking to VirtIO, and creates the
configured baseline snapshot.

`stop-vm.sh` attempts a graceful Windows shutdown. It refuses to force power-off
unless explicitly called with `--force`. Snapshot creation and reversion stop the
guest cleanly and start it afterward. Reverting discards all guest changes newer
than the selected snapshot.

Set `GALEFLING_VM_CONFIG=/path/to/vm.env` to use a configuration stored somewhere
other than `tools/windows-vm/vm.env`.

## Repository sharing

The live repository is mounted as `Z:` through VirtIO-FS. The finalizer also makes
a credential-free local copy at `C:\GaleFling` for pytest. It excludes `.env`,
`.git`, `.venv`, and `logs`; the repository's `logs` entry can be an absolute Linux
symlink that Windows cannot represent through VirtIO-FS.
