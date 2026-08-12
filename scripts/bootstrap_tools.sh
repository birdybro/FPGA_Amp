#!/usr/bin/env bash
set -euo pipefail

# Non-root convenience bootstrap for Arch-family development hosts. CI and
# packaged environments may install these tools normally instead.
repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tool_root="$repository_root/.tools/root"
package_cache="$repository_root/.tools/packages"
mkdir -p "$tool_root" "$package_cache"

if ! command -v pacman >/dev/null 2>&1; then
    echo "bootstrap_tools.sh currently supports pacman hosts; install ngspice and yosys manually" >&2
    exit 2
fi

download_and_extract() {
    local package_name=$1
    local package_url
    local archive
    package_url=$(pacman -Sp --print-format '%l' "$package_name" | tail -n 1)
    archive="$package_cache/${package_url##*/}"
    if [[ ! -f "$archive" ]]; then
        curl -L --fail --show-error "$package_url" -o "$archive"
    fi
    bsdtar -xf "$archive" -C "$tool_root"
}

download_and_extract ngspice
download_and_extract abc
download_and_extract yosys

echo "Tools extracted under $tool_root"
echo "Use: PATH=$tool_root/usr/bin:\$PATH make spice rtl"

