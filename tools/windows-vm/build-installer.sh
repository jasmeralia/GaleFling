#!/usr/bin/env bash
# Build a Windows executable and NSIS installer inside the Windows VM over
# SSH, for manual testing of a branch before it merges to master -- without
# creating a git tag or touching the release workflow.
#
# The version string is derived from `git describe` against whatever is
# currently checked out on the host (see scripts/write_version.py), so the
# build is clearly labeled as a dev build and never collides with a real
# release tag.
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source-path=SCRIPTDIR
# shellcheck source=lib.sh
source "$script_dir/lib.sh"

# See tools/windows-vm/run-tests.sh for why the guest builds from a copy
# rather than the VirtIO-FS share directly.
GUEST_PYTHON=${GUEST_PYTHON:-C:\\GaleFling-venv\\Scripts\\python.exe}
GUEST_SHARE=${GUEST_SHARE:-Z:\\}
GUEST_REPO=${GUEST_REPO:-C:\\GaleFling}

build_installer=1
revert_first=0
skip_sync=0

usage() {
    printf 'Usage: %s [--exe-only] [--revert] [--no-sync]\n' "$0" >&2
    printf '\n' >&2
    printf '  --exe-only   Build only the raw executable (dist/GaleFling.exe),\n' >&2
    printf '               skipping the NSIS installer stage below. Introduces no\n' >&2
    printf '               guest drift, so it needs no --revert.\n' >&2
    printf '  --revert     Revert to the %s snapshot before building, so the\n' "$BASELINE_SNAPSHOT" >&2
    printf '               build starts from identical state. Discards newer\n' >&2
    printf '               guest changes, including any prior installer-stage drift.\n' >&2
    printf '  --no-sync    Skip refreshing the guest copy of the repository.\n' >&2
    printf '\n' >&2
    printf 'By default, also builds the NSIS installer (GaleFling-Setup-*.exe), not\n' >&2
    printf 'just the raw executable. This bootstraps Chocolatey from the official\n' >&2
    printf 'https://community.chocolatey.org installer and installs NSIS on the\n' >&2
    printf 'guest if neither is already present -- this drifts the guest away from\n' >&2
    printf 'the %s snapshot. Pair it with --revert, or run\n' "$BASELINE_SNAPSHOT" >&2
    printf 'snapshot-vm.sh revert yourself afterward.\n' >&2
    printf '\n' >&2
    printf 'The raw executable (dist/GaleFling.exe) and, unless --exe-only is\n' >&2
    printf "given, the installer (build/GaleFling-Setup-*.exe) land directly in\n" >&2
    printf "this repo's own dist/ and build/ directories (both gitignored) via\n" >&2
    printf 'the VirtIO-FS share -- no manual copy needed.\n' >&2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --exe-only)
            build_installer=0
            shift
            ;;
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
        *)
            usage
            exit 2
            ;;
    esac
done

# robocopy /MIR deletes whatever is in the destination but not the source, so a
# destination equal to the source would mirror the live share onto itself.
if [[ $skip_sync -eq 0 && "${GUEST_REPO%\\}" == "${GUEST_SHARE%\\}" ]]; then
    printf 'GUEST_REPO must differ from GUEST_SHARE (%s): syncing a share onto\n' "$GUEST_SHARE" >&2
    printf 'itself would mirror it with robocopy /MIR. Pass --no-sync to build\n' >&2
    printf 'directly from the share instead.\n' >&2
    exit 2
fi

# Regenerate the dev version on the host, from whatever branch/commit is
# actually checked out here, so the guest build picks up a real
# git-describe-derived label (the guest copy excludes .git, so it cannot
# derive one itself). _version.py is gitignored and carried over by the
# ordinary repo sync below like any other working-tree file.
printf 'Writing dev version from git describe.\n'
python3 "$REPO_DIR/scripts/write_version.py" --root "$REPO_DIR"

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

