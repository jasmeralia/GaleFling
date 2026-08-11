#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib.sh
source "$script_dir/lib.sh"

action=${1:-}
snapshot_name=${2:-}

usage() {
    printf 'Usage:\n' >&2
    printf '  %s list\n' "$0" >&2
    printf '  %s create [name]\n' "$0" >&2
    printf '  %s revert [name]\n' "$0" >&2
}

validate_name() {
    if [[ ! $1 =~ ^[A-Za-z0-9._-]+$ ]]; then
        printf 'Snapshot names may contain only letters, numbers, dots, underscores, and hyphens.\n' >&2
        exit 2
    fi
}

case "$action" in
    list)
        if [[ $# -ne 1 ]]; then
            usage
            exit 2
        fi
        vm_virsh snapshot-list "$VM_NAME"
        ;;
    create)
        if [[ $# -gt 2 ]]; then
            usage
            exit 2
        fi
        if [[ -z "$snapshot_name" ]]; then
            snapshot_name="manual-$(date +%Y%m%d-%H%M%S)"
        fi
        validate_name "$snapshot_name"
        if vm_virsh snapshot-list "$VM_NAME" --name | grep -Fxq "$snapshot_name"; then
            printf 'Snapshot already exists: %s\n' "$snapshot_name" >&2
            exit 1
        fi
        "$script_dir/stop-vm.sh"
        vm_virsh snapshot-create-as "$VM_NAME" "$snapshot_name" \
            --description "Manual GaleFling VM snapshot created $(date --iso-8601=seconds)" \
            --atomic
        printf 'Created snapshot %s.\n' "$snapshot_name"
        "$script_dir/start-vm.sh"
        ;;
    revert)
        if [[ $# -gt 2 ]]; then
            usage
            exit 2
        fi
        snapshot_name=${snapshot_name:-$BASELINE_SNAPSHOT}
        validate_name "$snapshot_name"
        if ! vm_virsh snapshot-list "$VM_NAME" --name | grep -Fxq "$snapshot_name"; then
            printf 'Snapshot does not exist: %s\n' "$snapshot_name" >&2
            exit 1
        fi
        printf 'Reverting to %s; newer guest changes will be discarded.\n' "$snapshot_name"
        "$script_dir/stop-vm.sh"
        start_seconds=$SECONDS
        vm_virsh snapshot-revert "$VM_NAME" "$snapshot_name"
        elapsed_seconds=$((SECONDS - start_seconds))
        printf 'Reverted snapshot %s in %s seconds.\n' "$snapshot_name" "$elapsed_seconds"
        "$script_dir/start-vm.sh"
        ;;
    *)
        usage
        exit 2
        ;;
esac
