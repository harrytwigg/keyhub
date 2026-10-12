#!/usr/bin/env bash
# Install keyhub into its own venv and hand it the keyboard.
# Undo with: keyhub restore
set -euo pipefail

repo="$(cd "$(dirname "$0")" && pwd)"
venv="${XDG_DATA_HOME:-$HOME/.local/share}/keyhub/venv"

python3 -m venv "$venv"
"$venv/bin/pip" install --quiet --upgrade pip
"$venv/bin/pip" install --quiet "$repo"

mkdir -p "$HOME/.local/bin"
ln -sf "$venv/bin/keyhub" "$HOME/.local/bin/keyhub"

"$venv/bin/keyhub" setup
