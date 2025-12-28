# Express FastAGI Service

FastAGI service for Asterisk integration with Express Taxi API. Provides ULINE (Unique Line Number) management for parked calls and real-time notification to Express API.

## 🚀 Features

- ✅ **FastAGI Protocol** - Remote execution without Asterisk restart
- ✅ **ULINE Management** - Unique line numbers (1-199) for call parking
- ✅ **Async HTTP Requests** - Non-blocking API calls to Express
- ✅ **Multiple Endpoints** - Incoming calls, ULINE update, ULINE release
- ✅ **Systemd Integration** - Auto-start, monitoring, journalctl logging
- ✅ **Isolated Environment** - Virtual environment with dependencies
- ✅ **Production Ready** - Security hardening and error handling

## 📋 Requirements

- Debian 10+ (Buster or newer)
- Python 3.7+
- Asterisk 13+ (with FastAGI support)
- Root access for installation

## 📦 Installation

### Quick Installation

```bash
# 1. Download all project files
cd /tmp
# (copy express-fastagi directory here)

cd express-fastagi

# 2. Run installation script
chmod +x install.sh
sudo ./install.sh
```

### Manual Installation

```bash
# 1. Create directory
sudo mkdir -p /opt/express-fastagi
cd /opt/express-fastagi

# 2. Copy files
sudo cp express_fastagi.py /opt/express-fastagi/
sudo cp requirements.txt /opt/express-fastagi/
sudo cp .env.example /opt/express-fastagi/.env

# 3. Create virtual environment
sudo apt-get install python3-venv python3-pip
sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt

# 4. Set permissions
sudo chown -R asterisk:asterisk /opt/express-fastagi
sudo chmod +x /opt/express-fastagi/express_fastagi.py

# 5. Install systemd service
sudo cp express-fastagi.service /etc/systemd/system/
sudo systemctl daemon-reload

# 6. Configure firewall
sudo iptables -I INPUT -p tcp --dport 4574 -j ACCEPT
sudo netfilter-persistent save
```

## ⚙️ Configuration

### 1. Service Configuration (.env)

```bash
sudo nano /opt/express-fastagi/.env
```

**Minimum required settings:**

```ini
# FastAGI Server
FASTAGI_HOST=0.0.0.0
FASTAGI_PORT=4574

# Logging
LOG_LEVEL=INFO

# Express Taxi API (MANDATORY!)
DEFAULT_EXPRESS_URL=http://192.168.1.100:8080/YTaxi/ru/ManagePBX/IncomingCall
DEFAULT_EXPRESS_PROVIDER=provider_123
DEFAULT_EXPRESS_CLASS=0

# HTTP Timeout
HTTP_TIMEOUT=10

# ULINE Range
ULINE_MIN=1
ULINE_MAX=199
```

### 2. Asterisk Configuration

#### extensions.conf - Basic Queue Example

```ini
[express-incoming]
exten => _0XXXXXXXXX,1,NoOp(Incoming call from ${CALLERID(num)})
 same => n,Set(EXPRESS_PROVIDER=provider_123)
 same => n,Set(EXPRESS_CLASS=1)
 same => n,Set(EXPRESS_URL=http://192.168.1.100:8080/YTaxi/ru/ManagePBX/IncomingCall)
 same => n,Answer()
 same => n,Queue(taxi-operators,t,,,300)
 same => n,AGI(agi://localhost:4574)
 same => n,Hangup()
```

#### extensions.conf - With ULINE Release on Hangup

```ini
[express-incoming]
exten => _0XXXXXXXXX,1,NoOp(Incoming call from ${CALLERID(num)})
 same => n,Set(EXPRESS_PROVIDER=provider_123)
 same => n,Set(EXPRESS_CLASS=1)
 same => n,Set(EXPRESS_URL=http://192.168.1.100:8080/YTaxi/ru/ManagePBX/IncomingCall)
 ; Set hangup handler to release ULINE
 same => n,Set(CHANNEL(hangup_handler_push)=uline-release,s,1)
 same => n,Answer()
 same => n,Queue(taxi-operators)
 same => n,AGI(agi://localhost:4574)
 same => n,Hangup()

; Hangup handler to release ULINE
[uline-release]
exten => s,1,NoOp(Releasing ULINE for ${CDR(uniqueid)})
 same => n,AGI(agi://localhost:4574/release)
 same => n,Return()
```

#### extensions.conf - With Call Parking