sync_block=''
if [[ $skip_sync -eq 0 ]]; then
    # /MIR mirrors deletions too, so a file removed on the host disappears in
    # the guest. .env is excluded deliberately -- functional-test credentials
    # have no business anywhere near a build artifact.
    sync_block=$(
        cat <<EOF
Write-Output 'Syncing repository to $GUEST_REPO.'
& robocopy.exe $(ps_quote "$GUEST_SHARE") $(ps_quote "$GUEST_REPO") /MIR /XD $(ps_quote "${GUEST_SHARE}.git") $(ps_quote "${GUEST_SHARE}.venv") /XF '.env' 'logs' /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
if (\$LASTEXITCODE -ge 8) { throw "robocopy failed with exit code \$LASTEXITCODE." }
EOF
    )
fi

installer_block=''
if [[ $build_installer -eq 1 ]]; then
    installer_block=$(
        cat <<'EOF'
$nsisX86 = "${env:ProgramFiles(x86)}\NSIS\makensis.exe"
$nsisX64 = "${env:ProgramFiles}\NSIS\makensis.exe"
$nsis = $null
if (Test-Path $nsisX86) { $nsis = $nsisX86 }
elseif (Test-Path $nsisX64) { $nsis = $nsisX64 }
if (-not $nsis) {
    if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
        Write-Output 'Bootstrapping Chocolatey from community.chocolatey.org.'
        Set-ExecutionPolicy Bypass -Scope Process -Force
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    }
    Write-Output 'Installing NSIS via Chocolatey.'
    choco install nsis -y | Out-Null
    if (Test-Path $nsisX86) { $nsis = $nsisX86 }
    elseif (Test-Path $nsisX64) { $nsis = $nsisX64 }
    if (-not $nsis) { throw 'NSIS install reported success but makensis.exe was not found.' }
}
Write-Output 'Building the NSIS installer.'
& $nsis build\installer.nsi
if ($LASTEXITCODE -ne 0) { throw "makensis failed with exit code $LASTEXITCODE." }
Write-Output 'Copying the installer back to the host via the share.'
New-Item -ItemType Directory -Force -Path 'Z:\build' | Out-Null
Copy-Item build\GaleFling-Setup-*.exe 'Z:\build\' -Force
EOF
    )
fi

remote_command=$(
    cat <<EOF
\$ErrorActionPreference = 'Stop'
\$ProgressPreference = 'SilentlyContinue'
$sync_block
Set-Location $(ps_quote "$GUEST_REPO")
Write-Output 'Building the executable with PyInstaller.'
& $(ps_quote "$GUEST_PYTHON") -m PyInstaller build\\build.spec --distpath dist\\ --workpath build\\tmp --clean
if (\$LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code \$LASTEXITCODE." }
Write-Output 'Copying the executable back to the host via the share.'
New-Item -ItemType Directory -Force -Path 'Z:\\dist' | Out-Null
Copy-Item dist\\GaleFling.exe 'Z:\\dist\\' -Force
$installer_block
exit 0
EOF
)

# Windows OpenSSH joins argv into one command line, which mangles a multi-line
# -Command payload and silently runs nothing at all (exiting 0). Base64
# UTF-16LE via -EncodedCommand is immune to that.
encoded_command=$(printf '%s' "$remote_command" | iconv -f UTF-8 -t UTF-16LE | base64 -w0)

printf 'Building in %s (%s)%s\n' "$VM_NAME" "$guest_ip" "$([[ $build_installer -eq 1 ]] && printf ' (exe + installer)' || printf ' (exe only)')"
set +e
ssh_vm "$guest_ip" powershell -NoProfile -NonInteractive -EncodedCommand "$encoded_command"
exit_code=$?
set -e

if [[ $exit_code -ne 0 ]]; then
    printf '\nBuild failed in the guest (exit %s).\n' "$exit_code" >&2
    exit "$exit_code"
fi

printf '\nBuilt: %s/dist/GaleFling.exe\n' "$REPO_DIR"
if [[ $build_installer -eq 1 ]]; then
    printf 'Built: %s/build/GaleFling-Setup-*.exe\n' "$REPO_DIR"
    printf '\nThe installer stage drifted the guest (Chocolatey/NSIS install).\n' >&2
    printf 'Revert the baseline before relying on it for functional-test\n' >&2
    printf 'isolation again:\n' >&2
    printf '  %s/snapshot-vm.sh revert %s\n' "$script_dir" "$BASELINE_SNAPSHOT" >&2
fi
printf '\nStop the VM when done: %s/stop-vm.sh\n' "$script_dir"
