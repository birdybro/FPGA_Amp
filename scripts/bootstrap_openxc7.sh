#!/usr/bin/env bash
set -euo pipefail

# Reproducible non-root build of the experimental open XC7 place/route tool.
repository_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tool_root="$repository_root/.tools/root"
package_cache="$repository_root/.tools/packages"
source_root="$repository_root/.tools/src"
build_root="$repository_root/.tools/build/nextpnr-himbaechel-xc7-artix"
prjxray_build_root="$repository_root/.tools/build/prjxray"
python_environment="$repository_root/.tools/openxc7-venv"
nextpnr_commit=4d235150266df2fa5c2c6102c67aa16ff34e6469
prjxray_db_commit=0a0addedd73e7e4139d52a6d8db4258763e0f1f3
prjxray_commit=c9f02d8576042325425824647ab5555b1bc77833

if ! command -v pacman >/dev/null 2>&1; then
    echo "bootstrap_openxc7.sh currently supports pacman hosts" >&2
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

mkdir -p "$tool_root" "$package_cache" "$source_root" "$build_root" \
    "$prjxray_build_root"
download_and_extract boost
download_and_extract boost-libs
download_and_extract eigen

if [[ ! -d "$source_root/nextpnr/.git" ]]; then
    git clone https://github.com/YosysHQ/nextpnr.git "$source_root/nextpnr"
fi
git -C "$source_root/nextpnr" fetch origin "$nextpnr_commit"
git -C "$source_root/nextpnr" checkout --detach "$nextpnr_commit"
git -C "$source_root/nextpnr" submodule update --init --recursive

if [[ ! -d "$source_root/prjxray-db/.git" ]]; then
    git clone https://github.com/f4pga/prjxray-db.git "$source_root/prjxray-db"
fi
git -C "$source_root/prjxray-db" fetch origin "$prjxray_db_commit"
git -C "$source_root/prjxray-db" checkout --detach "$prjxray_db_commit"

if [[ ! -d "$source_root/prjxray/.git" ]]; then
    git clone https://github.com/f4pga/prjxray.git "$source_root/prjxray"
fi
git -C "$source_root/prjxray" fetch origin "$prjxray_commit"
git -C "$source_root/prjxray" checkout --detach "$prjxray_commit"
git -C "$source_root/prjxray" submodule update --init --recursive

cmake -S "$source_root/nextpnr" -B "$build_root" -G Ninja \
    -DARCH=himbaechel \
    -DHIMBAECHEL_UARCH=xilinx \
    -DHIMBAECHEL_XILINX_DEVICES='xc7a100t;xc7a200t' \
    -DHIMBAECHEL_PRJXRAY_DB="$source_root/prjxray-db" \
    -DBUILD_GUI=OFF \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$tool_root/usr" \
    -DCMAKE_PREFIX_PATH="$tool_root/usr"
build_jobs=$(nproc)
if ((build_jobs > 8)); then
    build_jobs=8
fi
cmake --build "$build_root" --target nextpnr-himbaechel -j "$build_jobs"
cmake --install "$build_root"

# Project X-Ray's pinned headers predate modern libstdc++ transitive-include
# cleanup, so force the missing standard integer header without modifying the
# external checkout. CMake 4 also requires an explicit compatibility floor for
# two old third-party CMakeLists files.
cmake -S "$source_root/prjxray" -B "$prjxray_build_root" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$tool_root/usr" \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DCMAKE_CXX_FLAGS='-include cstdint'
cmake --build "$prjxray_build_root" --target install -j "$build_jobs"

python3 -m venv "$python_environment"
"$python_environment/bin/python" -m pip install --disable-pip-version-check \
    'textX==4.4.0' \
    'intervaltree==3.2.1' \
    'simplejson==4.1.1' \
    'PyYAML==6.0.3'

echo "Open XC7 implementation tools installed under $tool_root/usr"
echo "Run: make openxc7-probe"