```ini
[express-incoming]
exten => _0XXXXXXXXX,1,NoOp(Incoming call from ${CALLERID(num)})
 same => n,Set(EXPRESS_PROVIDER=provider_123)
 same => n,Set(EXPRESS_CLASS=1)
 same => n,Set(EXPRESS_URL=http://192.168.1.100:8080/YTaxi/ru/ManagePBX/IncomingCall)
 same => n,Set(CHANNEL(hangup_handler_push)=uline-release,s,1)
 same => n,Answer()
 same => n,Queue(taxi-operators)
 same => n,AGI(agi://localhost:4574)
 same => n,Hangup()

; Park call handler
[parking-handler]
exten => _70X,1,NoOp(Parking call)
 same => n,Park()
 ; Update ULINE when call is parked
 same => n,AGI(agi://localhost:4574/update)
 same => n,Hangup()

; Pickup parked call by ULINE (PAGINGEXTEN)
[uline-pickup]
exten => _[1-9]XX,1,NoOp(Pickup call with ULINE ${EXTEN})
 same => n,ParkedCall(${EXTEN})
 same => n,Hangup()

[uline-release]
exten => s,1,NoOp(Releasing ULINE for ${CDR(uniqueid)})
 same => n,AGI(agi://localhost:4574/release)
 same => n,Return()
```

## 🎯 Usage

### Start Service

```bash
# Start service
sudo systemctl start express-fastagi

# Enable auto-start
sudo systemctl enable express-fastagi

# Check status
sudo systemctl status express-fastagi

# View logs
sudo journalctl -u express-fastagi -f
```

### Stop Service

```bash
sudo systemctl stop express-fastagi
```

### Restart Service

```bash
sudo systemctl restart express-fastagi
```

## 📊 ULINE Management

### What is ULINE?

ULINE (Unique Line Number) is a simple unique identifier (1-199) assigned to each call. It's used for:

1. **Call Parking** - Park calls with unique numbers
2. **Call Pickup** - Operators can dial ULINE to pickup parked calls
3. **Express API** - Send ULINE to Express system for tracking

### ULINE Lifecycle

```
Call Arrives → ULINE Allocated → Call Answered → Express Notified
                     ↓                                    ↓
              Set ULINE var                         HTTP Request
                     ↓                                    ↓
              Call Parked → ULINE Updated → Park Number = ULINE
                     ↓                                    ↓
              Call Ends → ULINE Released → Available Again
```

### FastAGI Endpoints

The service provides three endpoints:

1. **`agi://host:4574`** - Main handler (incoming calls, ULINE allocation)
2. **`agi://host:4574/update`** - Update ULINE when call is parked
3. **`agi://host:4574/release`** - Release ULINE when call ends

## 🔍 Diagnostics

### Check Service Status

```bash
# Service status
sudo systemctl status express-fastagi

# Check if port is open
sudo netstat -tlnp | grep 4574

# Test connection
telnet localhost 4574
```

### View Logs

```bash
# Real-time logs
sudo journalctl -u express-fastagi -f

# Last 100 lines
sudo journalctl -u express-fastagi -n 100

# Logs for specific time
sudo journalctl -u express-fastagi --since "10 minutes ago"

# Logs with errors only
sudo journalctl -u express-fastagi -p err
```

### Check Firewall

```bash
# View iptables rules
sudo iptables -L INPUT -n --line-numbers | grep 4574

# Test from remote Asterisk server
telnet <express-fastagi-ip> 4574
```

### Test ULINE Allocation

```bash
# Start service with debug logging
sudo systemctl stop express-fastagi
cd /opt/express-fastagi
sudo -u asterisk bash -c "source venv/bin/activate && LOG_LEVEL=DEBUG python express_fastagi.py"

# Make a test call and watch ULINE allocation
```

## 🐛 Troubleshooting

### Problem: Service won't start

```bash
# Check logs for errors
sudo journalctl -u express-fastagi -n 50

# Check Python dependencies
/opt/express-fastagi/venv/bin/python -c "import twisted, starpy, aiohttp"

# Check permissions
ls -la /opt/express-fastagi/
sudo chown -R asterisk:asterisk /opt/express-fastagi/
```

### Problem: Asterisk can't connect

```bash
# Check firewall
sudo iptables -L INPUT -n | grep 4574
sudo iptables -I INPUT -p tcp --dport 4574 -j ACCEPT
sudo netfilter-persistent save

# Check service is listening
sudo netstat -tlnp | grep 4574

# Check from Asterisk
telnet localhost 4574
```

### Problem: HTTP requests failing

```bash
# Test Express API manually
curl "http://YOUR_EXPRESS_IP:8080/YTaxi/ru/ManagePBX/IncomingCall?provider=test&from=0671234567&to=192.168.1.1&line=1&carClass=0"

# Check logs for HTTP errors
sudo journalctl -u express-fastagi -f | grep -i http
```

### Problem: ULINE not allocated

