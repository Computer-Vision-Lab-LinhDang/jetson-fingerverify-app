#!/usr/bin/env bash
# Install Litestream and enable continuous replication of data/mdgt_edge.db.
#
# Usage (as root, on the Jetson):
#   sudo bash scripts/install_litestream.sh
#
# After install:
#   sudo vi /etc/default/mdgt-litestream     # fill in bucket + credentials
#   sudo systemctl restart mdgt-litestream
#   sudo systemctl status  mdgt-litestream

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LITESTREAM_VERSION="${LITESTREAM_VERSION:-0.3.13}"

ARCH_RAW="$(uname -m)"
case "$ARCH_RAW" in
    x86_64)  ARCH="amd64" ;;
    aarch64) ARCH="arm64" ;;
    armv7l)  ARCH="arm7"  ;;
    *)
        echo "Unsupported architecture: $ARCH_RAW" >&2
        exit 1
        ;;
esac

if [[ $EUID -ne 0 ]]; then
    echo "Please run as root (sudo)." >&2
    exit 1
fi

# --- 1. Download Litestream binary -----------------------------------------
if ! command -v litestream >/dev/null 2>&1; then
    tmp="$(mktemp -d)"
    url="https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-v${LITESTREAM_VERSION}-linux-${ARCH}.tar.gz"
    echo "[litestream] downloading $url"
    curl -fsSL "$url" -o "$tmp/litestream.tgz"
    tar -xzf "$tmp/litestream.tgz" -C "$tmp"
    install -m 0755 "$tmp/litestream" /usr/local/bin/litestream
    rm -rf "$tmp"
else
    echo "[litestream] already installed: $(litestream version)"
fi

# --- 2. Install config + systemd unit --------------------------------------
install -m 0644 "$REPO_ROOT/deploy/litestream.yml"           /etc/litestream.yml
install -m 0644 "$REPO_ROOT/deploy/mdgt-litestream.service"  /etc/systemd/system/mdgt-litestream.service

if [[ ! -f /etc/default/mdgt-litestream ]]; then
    install -m 0600 "$REPO_ROOT/deploy/mdgt-litestream.env.example" /etc/default/mdgt-litestream
    echo "[litestream] wrote /etc/default/mdgt-litestream — EDIT IT before starting the service."
else
    echo "[litestream] /etc/default/mdgt-litestream already exists — leaving untouched."
fi

systemctl daemon-reload
systemctl enable mdgt-litestream.service

cat <<EOF

=============================================================================
Litestream installed.  Next steps:

  1. Edit credentials + bucket:
       sudo vi /etc/default/mdgt-litestream

  2. Start the replicator:
       sudo systemctl restart mdgt-litestream
       sudo systemctl status  mdgt-litestream
       sudo journalctl -u mdgt-litestream -f

  3. Verify the replica:
       litestream snapshots -config /etc/litestream.yml /opt/mdgt-edge/data/mdgt_edge.db

  4. Restore (on a fresh machine):
       litestream restore -config /etc/litestream.yml -o /tmp/restored.db \\
                          /opt/mdgt-edge/data/mdgt_edge.db
=============================================================================
EOF
