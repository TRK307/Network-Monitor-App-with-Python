# Network Monitor Dashboard // Calm Dark

A real-time, low-latency telemetry dashboard designed for homelab enthusiasts using OpenWrt routers. This application pulls live metrics directly from your router via SSH and visualizes them through a professional, desaturated "Calm Dark" web interface.

![Dashboard Preview](Dashboard.png)

## 🚀 Key Features

- **Dynamic Throughput**: Real-time Mbps calculation for WAN traffic
- **Semantic Coloring**: Muted color-coding for Latency (Good/Warn/Bad) and Service Tags
- **Identity Awareness**: Automatically differentiates between WiFi and LAN clients using DHCP leases and wireless station dumps
- **Service Intelligence**: Identifies specific traffic types such as HTTPS, SSH, and Speedtests
- **System Health**: Monitors router CPU load and hardware link speeds

## 📋 Prerequisites

Before you begin, ensure you have:

- **OpenWrt Router** with SSH access enabled
- **Python 3.7+** installed on your monitoring machine (the computer that will run this dashboard)
- **Network connectivity** between your monitoring machine and router
- **Basic command-line knowledge** for SSH and Python

## 🛠 Installation Guide

### Step 1: Router Setup

First, install the required packages on your OpenWrt router:

```bash
# SSH into your router
ssh root@192.168.1.1  # Replace with your router's IP

# Update package lists and install dependencies
opkg update
opkg install iftop ethtool

# Exit the router SSH session
exit
```

### Step 2: Configure SSH Key Authentication

Set up passwordless SSH access from your monitoring machine to the router:

```bash
# Generate SSH key (if you don't already have one)
ssh-keygen -t rsa -b 4096

# Copy the key to your router (replace with your router's IP)
ssh-copy-id root@192.168.1.1

# Test passwordless login (should connect without asking for password)
ssh root@192.168.1.1
exit
```

**Note**: If `ssh-copy-id` doesn't work, manually copy your public key:
```bash
cat ~/.ssh/id_rsa.pub | ssh root@192.168.1.1 "cat >> /etc/dropbear/authorized_keys"
```

### Step 3: Clone and Set Up the Application

```bash
# Clone the repository
git clone https://github.com/TRK307/Network-Monitor-App-with-Python.git
cd Network-Monitor-App-with-Python

# Create a Python virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate  # On Linux/macOS
# OR
.\venv\Scripts\activate   # On Windows
```

### Step 4: Install Python Dependencies

```bash
# With the virtual environment activated, install required packages
pip install Flask paramiko
```

### Step 5: Configure the Application

Edit `Network Monitor.py` and update the following constants near the top of the file to match your network:

```python
ROUTER_IP = "192.168.1.1"    # Your OpenWrt router's IP address
INTERFACE = "eth1"            # Your WAN interface name (e.g., eth1, wan, pppoe-wan)
```

**Finding your WAN interface name:**
```bash
# SSH into your router and run:
ip link show
# or
uci show network.wan.device
```

### Step 6: Run the Application

```bash
# Ensure your virtual environment is activated
source venv/bin/activate  # Skip if already activated

# Run the dashboard
python "Network Monitor.py"
```

You should see output indicating Flask is running:
```
 * Running on http://0.0.0.0:5000
```

### Step 7: Access the Dashboard

Open your web browser and navigate to:

- **From the same machine**: `http://localhost:5000`
- **From other devices on your network**: `http://<monitoring-machine-ip>:5000`

Replace `<monitoring-machine-ip>` with the IP address of the computer running the Python application (not your router's IP).

## 📂 Project Structure

```
Network-Monitor-App-with-Python/
├── Network Monitor.py     # Main Flask application and telemetry engine
├── Dashboard.png          # Screenshot of the dashboard
├── README.md              # This file
└── LICENSE                # GNU GPL v3.0 license
```

## 🔧 Troubleshooting

### SSH Connection Issues

**Problem**: Application can't connect to router via SSH

**Solutions**:
- Verify passwordless SSH works: `ssh root@192.168.1.1` (should not ask for password)
- Ensure the router IP in `Network Monitor.py` matches your router's actual IP
- Check that SSH is enabled on your router: `uci show dropbear`
- Verify firewall rules allow SSH from your monitoring machine

### Permission Denied Errors

**Problem**: SSH authentication fails

**Solutions**:
- Confirm your SSH key was copied correctly: `ssh root@192.168.1.1 cat /etc/dropbear/authorized_keys`
- Check SSH key file permissions: `chmod 600 ~/.ssh/id_rsa`
- Try re-running `ssh-copy-id root@192.168.1.1`

### Missing Packages on Router

**Problem**: Commands like `iftop` or `ethtool` not found

**Solutions**:
- SSH into router and verify installation: `opkg list-installed | grep -E 'iftop|ethtool'`
- Reinstall if needed: `opkg update && opkg install iftop ethtool`
- Ensure sufficient storage space on router: `df -h`

### Wrong Interface Name

**Problem**: No data showing or incorrect throughput values

**Solutions**:
- SSH into router and list interfaces: `ip link show` or `ifconfig`
- Common WAN interface names: `eth1`, `eth0.2`, `wan`, `pppoe-wan`, `wwan0`
- Update `INTERFACE` constant in `Network Monitor.py` to match your actual WAN interface

### Dashboard Won't Load

**Problem**: Can't access `http://localhost:5000`

**Solutions**:
- Verify Flask is running without errors in the terminal
- Check if port 5000 is already in use: `lsof -i :5000` (Linux/macOS) or `netstat -ano | findstr :5000` (Windows)
- Try accessing via IP instead of localhost: `http://127.0.0.1:5000`
- Check firewall settings on your monitoring machine

### Python Module Not Found

**Problem**: `ModuleNotFoundError` when running the application

**Solutions**:
- Ensure virtual environment is activated (you should see `(venv)` in your terminal prompt)
- Reinstall dependencies: `pip install Flask paramiko`
- Verify you're using the correct Python version: `python --version` (should be 3.7+)

## 🔒 Security Considerations

- This application requires SSH access with root privileges to your router
- SSH keys provide secure, passwordless authentication
- The dashboard runs on your local network and should not be exposed to the internet without additional security measures
- Consider using a firewall to restrict access to port 5000 if running on a shared network

## 🤝 Contributing

Contributions are welcome! Feel free to:

- Report bugs or issues
- Suggest new features or improvements
- Submit pull requests

## ⚖️ License

This project is distributed under the GNU General Public License v3.0. This ensures the project remains open-source and respects the user's right to modify their own hardware telemetry. See [LICENSE](LICENSE) for more information.

## 🙏 Acknowledgments

- [OpenWrt](https://openwrt.org/) for the incredible router firmware
- [Flask](https://flask.palletsprojects.com/) for the lightweight web framework
- [Outfit Font](https://fonts.google.com/specimen/Outfit) by Google Fonts for the modern aesthetic
- The homelab community for inspiration and support

## 📞 Support

If you encounter issues not covered in the troubleshooting section:

1. Check existing [GitHub Issues](https://github.com/TRK307/Network-Monitor-App-with-Python/issues)
2. Create a new issue with detailed information about your setup and the problem
3. Include relevant log output and error messages

---

**Note**: This is a homelab project designed for personal use. Performance and compatibility may vary based on your specific router model and network configuration.