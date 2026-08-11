#!/usr/bin/env bash
# Run a command with display variables borrowed from the live KDE session.
set -euo pipefail

target_user="${DESKTOP_SESSION_USER:-$(id -un)}"
candidates=(plasmashell kwin_wayland startplasma-wayland)
session_pid=""

for name in "${candidates[@]}"; do
    pid="$(pgrep -u "$target_user" -x "$name" | head -n1 || true)"
    if [[ -n "$pid" ]] && [[ -r "/proc/$pid/environ" ]]; then
        session_pid="$pid"
        break
    fi
done

if [[ -z "$session_pid" ]]; then
    echo "run-with-desktop-session: no graphical session found for $target_user." >&2
    exit 1
fi

get_env_var() {
    local var="$1"
    tr '\0' '\n' < "/proc/$session_pid/environ" | sed -n "s/^${var}=//p"
}

display_val="$(get_env_var DISPLAY)"
wayland_display_val="$(get_env_var WAYLAND_DISPLAY)"
xauthority_val="$(get_env_var XAUTHORITY)"
xdg_runtime_dir_val="$(get_env_var XDG_RUNTIME_DIR)"
dbus_session_bus_address_val="$(get_env_var DBUS_SESSION_BUS_ADDRESS)"

if [[ -z "$display_val" || -z "$xdg_runtime_dir_val" ]]; then
    echo "run-with-desktop-session: graphical session is missing DISPLAY or XDG_RUNTIME_DIR." >&2
    exit 1
fi

export DISPLAY="$display_val"
export XDG_RUNTIME_DIR="$xdg_runtime_dir_val"
[[ -n "$wayland_display_val" ]] && export WAYLAND_DISPLAY="$wayland_display_val"
[[ -n "$xauthority_val" ]] && export XAUTHORITY="$xauthority_val"
[[ -n "$dbus_session_bus_address_val" ]] && \
    export DBUS_SESSION_BUS_ADDRESS="$dbus_session_bus_address_val"

echo "run-with-desktop-session: using graphical session from pid $session_pid."
exec "$@"
