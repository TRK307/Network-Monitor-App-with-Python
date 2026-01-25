## Network Monitor Dashboard // Calm Dark

 A real-time, low-latency telemetry dashboard designed for homelab enthusiasts using OpenWrt routers. This application pulls live metrics directly from your router via SSH and visualizes them through a professional, desaturated "Calm Dark" web interface.


🚀 Key Features

  Dynamic Throughput: Real-time Mbps calculation for WAN traffic.

  Semantic Coloring: Muted color-coding for Latency (Good/Warn/Bad) and Service Tags.

  Identity Awareness: Automatically differentiates between WiFi and LAN clients using DHCP leases and wireless station dumps.

  Service Intelligence: Identifies specific traffic types such as HTTPS, SSH, and Speedtests.

  System Health: Monitors router CPU load and hardware link speeds.



## 🛠 Homelab Environment Setup

1. Router Requirements

Your router must be running OpenWrt (or another Linux-based firmware). Ensure the following packages are installed on the router:
```
opkg update
opkg install iftop ethtool
```
2. SSH Authentication

The dashboard requires passwordless SSH access to the router. Generate an SSH key on your hosting machine and copy it to the router:
```
ssh-keygen -t rsa
ssh-copy-id root@your.router.ip
```
3. Python Environment (venv)

It is recommended to host this app in a dedicated virtual environment.
Bash
```
# Create and activate the virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# Install dependencies
pip install Flask
```

##🖥 Deployment

Create Network_Monitor.py

```
nano Network Monitor.py
```
Paste the contents of Network Monitor.py then save
```
CTRL + O > ENTER > CTRL + X
```

Open test_router.py and update the ROUTER_IP and INTERFACE constants to match your network.

Run the application:
```
#Ensure the python VENV is running, since its hosting the App
python test_router.py
Access the dashboard at http://<your-server-ip>:5000.
```

##📂 Project Structure

  test_router.py: The core Flask application and telemetry engine.

  requirements.txt: Python dependency list.

  LICENSE: GNU General Public License v3.0.

⚖️ License


##Distributed under the GNU General Public License v3.0. This ensures the project remains open-source and respects the user's right to modify their own hardware telemetry. See LICENSE for more information.


🤝 Acknowledgments

  OpenWrt for the incredible router firmware.

  Flask for the lightweight backend.

  Outfit Font by Google Fonts for the modern aesthetic.
