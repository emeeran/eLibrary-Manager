#!/usr/bin/env bash
# setup_nas_mount.sh — Interactive NAS mount setup for Dawnstar eBook Manager
#
# This script configures an SMB/CIFS mount for your Synology NAS.
# Run it once to set up persistent mounting via /etc/fstab.
#
# Usage: ./scripts/setup_nas_mount.sh

set -euo pipefail

echo "=== Dawnstar NAS Mount Setup ==="
echo ""

# Check for cifs-utils
if ! command -v mount.cifs &>/dev/null; then
    echo "Installing cifs-utils..."
    sudo apt-get update -qq && sudo apt-get install -y -qq cifs-utils
fi

# Collect NAS details
read -rp "NAS IP address [192.168.1.100]: " NAS_HOST
NAS_HOST="${NAS_HOST:-192.168.1.100}"

read -rp "Share name [ebook_library]: " NAS_SHARE
NAS_SHARE="${NAS_SHARE:-ebook_library}"

read -rp "Local mount point [/mnt/nas/ebooks]: " MOUNT_POINT
MOUNT_POINT="${MOUNT_POINT:-/mnt/nas/ebooks}"

read -rp "NAS username: " NAS_USER
read -rsp "NAS password: " NAS_PASS
echo ""

# Create mount point
sudo mkdir -p "$MOUNT_POINT"

# Create credentials file
CRED_FILE="/etc/.smbcredentials-dawnstar"
echo "username=$NAS_USER" | sudo tee "$CRED_FILE" > /dev/null
echo "password=$NAS_PASS" | sudo tee -a "$CRED_FILE" > /dev/null
sudo chmod 600 "$CRED_FILE"

# Get current user UID/GID
USER_UID=$(id -u)
USER_GID=$(id -g)

# Add fstab entry if not already present
FSTAB_ENTRY="//$NAS_HOST/$NAS_SHARE $MOUNT_POINT cifs credentials=$CRED_FILE,uid=$USER_UID,gid=$USER_GID,iocharset=utf8,sec=ntlmssp,_netdev,vers=3.0 0 0"

if grep -q "$MOUNT_POINT" /etc/fstab 2>/dev/null; then
    echo "fstab entry for $MOUNT_POINT already exists. Skipping."
else
    echo "$FSTAB_ENTRY" | sudo tee -a /etc/fstab > /dev/null
    echo "Added fstab entry."
fi

# Mount
echo "Mounting $MOUNT_POINT..."
sudo mount "$MOUNT_POINT" 2>/dev/null || sudo mount -a

# Verify
if mountpoint -q "$MOUNT_POINT"; then
    FILE_COUNT=$(find "$MOUNT_POINT" -type f | wc -l)
    echo ""
    echo "SUCCESS: NAS mounted at $MOUNT_POINT"
    echo "Found $FILE_COUNT files in the share."
    echo ""
    echo "In Dawnstar Settings > NAS Storage, use:"
    echo "  Host:        $NAS_HOST"
    echo "  Share:       $NAS_SHARE"
    echo "  Mount Path:  $MOUNT_POINT"
else
    echo "ERROR: Mount failed. Check your NAS IP, share name, and credentials."
    exit 1
fi

echo ""
echo "=== Remote Access Tip ==="
echo "For access outside your local network, consider:"
echo "  - Tailscale (https://tailscale.com) — zero-config VPN"
echo "  - WireGuard — lightweight VPN, Synology package available"
echo ""
echo "Once VPN is active, the SMB mount works from any network."
