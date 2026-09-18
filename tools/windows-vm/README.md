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

## Run the functional tests

```bash
make test-functional-win-vm                    # whole functional suite
make test-functional-win-vm PYTEST_ARGS="tests/functional/test_media_processing.py"
make test-functional-win-vm-clean              # revert to the baseline snapshot first
```

`run-tests.sh` starts the VM if needed, re-syncs the guest copy of the repository,
runs pytest over SSH, and exits with the guest's exit code. Pass `--no-sync` to skip
the refresh. See `docs/testing/FUNCTIONAL_TESTING.md` for the full workflow.

Tests run from `C:\GaleFling`, not the share: pytest's rootdir scan fails on the
repository's `logs` symlink through VirtIO-FS. The copy is mirrored from `Z:` on every
run, so it always matches the host working tree. Credentials are read from
`Z:\tests\functional\.env` via `GALEFLING_FUNCTIONAL_ENV` and are never written to the
guest disk.

## Build a Windows executable or installer

```bash
make win-vm-installer                        # dist/GaleFling.exe + build/GaleFling-Setup-*.exe
make win-vm-installer BUILD_ARGS="--exe-only" # dist/GaleFling.exe only
make win-vm-installer-clean                   # revert to the baseline snapshot first
```

Useful for producing a Windows build of a branch to test manually before it merges
to `master`, without creating a git tag or touching `.github/workflows/release.yml`
(which only ever builds from `master` or an existing `refs/tags/vX.Y.Z`, and would
pollute the tag history used to compute the next release version if abused for
this). `build-installer.sh` regenerates `src/utils/_version.py` on the host from
`git describe` against whatever is currently checked out, syncs the guest copy,
builds with PyInstaller, and copies `dist\GaleFling.exe` back through the VirtIO-FS
share into this repo's own (gitignored) `dist/`.

By default it also bootstraps Chocolatey from the official
`community.chocolatey.org` installer and installs NSIS on the guest if neither is
already present, then builds `build/GaleFling-Setup-*.exe` the same way CI does.
That installs software on the guest, drifting it away from the `clean-loggedout`
baseline — pair a default run with `--revert`/`win-vm-installer-clean`, or run
`snapshot-vm.sh revert clean-loggedout` yourself afterward, before relying on the
VM for isolated functional-test runs again. Pass `--exe-only` to skip the NSIS
stage entirely and avoid that drift.

## Repository sharing

The live repository is mounted as `Z:` through VirtIO-FS. The finalizer also makes
a credential-free local copy at `C:\GaleFling` for pytest. It excludes `.env`,
`.git`, `.venv`, and `logs`; the repository's `logs` entry can be an absolute Linux
symlink that Windows cannot represent through VirtIO-FS.
