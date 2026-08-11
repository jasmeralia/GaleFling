#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib.sh
source "$script_dir/lib.sh"

force=false
if [[ ${1:-} == '--force' ]]; then
    force=true
elif [[ $# -gt 0 ]]; then
    printf 'Usage: %s [--force]\n' "$0" >&2
    exit 2
fi

vm_state=$(vm_virsh domstate "$VM_NAME" 2>/dev/null | tr -d '\r')
if [[ "$vm_state" == 'shut off' ]]; then
    printf 'VM %s is already shut off.\n' "$VM_NAME"
    exit 0
fi
if [[ "$vm_state" != running && "$vm_state" != paused ]]; then
    printf 'VM %s is in an unsupported state: %s\n' "$VM_NAME" "$vm_state" >&2
    exit 1
fi

if [[ "$vm_state" == paused ]]; then
    vm_virsh resume "$VM_NAME"
fi

guest_ip=$(get_vm_ip)
shutdown_requested=false
if [[ -n "$guest_ip" ]] && ssh_vm "$guest_ip" 'shutdown.exe /s /t 0 /f'; then
    shutdown_requested=true
fi

if [[ "$shutdown_requested" != true ]]; then
    vm_virsh shutdown "$VM_NAME" --mode acpi
fi

if wait_for_shutoff; then
    printf 'VM %s is shut off.\n' "$VM_NAME"
    exit 0
fi

if [[ "$force" == true ]]; then
    printf 'Graceful shutdown timed out; forcing VM %s off.\n' "$VM_NAME" >&2
    vm_virsh destroy "$VM_NAME"
    exit 0
fi

printf 'Graceful shutdown timed out. Re-run with --force only if discarding in-flight guest writes is acceptable.\n' >&2
exit 1
