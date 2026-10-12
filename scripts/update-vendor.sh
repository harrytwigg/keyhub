#!/usr/bin/env bash
# Re-vendor the Toshy runtime files keyhub needs from upstream.
# Usage: scripts/update-vendor.sh [git-ref]   (default: the ref pinned in UPSTREAM)
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
dest="$repo_root/src/keyhub/vendor/toshy"
pin_file="$dest/UPSTREAM"
ref="${1:-$(sed -n 's/^commit=//p' "$pin_file" 2>/dev/null || echo main)}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git clone -q https://github.com/RedBearAK/toshy.git "$work/toshy"
git -C "$work/toshy" checkout -q "$ref"
commit="$(git -C "$work/toshy" rev-parse HEAD)"

rm -rf "$dest"
mkdir -p "$dest"
cp "$work/toshy/default-toshy-config/toshy_config.py" "$dest/"
cp "$work/toshy/LICENSE" "$dest/"
cp -r "$work/toshy/toshy_common" "$work/toshy/assets" \
      "$work/toshy/kwin-dbus-service" "$work/toshy/kwin-script" "$dest/"
mkdir -p "$dest/scripts"
cp "$work/toshy/scripts/toshy-kwin-script-kickstart.sh" "$dest/scripts/"
rm -rf "$dest/toshy_common/_archived"
find "$dest" -name __pycache__ -type d -prune -exec rm -rf {} +

cat > "$pin_file" <<PIN
repo=https://github.com/RedBearAK/toshy
commit=$commit
PIN
echo "Vendored Toshy $commit into $dest"
