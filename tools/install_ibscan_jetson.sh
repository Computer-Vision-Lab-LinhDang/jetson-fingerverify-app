#!/usr/bin/env bash
# Install Integrated Biometrics IBScanUltimate runtime on Jetson / aarch64.
#
# Usage:
#   sudo bash tools/install_ibscan_jetson.sh /path/to/IBScanUltimate_arm_package
#
# The provided SDK directory must contain:
#   lib/aarch64-linux-gnu/libIBScanUltimate.so
# and the matching runtime dependencies such as libAKXUS.so* and libuvc.so*.

set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run as root: sudo bash $0 /path/to/IBScanUltimate_sdk"
  exit 1
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: sudo bash $0 /path/to/IBScanUltimate_sdk"
  exit 1
fi

SDK_ROOT="$(python3 - "$1" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1]).expanduser().resolve()
candidates = [root]
candidates.extend(p for p in root.iterdir() if p.is_dir())

for candidate in candidates:
    libdir = candidate / "lib" / "aarch64-linux-gnu"
    if libdir.is_dir():
        print(candidate)
        break
else:
    print(root)
PY
)"

LIB_DIR="${SDK_ROOT}/lib/aarch64-linux-gnu"
PLUGIN_DIR="${SDK_ROOT}/Plugin/lib/aarch64-linux-gnu"
INSTALL_DIR="/opt/IBScanUltimate/lib"

if [[ ! -d "${LIB_DIR}" ]]; then
  echo "No aarch64 runtime found under: ${SDK_ROOT}"
  echo "Expected directory: ${LIB_DIR}"
  echo "This usually means you have the wrong SDK package (for example x64 instead of ARM)."
  exit 2
fi

if [[ ! -f "${LIB_DIR}/libIBScanUltimate.so" ]]; then
  echo "Missing ${LIB_DIR}/libIBScanUltimate.so"
  exit 2
fi

ARCH_INFO="$(file "${LIB_DIR}/libIBScanUltimate.so")"
echo "Detected library: ${ARCH_INFO}"
if ! grep -qi "aarch64\|arm64\|ARM aarch64" <<<"${ARCH_INFO}"; then
  echo "Refusing to install non-aarch64 library."
  exit 3
fi

mkdir -p "${INSTALL_DIR}"

echo "Installing IBScan runtime into ${INSTALL_DIR}"
cp -f "${LIB_DIR}/libIBScanUltimate.so" "${INSTALL_DIR}/"

for pattern in libAKXUS.so libAKXUS.so.* libuvc.so libuvc.so.* libIBScanUltimateJNI.so libLiveFinger2.so; do
  for file in "${LIB_DIR}"/${pattern}; do
    [[ -e "${file}" ]] || continue
    cp -f "${file}" "${INSTALL_DIR}/"
  done
done

if [[ -d "${PLUGIN_DIR}" ]]; then
  for file in "${PLUGIN_DIR}"/libIBScanNFIQ2.so; do
    [[ -e "${file}" ]] || continue
    cp -f "${file}" "${INSTALL_DIR}/"
  done
fi

echo "/opt/IBScanUltimate/lib" > /etc/ld.so.conf.d/ibscan.conf
ldconfig

cat > /etc/udev/rules.d/99-fingerprint.rules <<'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="113f", ATTR{idProduct}=="1500", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="113f", ATTR{idProduct}=="1500", ENV{UDISKS_IGNORE}="1"
SUBSYSTEM=="usb", ATTR{idVendor}=="0483", ATTR{idProduct}=="5720", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="0483", ATTR{idProduct}=="5720", ENV{UDISKS_IGNORE}="1"
EOF

udevadm control --reload-rules
udevadm trigger

echo
echo "Installed files:"
find "${INSTALL_DIR}" -maxdepth 1 -type f | sort
echo
echo "Next steps:"
echo "1. Replug the sensor."
echo "2. Ensure your user is in the plugdev group."
echo "3. Start the app with: export MDGT_IBSCAN_LIB_DIR=${INSTALL_DIR}"
