#!/usr/bin/env bash

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    printf 'This file is a library for the Windows VM scripts and is not run directly.\n' >&2
    exit 2
fi

tool_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
default_repo_dir=$(cd "$tool_dir/../.." && pwd)
config_file=${GALEFLING_VM_CONFIG:-$tool_dir/vm.env}

if [[ ! -r "$config_file" ]]; then
    printf 'Missing VM configuration: %s\n' "$config_file" >&2
    printf 'Copy %s/vm.env.example to vm.env and set local paths.\n' "$tool_dir" >&2
    exit 1
fi

# shellcheck source-path=SCRIPTDIR
# shellcheck source=vm.env.example
source "$config_file"

REPO_DIR=${REPO_DIR:-$default_repo_dir}
export REPO_DIR
unset default_repo_dir

: "${VM_NAME:?VM_NAME is required in vm.env}"
: "${VM_COMPUTER_NAME:?VM_COMPUTER_NAME is required in vm.env}"
: "${VM_USER:?VM_USER is required in vm.env}"
: "${VM_FULL_NAME:?VM_FULL_NAME is required in vm.env}"
: "${VM_TIME_ZONE:?VM_TIME_ZONE is required in vm.env}"
: "${VM_MEMORY_MIB:?VM_MEMORY_MIB is required in vm.env}"
: "${VM_VCPUS:?VM_VCPUS is required in vm.env}"
: "${VM_DISK_GIB:?VM_DISK_GIB is required in vm.env}"
: "${LIBVIRT_URI:?LIBVIRT_URI is required in vm.env}"
: "${LIBVIRT_NETWORK:?LIBVIRT_NETWORK is required in vm.env}"
: "${LIBVIRT_QEMU_USER:?LIBVIRT_QEMU_USER is required in vm.env}"
: "${BASELINE_SNAPSHOT:?BASELINE_SNAPSHOT is required in vm.env}"
: "${DATA_DIR:?DATA_DIR is required in vm.env}"
: "${WINDOWS_ISO:?WINDOWS_ISO is required in vm.env}"
: "${VIRTIO_ISO:?VIRTIO_ISO is required in vm.env}"
: "${PYTHON_INSTALLER:?PYTHON_INSTALLER is required in vm.env}"
: "${WINFSP_INSTALLER:?WINFSP_INSTALLER is required in vm.env}"
: "${PRODUCT_KEY_FILE:?PRODUCT_KEY_FILE is required in vm.env}"
: "${VM_PASSWORD_FILE:?VM_PASSWORD_FILE is required in vm.env}"
: "${DISK_IMAGE:?DISK_IMAGE is required in vm.env}"
: "${SSH_PRIVATE_KEY:?SSH_PRIVATE_KEY is required in vm.env}"
: "${SSH_PUBLIC_KEY:?SSH_PUBLIC_KEY is required in vm.env}"

vm_virsh() {
    sudo virsh --connect "$LIBVIRT_URI" "$@"
}

get_vm_ip() {
    vm_virsh domifaddr "$VM_NAME" --source lease |
        awk '/ipv4/ {sub("/.*", "", $4); print $4; exit}'
}

wait_for_agent() {
    local attempts=$1
    local delay=$2
    local attempt

    for ((attempt = 1; attempt <= attempts; attempt++)); do
        if vm_virsh qemu-agent-command "$VM_NAME" '{"execute":"guest-ping"}' >/dev/null 2>&1; then
            return 0
        fi
        sleep "$delay"
    done
    return 1
}

wait_for_shutoff() {
    local vm_state

    for _ in {1..150}; do
        vm_state=$(vm_virsh domstate "$VM_NAME" 2>/dev/null | tr -d '\r')
        if [[ "$vm_state" == 'shut off' ]]; then
            return 0
        fi
        sleep 2
    done
    return 1
}

ssh_vm() {
    local guest_ip=$1
    shift
    ssh -i "$SSH_PRIVATE_KEY" \
        -o BatchMode=yes \
        -o ConnectTimeout=5 \
        -o LogLevel=ERROR \
        -o StrictHostKeyChecking=accept-new \
        "$VM_USER@$guest_ip" "$@"
}
