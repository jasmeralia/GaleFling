#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib.sh
source "$script_dir/lib.sh"

finalize_script="$script_dir/finalize.ps1"

run_powershell_file() {
    local script_path=$1
    local timeout_seconds=$2
    local encoded_script request response guest_pid result elapsed exit_code

    encoded_script=$(iconv -f UTF-8 -t UTF-16LE "$script_path" | base64 -w0)
    request=$(jq -nc --arg encoded "$encoded_script" '{
        execute: "guest-exec",
        arguments: {
            path: "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
            arg: ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded],
            "capture-output": true
        }
    }')
    unset encoded_script
    response=$(vm_virsh qemu-agent-command "$VM_NAME" "$request")
    guest_pid=$(jq -er '.return.pid' <<<"$response")

    for ((elapsed = 0; elapsed < timeout_seconds; elapsed += 2)); do
        result=$(vm_virsh qemu-agent-command "$VM_NAME" \
            "{\"execute\":\"guest-exec-status\",\"arguments\":{\"pid\":$guest_pid}}")
        if jq -e '.return.exited == true' >/dev/null <<<"$result"; then
            jq -r '.return["out-data"] // empty' <<<"$result" | base64 -d
            jq -r '.return["err-data"] // empty' <<<"$result" | base64 -d >&2
            exit_code=$(jq -er '.return.exitcode' <<<"$result")
            return "$exit_code"
        fi
        sleep 2
    done

    printf 'Guest finalization timed out after %s seconds.\n' "$timeout_seconds" >&2
    return 124
}

for command_name in base64 iconv jq qemu-img ssh virt-xml; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'Missing required host command: %s\n' "$command_name" >&2
        exit 1
    fi
done
if [[ ! -r "$finalize_script" ]]; then
    printf 'Missing finalization script: %s\n' "$finalize_script" >&2
    exit 1
fi
if ! vm_virsh dominfo "$VM_NAME" >/dev/null 2>&1; then
    printf 'VM does not exist: %s\n' "$VM_NAME" >&2
    exit 1
fi

printf 'Waiting for the Windows guest agent.\n'
if ! wait_for_agent 900 2; then
    printf 'The guest agent did not become ready within 30 minutes.\n' >&2
    exit 1
fi

run_powershell_file "$finalize_script" 2700

guest_ip=$(get_vm_ip)
if [[ -z "$guest_ip" ]]; then
    printf 'Could not determine the guest IPv4 address.\n' >&2
    exit 1
fi

ssh_ready=false
for _ in {1..60}; do
    if ssh_vm "$guest_ip" 'exit 0' 2>/dev/null; then
        printf 'OpenSSH key authentication is ready at %s.\n' "$guest_ip"
        ssh_ready=true
        break
    fi
    sleep 2
done
if [[ "$ssh_ready" != true ]]; then
    printf 'OpenSSH did not accept key authentication at %s.\n' "$guest_ip" >&2
    exit 1
fi

domain_xml=$(vm_virsh dumpxml "$VM_NAME")
if ! grep -q "target dev='vda' bus='virtio'" <<<"$domain_xml"; then
    vm_mac=$(vm_virsh domiflist "$VM_NAME" | awk '$2 == "network" {print $5; exit}')
    if [[ -z "$vm_mac" ]]; then
        printf 'Could not determine the VM network MAC address.\n' >&2
        exit 1
    fi
    bind_disk="$(dirname "$DISK_IMAGE")/${VM_NAME}-virtio-bind.qcow2"
    if [[ -e "$bind_disk" ]]; then
        printf 'Temporary VirtIO binding disk already exists: %s\n' "$bind_disk" >&2
        exit 1
    fi

    printf 'Binding the VirtIO storage driver to a disposable disk.\n'
    sudo qemu-img create -q -f qcow2 "$bind_disk" 1G
    vm_virsh attach-disk "$VM_NAME" "$bind_disk" vdb \
        --targetbus virtio --subdriver qcow2 --live --config
    sleep 15
    "$script_dir/stop-vm.sh"

    vm_virsh detach-disk "$VM_NAME" vdb --config
    sudo virt-xml --connect "$LIBVIRT_URI" "$VM_NAME" \
        --edit target=sda --disk bus=virtio,target=vda,xpath1.delete=./address
    sudo virt-xml --connect "$LIBVIRT_URI" "$VM_NAME" \
        --edit mac="$vm_mac" --network model=virtio
    sudo /usr/bin/rm "$bind_disk"

    while read -r cdrom_target; do
        vm_virsh change-media "$VM_NAME" "$cdrom_target" --eject --config
    done < <(vm_virsh domblklist "$VM_NAME" --details | awk '$2 == "cdrom" && $4 != "-" {print $3}')

    vm_virsh start "$VM_NAME"
    if ! wait_for_agent 150 2; then
        printf 'The guest did not boot after the VirtIO conversion.\n' >&2
        exit 1
    fi
    guest_ip=$(get_vm_ip)
    ssh_vm "$guest_ip" 'exit 0'
fi

if ! vm_virsh snapshot-list "$VM_NAME" --name | grep -Fxq "$BASELINE_SNAPSHOT"; then
    printf 'Creating the %s snapshot.\n' "$BASELINE_SNAPSHOT"
    "$script_dir/stop-vm.sh"
    vm_virsh snapshot-create-as "$VM_NAME" "$BASELINE_SNAPSHOT" \
        --description 'Windows 11 GaleFling WebView test baseline; no platform logins' \
        --atomic

    start_seconds=$SECONDS
    vm_virsh snapshot-revert "$VM_NAME" "$BASELINE_SNAPSHOT"
    revert_seconds=$((SECONDS - start_seconds))
    if ((revert_seconds >= 60)); then
        printf 'Snapshot revert took %s seconds (expected under 60).\n' "$revert_seconds" >&2
        exit 1
    fi
    printf 'Snapshot revert completed in %s seconds.\n' "$revert_seconds"
    vm_virsh start "$VM_NAME"
    wait_for_agent 150 2
fi

printf 'VM %s is fully configured and running.\n' "$VM_NAME"
