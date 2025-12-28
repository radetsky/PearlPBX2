#!/bin/bash
# Express FastAGI Service - Installation Script for Debian

set -e

echo "=========================================="
echo "Express FastAGI Service - Installation"
echo "=========================================="

# Check root privileges
if [ "$EUID" -ne 0 ]; then 
    echo "Error: Run this script as root (sudo)"
    exit 1
fi

# Configuration
INSTALL_DIR="/opt/express-fastagi"
SERVICE_FILE="/etc/systemd/system/express-fastagi.service"
FASTAGI_PORT=4574

echo ""
echo "1. Creating installation directory..."
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

echo ""
echo "2. Copying files..."
if [ -f "express_fastagi.py" ]; then
    cp -v express_fastagi.py "$INSTALL_DIR/"
    cp -v requirements.txt "$INSTALL_DIR/"
    cp -v .env.example "$INSTALL_DIR/.env"
else
    echo "Error: Files not found in current directory"
    echo "Please run this script from the express-fastagi directory"
    exit 1
fi

echo ""
echo "3. Installing Python dependencies..."
# Check for python3-venv
if ! dpkg -l | grep -q python3-venv; then
    echo "Installing python3-venv..."
    apt-get update
    apt-get install -y python3-venv python3-pip
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Install packages
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "4. Setting up permissions..."
chown -R asterisk:asterisk "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/express_fastagi.py"

echo ""
echo "5. Installing systemd service..."
cp -v express-fastagi.service "$SERVICE_FILE"
systemctl daemon-reload

echo ""
echo "6. Configuring firewall (iptables)..."

# Check if iptables is installed
if ! command -v iptables &> /dev/null; then
    echo "Installing iptables..."
    apt-get install -y iptables iptables-persistent
fi

# Add iptables rule for FastAGI port
echo "Adding iptables rule for port $FASTAGI_PORT..."

# Check if rule already exists
if ! iptables -C INPUT -p tcp --dport $FASTAGI_PORT -j ACCEPT 2>/dev/null; then
    iptables -I INPUT -p tcp --dport $FASTAGI_PORT -j ACCEPT
    echo "✓ iptables rule added"
else
    echo "✓ iptables rule already exists"
fi

# Save iptables rules
echo "Saving iptables rules..."
if command -v netfilter-persistent &> /dev/null; then
    netfilter-persistent save
    echo "✓ Rules saved with netfilter-persistent"
elif command -v iptables-save &> /dev/null; then
    iptables-save > /etc/iptables/rules.v4
    echo "✓ Rules saved to /etc/iptables/rules.v4"
else
    echo "⚠ Warning: Could not save iptables rules permanently"
    echo "  Rules will be lost after reboot"
    echo "  Install iptables-persistent: apt-get install iptables-persistent"
fi

echo ""
echo "=========================================="
echo "Installation completed!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Edit configuration:"
echo "   nano $INSTALL_DIR/.env"
echo ""
echo "2. Set required parameters:"
echo "   - DEFAULT_EXPRESS_URL (mandatory!)"
echo "   - DEFAULT_EXPRESS_PROVIDER"
echo "   - DEFAULT_EXPRESS_CLASS"
echo ""
echo "3. Start the service:"
echo "   systemctl start express-fastagi"
echo "   systemctl enable express-fastagi"
echo ""
echo "4. Check status:"
echo "   systemctl status express-fastagi"
echo "   journalctl -u express-fastagi -f"
echo ""
echo "5. Configure Asterisk extensions.conf:"
echo "   exten => _X.,1,Set(EXPRESS_PROVIDER=provider_id)"
echo "   same => n,Set(EXPRESS_CLASS=1)"
echo "   same => n,Set(EXPRESS_URL=http://ip:port/YTaxi/ru/ManagePBX/IncomingCall)"
echo "   same => n,Queue(your-queue)"
echo "   same => n,AGI(agi://localhost:4574)"
echo "   same => n,Hangup()"
echo ""
echo "6. For ULINE release on hangup, add to hangup handler:"
echo "   same => n,Set(CHANNEL(hangup_handler_push)=uline-release,s,1)"
echo ""
echo "   [uline-release]"
echo "   exten => s,1,AGI(agi://localhost:4574/release)"
echo "   same => n,Return()"
echo ""
echo "Firewall status:"
echo "  Port $FASTAGI_PORT is now open"
echo "  View rules: iptables -L INPUT -n --line-numbers"
echo ""
echo "=========================================="
