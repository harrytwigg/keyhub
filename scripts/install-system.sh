#!/usr/bin/env bash
# System-wide permissions keyhub needs (run with sudo). Makes keyhub independent
# of Toshy's installer: keyboards readable and /dev/uinput writable by 'input'.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }

repo="$(cd "$(dirname "$0")/.." && pwd)"
user="${SUDO_USER:?run with sudo from your own account}"

install -m 0644 "$repo/packaging/70-keyhub-input.rules" /etc/udev/rules.d/70-keyhub-input.rules
install -m 0644 "$repo/packaging/keyhub-uinput.conf" /etc/modules-load.d/keyhub-uinput.conf
modprobe uinput
getent group input >/dev/null || groupadd --system input
usermod -aG input "$user"
udevadm control --reload-rules
udevadm trigger --subsystem-match=input --subsystem-match=misc --action=change
echo "keyhub: udev rules installed; $user is in the 'input' group"
