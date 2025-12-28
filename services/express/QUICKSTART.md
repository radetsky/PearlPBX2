# Express FastAGI - Quick Start Guide

Get up and running in 5 minutes! 🚀

## 📥 Installation

```bash
# 1. Navigate to project directory
cd /path/to/express-fastagi

# 2. Run installation
chmod +x install.sh
sudo ./install.sh
```

## ⚙️ Minimum Configuration

```bash
# Edit .env file
sudo nano /opt/express-fastagi/.env
```

**Set these required values:**

```ini
DEFAULT_EXPRESS_URL=http://192.168.1.100:8080/YTaxi/ru/ManagePBX/IncomingCall
DEFAULT_EXPRESS_PROVIDER=provider_123
```

## 🚀 Start Service

```bash
sudo systemctl start express-fastagi
sudo systemctl enable express-fastagi
sudo systemctl status express-fastagi
```

## 📞 Configure Asterisk

### extensions.conf

```ini
[your-context]
exten => _0XXXXXXXXX,1,Set(EXPRESS_PROVIDER=provider_123)
 same => n,Set(EXPRESS_CLASS=1)
 same => n,Set(EXPRESS_URL=http://192.168.1.100:8080/YTaxi/ru/ManagePBX/IncomingCall)
 same => n,Set(CHANNEL(hangup_handler_push)=uline-release,s,1)
 same => n,Queue(taxi-operators)
 same => n,AGI(agi://localhost:4574)
 same => n,Hangup()

[uline-release]
exten => s,1,AGI(agi://localhost:4574/release)
 same => n,Return()
```

**Reload Asterisk:**

```bash
sudo asterisk -rx "dialplan reload"
```

## ✅ Test

```bash
# View logs in real-time
sudo journalctl -u express-fastagi -f

# Make a test call to see ULINE allocation
```

## 📊 Monitor

```bash
# Service status
sudo systemctl status express-fastagi

# Live logs
sudo journalctl -u express-fastagi -f

# Check ULINE usage
sudo journalctl -u express-fastagi | grep "ULINE stats"
```

## 🔍 Quick Diagnostics

### Service won't start?

```bash
sudo journalctl -u express-fastagi -n 50
```

### Asterisk can't connect?

```bash
sudo iptables -L INPUT -n | grep 4574
telnet localhost 4574
```

### HTTP requests failing?

```bash
curl "http://YOUR_EXPRESS_IP:8080/YTaxi/ru/ManagePBX/IncomingCall?provider=test&from=0671234567&to=192.168.1.1&line=1&carClass=0"
```

## 📚 More Information

See **README.md** for complete documentation!

---

**That's it! You're ready to go! 🎉**
