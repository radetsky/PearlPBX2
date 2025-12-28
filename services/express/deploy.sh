#!/bin/bash
# Express FastAGI - Remote Deployment Script

set -e

REMOTE_HOST="${1}"
REMOTE_USER="${2:-root}"
INSTALL_DIR="/opt/express-fastagi"

if [ -z "$REMOTE_HOST" ]; then
    echo "Usage: $0 <remote_host> [remote_user]"
    echo "Example: $0 192.168.1.100 root"
    exit 1
fi

echo "=========================================="
echo "Express FastAGI - Remote Deployment"
echo "=========================================="
echo "Remote Host: $REMOTE_HOST"
echo "Remote User: $REMOTE_USER"
echo ""

# Create temporary directory
TEMP_DIR=$(mktemp -d)
echo "Packaging files..."

# Copy files
cp express_fastagi.py "$TEMP_DIR/"
cp requirements.txt "$TEMP_DIR/"
cp .env.example "$TEMP_DIR/"
cp install.sh "$TEMP_DIR/"
cp express-fastagi.service "$TEMP_DIR/"
cp README.md "$TEMP_DIR/"
cp QUICKSTART.md "$TEMP_DIR/"
cp test_service.py "$TEMP_DIR/"

# Create archive
cd "$TEMP_DIR"
tar czf express-fastagi.tar.gz *
mv express-fastagi.tar.gz /tmp/

echo "✓ Files packaged: /tmp/express-fastagi.tar.gz"

# Copy to remote server
echo ""
echo "Copying to $REMOTE_HOST..."
scp /tmp/express-fastagi.tar.gz $REMOTE_USER@$REMOTE_HOST:/tmp/

# Extract and install on remote server
echo ""
echo "Installing on remote server..."
ssh $REMOTE_USER@$REMOTE_HOST << 'ENDSSH'
cd /tmp
mkdir -p express-fastagi-install
cd express-fastagi-install
tar xzf ../express-fastagi.tar.gz
chmod +x install.sh
echo ""
echo "Running install.sh on remote server..."
echo "=============================================="
./install.sh
ENDSSH

echo ""
echo "=========================================="
echo "Deployment completed!"
echo "=========================================="
echo ""
echo "Next steps on server $REMOTE_HOST:"
echo ""
echo "1. SSH to server:"
echo "   ssh $REMOTE_USER@$REMOTE_HOST"
echo ""
echo "2. Configure service:"
echo "   nano $INSTALL_DIR/.env"
echo ""
echo "3. Start service:"
echo "   systemctl start express-fastagi"
echo "   systemctl enable express-fastagi"
echo ""
echo "4. Check status:"
echo "   systemctl status express-fastagi"
echo "   journalctl -u express-fastagi -f"
echo ""

# Cleanup
rm -rf "$TEMP_DIR"
rm /tmp/express-fastagi.tar.gz

echo "=========================================="
