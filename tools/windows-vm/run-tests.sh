#!/usr/bin/env bash
# Run the functional test suite inside the Windows VM over SSH.
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib.sh
source "$script_dir/lib.sh"

# The guest runs from a copy rather than the VirtIO-FS share: the repository's
# `logs` entry is an absolute Linux symlink that Windows cannot represent, and
# pytest's rootdir scan fails on it with WinError 123 before any test runs.
# The copy is re-synced on every run so it is never stale.
GUEST_PYTHON=${GUEST_PYTHON:-C:\\GaleFling-venv\\Scripts\\python.exe}
GUEST_SHARE=${GUEST_SHARE:-Z:\\}
GUEST_REPO=${GUEST_REPO:-C:\\GaleFling}
# The host's .env carries a GALEFLING_DATA_DIR that only exists on the host, so
# WebView tests would skip with "GALEFLING_DATA_DIR does not exist" rather than
# testing anything.  Point them at the guest's own profile directory instead.
GUEST_DATA_DIR=${GUEST_DATA_DIR:-C:\\Users\\$VM_USER\\AppData\\Roaming\\GaleFling}

revert_first=0
skip_sync=0

usage() {
    printf 'Usage: %s [--revert] [--no-sync] [pytest arguments...]\n' "$0" >&2
    printf '\n' >&2
    printf '  --revert    Revert to the %s snapshot before running, so the run\n' "$BASELINE_SNAPSHOT" >&2
    printf '              starts from identical state. Discards newer guest changes,\n' >&2
    printf '              including any session logged in by hand.\n' >&2
    printf '  --no-sync   Skip refreshing the guest copy of the repository.\n' >&2
    printf '\n' >&2
    printf 'Without pytest arguments the whole functional suite runs. Examples:\n' >&2
    printf '  %s tests/functional/test_media_processing.py\n' "$0" >&2
    printf '  %s -k composer -x\n' "$0" >&2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --revert)
            revert_first=1
            shift
            ;;
        --no-sync)
            skip_sync=1
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        *)
            break
            ;;
    esac
done

pytest_args=("$@")
if [[ ${#pytest_args[@]} -eq 0 ]]; then
    pytest_args=(tests/functional -m functional)
fi
pytest_args+=(-v --no-header)

if [[ $revert_first -eq 1 ]]; then
    "$script_dir/snapshot-vm.sh" revert "$BASELINE_SNAPSHOT"
else
    "$script_dir/start-vm.sh"
fi

guest_ip=$(get_vm_ip)
if [[ -z "$guest_ip" ]]; then
    printf 'Could not determine the IP address of VM %s.\n' "$VM_NAME" >&2
    exit 1
fi

# Quote for PowerShell: wrap in single quotes, doubling any embedded quote.
ps_quote() {
    printf "'%s'" "${1//\'/\'\'}"
}

quoted_args=''
for arg in "${pytest_args[@]}"; do
    quoted_args+=" $(ps_quote "$arg")"
done

sync_block=''
if [[ $skip_sync -eq 0 ]]; then
    # /MIR mirrors deletions too, so a file removed on the host disappears in the
    # guest.  .env is excluded deliberately — credentials are read from the share
    # at run time so they never land on the guest disk, where a snapshot taken
    # later would preserve them indefinitely.
    sync_block=$(
        cat <<EOF
& robocopy.exe $(ps_quote "$GUEST_SHARE") $(ps_quote "$GUEST_REPO") /MIR /XD $(ps_quote "${GUEST_SHARE}.git") $(ps_quote "${GUEST_SHARE}.venv") /XF '.env' 'logs' /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
if (\$LASTEXITCODE -ge 8) { throw "robocopy failed with exit code \$LASTEXITCODE." }
EOF
    )
fi

# GALEFLING_STRICT_FUNCTIONAL: report environment gaps as failures rather than
#   skips, matching test-functional-linux.  A silently skipped suite in a VM
#   nobody is watching is indistinguishable from a passing one.
# GALEFLING_FUNCTIONAL_ENV: read credentials from the host share, so they are
#   never written to the guest disk.
# -p no:cacheprovider: the cache is worthless for a one-shot run.
remote_command=$(
    cat <<EOF
\$ErrorActionPreference = 'Stop'
\$ProgressPreference = 'SilentlyContinue'
$sync_block
Set-Location $(ps_quote "$GUEST_REPO")
\$env:GALEFLING_STRICT_FUNCTIONAL = '1'
\$env:GALEFLING_FUNCTIONAL_ENV = $(ps_quote "${GUEST_SHARE}tests\\functional\\.env")
# Set before load_dotenv runs; python-dotenv does not override a value that is
# already present in the environment, so this wins over the host's .env entry.
\$env:GALEFLING_DATA_DIR = $(ps_quote "$GUEST_DATA_DIR")
New-Item -ItemType Directory -Force -Path $(ps_quote "$GUEST_DATA_DIR") | Out-Null
& $(ps_quote "$GUEST_PYTHON") -m pytest -p no:cacheprovider$quoted_args
exit \$LASTEXITCODE
EOF
)

# Windows OpenSSH joins argv into one command line, which mangles a multi-line
# -Command payload and silently runs nothing at all (exiting 0).  Base64
# UTF-16LE via -EncodedCommand is immune to that.
encoded_command=$(printf '%s' "$remote_command" | iconv -f UTF-8 -t UTF-16LE | base64 -w0)

printf 'Running functional tests in %s (%s)\n' "$VM_NAME" "$guest_ip"
set +e
ssh_vm "$guest_ip" powershell -NoProfile -NonInteractive -EncodedCommand "$encoded_command"
exit_code=$?
set -e

if [[ $exit_code -ne 0 ]]; then
    printf '\nFunctional tests failed in the guest (exit %s).\n' "$exit_code" >&2
fi
exit "$exit_code"
