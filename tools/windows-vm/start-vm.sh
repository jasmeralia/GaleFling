#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib.sh
source "$script_dir/lib.sh"

vm_state=$(vm_virsh domstate "$VM_NAME" 2>/dev/null | tr -d '\r')
case "$vm_state" in
    'shut off')
        vm_virsh start "$VM_NAME"
        ;;
    paused)
        vm_virsh resume "$VM_NAME"
        ;;
    running)
        printf 'VM %s is already running.\n' "$VM_NAME"
        ;;
    *)
        printf 'VM %s is in an unsupported state: %s\n' "$VM_NAME" "$vm_state" >&2
        exit 1
        ;;
esac

if ! wait_for_agent 150 2; then
    printf 'VM %s started, but the guest agent was not ready within five minutes.\n' "$VM_NAME" >&2
    exit 1
fi

guest_ip=$(get_vm_ip)
printf 'VM %s is ready.\n' "$VM_NAME"
if [[ -n "$guest_ip" ]]; then
    printf 'SSH: ssh -i %s %s@%s\n' "$SSH_PRIVATE_KEY" "$VM_USER" "$guest_ip"
fi