```bash
# Check ULINE statistics in logs
sudo journalctl -u express-fastagi | grep "ULINE stats"

# If all ULINEs are busy (199/199), increase range in .env
sudo nano /opt/express-fastagi/.env
# Change: ULINE_MAX=299
sudo systemctl restart express-fastagi
```

## 📝 API Reference

### Express API Request Format

```
GET http://{server_url}?provider={provider}&from={phone}&to={operator_ip}&line={uline}&carClass={class}
```

**Parameters:**

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| provider | string | Provider ID | provider_123 |
| from | string | Caller phone (10 digits) | 0671234567 |
| to | string | Operator IP address | 192.168.1.10 |
| line | integer | ULINE number | 42 |
| carClass | integer | Car class | 0, 1, 2 |

**Example URL:**

```
http://192.168.1.100:8080/YTaxi/ru/ManagePBX/IncomingCall?provider=provider_123&from=0671234567&to=192.168.1.10&line=42&carClass=1
```

## 🏗️ Architecture

```
┌─────────────────┐    FastAGI         ┌──────────────────────┐
│                 │   (port 4574)       │                      │
│   Asterisk      │◄──────────────────►│  Express FastAGI     │
│                 │                     │  Service             │
│   - Queues      │  agi://host:4574   │  - ULINE Manager     │
│   - Parking     │  /update           │  - HTTP Client       │
│   - CDR         │  /release          │  - Request Router    │
└─────────────────┘                     └──────────┬───────────┘
                                                   │
                                                   │ HTTP
                                                   │
                                                   ▼
                                        ┌──────────────────┐
                                        │                  │
                                        │  Express Taxi    │
                                        │  API Server      │
                                        │                  │
                                        └──────────────────┘
```

## 🔐 Security

### Systemd Security Features

The service runs with security hardening:

- `NoNewPrivileges=true` - Prevents privilege escalation
- `PrivateTmp=true` - Isolated /tmp directory
- `ProtectSystem=strict` - Read-only system directories
- `ProtectHome=true` - No access to home directories
- Runs as user `asterisk` (non-root)

### Firewall Configuration

```bash
# Restrict access to specific Asterisk servers
sudo iptables -I INPUT -p tcp -s 192.168.1.0/24 --dport 4574 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 4574 -j DROP
sudo netfilter-persistent save
```

### Logging

All events are logged to systemd journal for audit trail:

```bash
# View security-related logs
sudo journalctl -u express-fastagi -p warning

# Export logs for analysis
sudo journalctl -u express-fastagi --since "2024-01-01" > express-logs.txt
```

## 📈 Performance

### ULINE Capacity

- Default: 199 concurrent calls (ULINE 1-199)
- Configurable via `ULINE_MIN` and `ULINE_MAX` in .env
- Each ULINE tracks: CDR start, uniqueid, channel, timestamp

### HTTP Performance

- Async requests - doesn't block Asterisk
- Configurable timeout (default 10s)
- Connection pooling via aiohttp

### Monitoring

```bash
# Watch ULINE usage
sudo journalctl -u express-fastagi -f | grep "ULINE stats"

# Monitor request rate
sudo journalctl -u express-fastagi -f | grep "New request"
```

## 🚀 Advanced Configuration

### Multiple Express Servers

Use different URLs per call:

```ini
[express-vip]
exten => _1XX,1,Set(EXPRESS_URL=http://vip.server.com:8080/YTaxi/ru/ManagePBX/IncomingCall)
 same => n,AGI(agi://localhost:4574)

[express-standard]
exten => _2XX,1,Set(EXPRESS_URL=http://standard.server.com:8080/YTaxi/ru/ManagePBX/IncomingCall)
 same => n,AGI(agi://localhost:4574)
```

### Remote FastAGI

Run service on separate server:

```ini
; On Asterisk server
exten => _X.,1,AGI(agi://192.168.1.50:4574)
```

```bash
# On FastAGI server, open firewall
sudo iptables -I INPUT -p tcp -s 192.168.1.0/24 --dport 4574 -j ACCEPT
```

## 📚 Additional Resources

### Project Structure

```
/opt/express-fastagi/
├── express_fastagi.py       # Main service
├── requirements.txt          # Dependencies
├── .env                     # Configuration
├── venv/                    # Virtual environment
└── express-fastagi.service  # Systemd unit
```

### Dependencies

- **twisted** - Async framework
- **starpy** - AGI/FastAGI protocol
- **aiohttp** - Async HTTP client
- **python-dotenv** - Configuration management

### Links

- StarPy: https://github.com/radetsky/starpy
- Twisted: https://twisted.org/
- Asterisk AGI: https://docs.asterisk.org/

## 📄 License

MIT License

## 👤 Author

Express FastAGI Service - Asterisk integration for Express Taxi

---

**Version**: 2.0.0  
**Last Updated**: 2024-12-28
