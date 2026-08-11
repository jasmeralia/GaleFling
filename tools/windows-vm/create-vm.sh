#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib.sh
source "$script_dir/lib.sh"

answer_template="$script_dir/Autounattend.xml.template"
provision_template="$script_dir/provision.ps1.template"
answer_file="$DATA_DIR/Autounattend.xml"
provision_file="$DATA_DIR/provision.ps1"
answer_iso="$DATA_DIR/${VM_NAME}-unattended.iso"

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        printf 'Missing required host command: %s\n' "$1" >&2
        exit 1
    fi
}

verify_checksum() {
    local path=$1
    local expected=$2
    local actual

    if [[ -z "$expected" ]]; then
        return 0
    fi
    actual=$(sha256sum "$path" | awk '{print $1}')
    if [[ "$actual" != "$expected" ]]; then
        printf 'Checksum mismatch for %s\n' "$path" >&2
        exit 1
    fi
}

xml_escape() {
    local value=$1
    value=${value//&/\&amp;}
    value=${value//</\&lt;}
    value=${value//>/\&gt;}
    value=${value//\"/\&quot;}
    value=${value//\'/\&apos;}
    printf '%s' "$value"
}

grant_directory_traverse() {
    local directory=$1

    while [[ "$directory" != / ]]; do
        if ! sudo -u "$LIBVIRT_QEMU_USER" test -x "$directory"; then
            sudo setfacl -m "u:$LIBVIRT_QEMU_USER:--x" "$directory"
        fi
        directory=$(dirname "$directory")
    done
}

for command_name in base64 genisoimage iconv jq openssl setfacl sha256sum virt-install; do
    require_command "$command_name"
done

if [[ ! "$VM_COMPUTER_NAME" =~ ^[A-Za-z0-9-]{1,15}$ ]]; then
    printf 'VM_COMPUTER_NAME must contain 1-15 letters, numbers, or hyphens.\n' >&2
    exit 1
fi
if [[ ! "$VM_USER" =~ ^[A-Za-z0-9._-]+$ ]]; then
    printf 'VM_USER contains unsupported characters.\n' >&2
    exit 1
fi

install -d -m 700 "$DATA_DIR"
if [[ ! -e "$VM_PASSWORD_FILE" ]]; then
    umask 077
    openssl rand -base64 24 >"$VM_PASSWORD_FILE"
    printf 'Generated the VM password at %s.\n' "$VM_PASSWORD_FILE"
fi

for required_file in \
    "$WINDOWS_ISO" \
    "$VIRTIO_ISO" \
    "$PRODUCT_KEY_FILE" \
    "$VM_PASSWORD_FILE" \
    "$SSH_PRIVATE_KEY" \
    "$SSH_PUBLIC_KEY" \
    "$answer_template" \
    "$provision_template" \
    "$PYTHON_INSTALLER" \
    "$WINFSP_INSTALLER"; do
    if [[ ! -r "$required_file" ]]; then
        printf 'Missing required file: %s\n' "$required_file" >&2
        exit 1
    fi
done

verify_checksum "$VIRTIO_ISO" "${VIRTIO_SHA256:-}"
verify_checksum "$PYTHON_INSTALLER" "${PYTHON_SHA256:-}"
verify_checksum "$WINFSP_INSTALLER" "${WINFSP_SHA256:-}"

if vm_virsh dominfo "$VM_NAME" >/dev/null 2>&1; then
    printf 'VM %s already exists; refusing to overwrite it.\n' "$VM_NAME" >&2
    exit 1
fi
if [[ -e "$DISK_IMAGE" ]]; then
    printf 'Disk image already exists; refusing to overwrite it: %s\n' "$DISK_IMAGE" >&2
    exit 1
fi

umask 077
product_key=$(tr -d '\r\n' <"$PRODUCT_KEY_FILE")
vm_password=$(tr -d '\r\n' <"$VM_PASSWORD_FILE")
ssh_public_key_b64=$(base64 -w0 <"$SSH_PUBLIC_KEY")

answer_xml=$(<"$answer_template")
answer_xml=${answer_xml//@@PRODUCT_KEY@@/$(xml_escape "$product_key")}
answer_xml=${answer_xml//@@VM_PASSWORD@@/$(xml_escape "$vm_password")}
answer_xml=${answer_xml//@@VM_USER@@/$(xml_escape "$VM_USER")}
answer_xml=${answer_xml//@@VM_FULL_NAME@@/$(xml_escape "$VM_FULL_NAME")}
answer_xml=${answer_xml//@@VM_COMPUTER_NAME@@/$(xml_escape "$VM_COMPUTER_NAME")}
answer_xml=${answer_xml//@@VM_TIME_ZONE@@/$(xml_escape "$VM_TIME_ZONE")}
printf '%s\n' "$answer_xml" >"$answer_file"

provision_script=$(<"$provision_template")
provision_script=${provision_script//@@SSH_PUBLIC_KEY_B64@@/$ssh_public_key_b64}
printf '%s\n' "$provision_script" >"$provision_file"

unset answer_xml product_key provision_script ssh_public_key_b64 vm_password
chmod 600 "$answer_file" "$provision_file" "$VM_PASSWORD_FILE" "$PRODUCT_KEY_FILE"

iso_staging=$(mktemp -d)
trap 'command rm -r "$iso_staging"' EXIT
install -m 600 "$answer_file" "$iso_staging/Autounattend.xml"
install -m 600 "$provision_file" "$iso_staging/provision.ps1"
install -m 644 "$PYTHON_INSTALLER" "$iso_staging/python-installer.exe"
install -m 644 "$WINFSP_INSTALLER" "$iso_staging/winfsp.msi"
genisoimage -quiet -J -r -V GALESETUP -o "$answer_iso" "$iso_staging"
chmod 600 "$answer_iso"

for path in "$WINDOWS_ISO" "$VIRTIO_ISO" "$answer_iso" "$REPO_DIR"; do
    grant_directory_traverse "$(dirname "$path")"
done
sudo setfacl -m "u:$LIBVIRT_QEMU_USER:r--" "$WINDOWS_ISO" "$VIRTIO_ISO" "$answer_iso"
sudo setfacl -m "u:$LIBVIRT_QEMU_USER:rx" "$REPO_DIR"

sudo virt-install \
    --connect "$LIBVIRT_URI" \
    --name "$VM_NAME" \
    --memory "$VM_MEMORY_MIB" \
    --memorybacking source.type=memfd,access.mode=shared \
    --vcpus "$VM_VCPUS",sockets=1,cores="$VM_VCPUS",threads=1 \
    --cpu host-passthrough \
    --machine q35 \
    --osinfo win11 \
    --boot firmware=efi,firmware.feature0.name=secure-boot,firmware.feature0.enabled=yes,firmware.feature1.name=enrolled-keys,firmware.feature1.enabled=yes \
    --features smm=on \
    --tpm backend.type=emulator,backend.version=2.0,model=tpm-crb \
    --disk path="$DISK_IMAGE",size="$VM_DISK_GIB",format=qcow2,bus=sata,cache=none,discard=unmap \
    --disk path="$WINDOWS_ISO",device=cdrom,readonly=on,boot.order=1 \
    --disk path="$VIRTIO_ISO",device=cdrom,readonly=on \
    --disk path="$answer_iso",device=cdrom,readonly=on \
    --filesystem source="$REPO_DIR",target=mount_tag,driver.type=virtiofs,accessmode=passthrough \
    --network network="$LIBVIRT_NETWORK",model=e1000e \
    --graphics spice,listen=none \
    --video qxl \
    --channel spicevmc \
    --channel type=unix,target.type=virtio,target.name=org.qemu.guest_agent.0 \
    --controller usb,model=qemu-xhci \
    --autostart \
    --noautoconsole

# Microsoft's retail ISO requires a keypress before its UEFI bootloader starts.
for _ in {1..10}; do
    sleep 1
    vm_virsh send-key "$VM_NAME" KEY_ENTER
done

printf 'Started unattended installation for %s.\n' "$VM_NAME"
printf 'The VM password is stored in %s.\n' "$VM_PASSWORD_FILE"
"$script_dir/finish-vm.sh"
