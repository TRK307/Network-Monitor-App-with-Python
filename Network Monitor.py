import subprocess
import time
import logging
from flask import Flask, render_template_string, jsonify
from datetime import datetime
from collections import deque

app = Flask(__name__)

# --- CONFIGURATION ---
ROUTER_IP = "10.0.0.1"
INTERFACE = "eth0"        # WAN
LAN_INTERFACE = "br-lan"  # For Traffic Analysis

# Enhanced state tracking
last_state = {
    "rx_bytes": 0,
    "tx_bytes": 0,
    "time": time.time()
}

# Debug log storage (keep last 50 entries)
debug_logs = deque(maxlen=50)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def log_debug(level, message):
    """Add entry to debug log with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    entry = {
        "time": timestamp,
        "level": level,
        "message": message
    }
    debug_logs.append(entry)
    logger.info(f"[{level}] {message}")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>ROUTER MONITOR // V6_BAND_DETECT</title>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        /* Dracula Theme Colors - Muted & Professional */
        :root {
            --bg: #282a36;
            --bg-darker: #1e1f29;
            --card-bg: #2e3240;
            --card-border: #3d4054;
            --purple: #bd93f9;
            --cyan: #8be9fd;
            --green: #50fa7b;
            --orange: #ffb86c;
            --pink: #ff79c6;
            --red: #ff5555;
            --yellow: #f1fa8c;
            --text: #f8f8f2;
            --text-muted: #6272a4;
            --comment: #6272a4;
        }

        body { 
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; 
            background: var(--bg); 
            color: var(--text); 
            margin: 0; 
            padding: 20px;
            line-height: 1.6;
        }

        .dashboard { 
            max-width: 1400px; 
            margin: auto; 
            display: grid; 
            grid-template-columns: repeat(4, 1fr); 
            gap: 12px; 
        }
        
        .card { 
            background: var(--card-bg); 
            border-radius: 6px; 
            padding: 18px; 
            border: 1px solid var(--card-border); 
            box-shadow: 0 2px 8px rgba(0,0,0,0.3); 
            position: relative;
            transition: border-color 0.3s ease;
        }

        .card:hover {
            border-color: var(--purple);
        }

        .full-width { grid-column: span 4; }
        .half-width { grid-column: span 2; }

        /* Typography & Headers */
        h2 { 
            font-size: 0.65rem; 
            text-transform: uppercase; 
            letter-spacing: 2px; 
            color: var(--comment); 
            margin: 0 0 12px 0; 
            display: flex; 
            justify-content: space-between;
            align-items: center;
            font-weight: 600;
        }

        .value { 
            font-size: 2.4rem; 
            font-weight: 700; 
            color: var(--text); 
            line-height: 1.1; 
            margin: 8px 0;
        }

        .unit { 
            font-size: 0.7rem; 
            color: var(--text-muted); 
            margin-top: 4px; 
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        /* Color classes for different metrics */
        .color-purple { color: var(--purple); }
        .color-cyan { color: var(--cyan); }
        .color-green { color: var(--green); }
        .color-orange { color: var(--orange); }
        .color-pink { color: var(--pink); }
        .color-red { color: var(--red); }
        .color-yellow { color: var(--yellow); }

        /* Status tags */
        .status-tag { 
            font-size: 0.55rem; 
            padding: 3px 8px; 
            border: 1px solid var(--card-border); 
            border-radius: 3px;
            background: var(--bg-darker);
            color: var(--cyan);
            font-weight: 500;
        }

        /* Table Styling */
        table { 
            width: 100%; 
            border-collapse: collapse; 
            margin-top: 8px; 
        }
        
        th { 
            text-align: left; 
            font-size: 0.6rem; 
            color: var(--comment); 
            text-transform: uppercase; 
            padding: 10px 8px; 
            border-bottom: 1px solid var(--card-border);
            font-weight: 600;
            letter-spacing: 1px;
        }
        
        td { 
            padding: 10px 8px; 
            border-bottom: 1px solid var(--bg-darker); 
            font-size: 0.8rem; 
            color: var(--text);
        }
        
        .source-ip { color: var(--pink); font-weight: 500; }
        .dest-ip { color: var(--cyan); }
        .bw-val { color: var(--green); text-align: right; font-weight: 600; }

        /* Debug console styling */
        .debug-console {
            background: var(--bg-darker);
            border-radius: 4px;
            padding: 12px;
            max-height: 250px;
            overflow-y: auto;
            font-family: 'Fira Code', monospace;
            font-size: 0.7rem;
        }

        .debug-entry {
            display: flex;
            gap: 10px;
            padding: 4px 0;
            border-bottom: 1px solid var(--card-border);
        }

        .debug-entry:last-child {
            border-bottom: none;
        }

        .debug-time {
            color: var(--comment);
            min-width: 70px;
        }

        .debug-level {
            min-width: 50px;
            font-weight: 600;
        }

        .debug-level.INFO { color: var(--cyan); }
        .debug-level.SUCCESS { color: var(--green); }
        .debug-level.WARNING { color: var(--orange); }
        .debug-level.ERROR { color: var(--red); }

        .debug-message {
            color: var(--text);
            flex: 1;
        }

        /* Speed metrics container */
        .speed-container {
            display: flex;
            justify-content: space-between;
            gap: 15px;
        }

        .speed-metric {
            flex: 1;
        }

        .speed-metric .value {
            font-size: 1.8rem;
        }

        /* Scrollbar styling for debug console */
        .debug-console::-webkit-scrollbar {
            width: 6px;
        }

        .debug-console::-webkit-scrollbar-track {
            background: var(--bg);
        }

        .debug-console::-webkit-scrollbar-thumb {
            background: var(--comment);
            border-radius: 3px;
        }

        .debug-console::-webkit-scrollbar-thumb:hover {
            background: var(--purple);
        }

        /* Footer */
        .footer { 
            grid-column: span 4; 
            text-align: center; 
            padding-top: 25px; 
            font-size: 0.6rem; 
            color: var(--comment); 
            text-transform: uppercase; 
            letter-spacing: 4px;
        }

        /* Connection indicator */
        .connection-status {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--green);
            animation: pulse 2s infinite;
            margin-right: 6px;
        }

        .connection-status.offline {
            background: var(--red);
            animation: none;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        /* Temperature gauge visualization */
        .temp-bar {
            height: 6px;
            background: var(--bg-darker);
            border-radius: 3px;
            margin-top: 8px;
            overflow: hidden;
        }

        .temp-fill {
            height: 100%;
            border-radius: 3px;
            transition: width 0.5s ease, background-color 0.5s ease;
        }

        /* Connected Devices Styling */
        .devices-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 10px;
            margin-top: 10px;
        }

        .device-item {
            background: var(--bg-darker);
            border: 1px solid var(--card-border);
            border-radius: 4px;
            padding: 10px 12px;
            display: flex;
            align-items: center;
            gap: 10px;
            transition: border-color 0.3s ease;
        }
        
        /* Device OFFLINE State */
        .device-item.status-offline {
            opacity: 0.5;
            border-style: dashed;
        }

        .device-item:hover {
            border-color: var(--purple);
            opacity: 1;
        }

        .device-info {
            flex: 1;
            min-width: 0;
        }

        .device-name {
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .device-ip {
            font-size: 0.7rem;
            color: var(--comment);
            font-family: 'Monaco', monospace;
        }

        .device-connection {
            font-size: 0.55rem;
            padding: 2px 6px;
            border-radius: 3px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        /* Enhanced Connection Tags */
        .conn-wifi-5g {
            background: var(--purple);
            color: var(--bg);
        }

        .conn-wifi-2g {
            background: var(--orange);
            color: var(--bg);
        }

        .conn-lan {
            background: var(--cyan);
            color: var(--bg);
        }
        
        .conn-offline {
            background: var(--card-border);
            color: var(--text-muted);
        }

        .conn-unknown {
            background: var(--comment);
            color: var(--bg);
        }
    </style>
</head>
<body>

<div class="dashboard">
    <div class="card full-width" style="padding: 12px 18px;">
        <h2 style="margin: 0;">
            <span>
                <span id="connection-indicator" class="connection-status"></span>
                ROUTER MONITOR V6
            </span>
            <span id="clock" class="status-tag">00:00:00</span>
        </h2>
    </div>

    <div class="card">
        <h2>Latency <span class="status-tag">LIVE</span></h2>
        <div id="ping-val" class="value color-purple">--</div>
        <div class="unit">MS / GOOGLE DNS</div>
    </div>

    <div class="card">
        <h2>CPU Load <span class="status-tag">1MIN</span></h2>
        <div id="load-val" class="value color-cyan">--</div>
        <div class="unit">SYSTEM LOAD</div>
    </div>

    <div class="card">
        <h2>Router CPU <span class="status-tag">LIVE TEMP</span></h2>
        <div id="temp-val" class="value color-orange">--</div>
        <div class="unit">°C / ROUTER THERMAL</div>
        <div class="temp-bar">
            <div id="temp-fill" class="temp-fill" style="width: 0%;"></div>
        </div>
        <div id="temp-status" class="unit" style="margin-top: 8px; color: var(--comment);">Reading sensor...</div>
    </div>

    <div class="card">
        <h2>Memory <span class="status-tag">HTOP LOGIC</span></h2>
        <div id="mem-val" class="value color-green">--</div>
        <div class="unit">USAGE % (NO CACHE)</div>
    </div>

    <div class="card full-width">
        <h2>Network Throughput <span class="status-tag">{{ INTERFACE }}</span></h2>
        <div class="speed-container">
            <div class="speed-metric">
                <div class="unit" style="margin-bottom: 5px;">⬇ DOWNLOAD</div>
                <div id="download-speed" class="value color-green">0.00 <span class="unit" style="display: inline; margin: 0;">Mbps</span></div>
            </div>
            <div class="speed-metric">
                <div class="unit" style="margin-bottom: 5px;">⬆ UPLOAD</div>
                <div id="upload-speed" class="value color-pink">0.00 <span class="unit" style="display: inline; margin: 0;">Mbps</span></div>
            </div>
            <div class="speed-metric">
                <div class="unit" style="margin-bottom: 5px;">⇅ TOTAL</div>
                <div id="total-speed" class="value color-yellow">0.00 <span class="unit" style="display: inline; margin: 0;">Mbps</span></div>
            </div>
        </div>
    </div>

    <div class="card full-width">
        <h2>Active Socket Connections <span class="status-tag" id="conn-count">0 ACTIVE</span></h2>
        <table>
            <thead>
                <tr>
                    <th width="35%">Internal Source</th>
                    <th width="5%" style="text-align:center">Dir</th>
                    <th width="35%">External Destination</th>
                    <th width="25%" style="text-align:right">Traffic (2s)</th>
                </tr>
            </thead>
            <tbody id="iftop-body">
                <tr><td colspan="4" style="text-align:center; color: var(--comment);">Initializing...</td></tr>
            </tbody>
        </table>
    </div>

    <div class="card full-width">
        <h2>
            Connected Devices 
            <span class="status-tag" id="device-count">0 DEVICES</span>
        </h2>
        <div class="devices-grid" id="devices-grid">
            <div class="device-item">
                <div class="device-info">
                    <div class="device-name">Loading...</div>
                    <div class="device-ip">Scanning network</div>
                </div>
            </div>
        </div>
    </div>

    <div class="card full-width">
        <h2>
            System Debug Console 
            <span class="status-tag" id="debug-count">0 ENTRIES</span>
        </h2>
        <div class="debug-console" id="debug-console">
            <div class="debug-entry">
                <span class="debug-time">--:--:--</span>
                <span class="debug-level INFO">INFO</span>
                <span class="debug-message">Waiting for data...</span>
            </div>
        </div>
    </div>

    <div class="footer">
        GL-AX1800 // ENHANCED_MONITOR_V6 // DRACULA_THEME
    </div>
</div>

<script>
    let updateCounter = 0;
    let consecutiveErrors = 0;

    function formatSpeed(mbps) {
        return parseFloat(mbps).toFixed(2);
    }

    function getTempColor(temp) {
        if (temp < 50) return 'var(--green)';
        if (temp < 70) return 'var(--yellow)';
        if (temp < 85) return 'var(--orange)';
        return 'var(--red)';
    }

    function getTempWidth(temp) {
        return Math.min(100, temp);
    }

    function updateDebugConsole(logs) {
        let html = '';
        logs.reverse().forEach(log => {
            html += `<div class="debug-entry">
                <span class="debug-time">${log.time}</span>
                <span class="debug-level ${log.level}">${log.level}</span>
                <span class="debug-message">${log.message}</span>
            </div>`;
        });
        $('#debug-console').html(html || '<div class="debug-entry"><span class="debug-message">No logs available</span></div>');
        $('#debug-count').text(`${logs.length} ENTRIES`);
    }

    function updateDevices(devices) {
        if (!devices || devices.length === 0) {
            $('#devices-grid').html('<div class="device-item" style="grid-column: 1/-1;"><div class="device-info" style="text-align: center; color: var(--comment);">No devices detected</div></div>');
            $('#device-count').text('0 DEVICES');
            return;
        }

        let html = '';
        
        // Sort: Online first, then Offline
        devices.sort((a, b) => {
            if (a.status === 'online' && b.status !== 'online') return -1;
            if (a.status !== 'online' && b.status === 'online') return 1;
            return 0;
        });

        devices.forEach(device => {
            let connClass, connText, itemClass = 'device-item';
            
            if (device.status === 'online') {
                if (device.connection === 'wifi') {
                    if (device.band === '5g') {
                        connClass = 'conn-wifi-5g';
                        connText = '5G WIFI';
                    } else if (device.band === '2.4g') {
                        connClass = 'conn-wifi-2g';
                        connText = '2.4G WIFI';
                    } else {
                        connClass = 'conn-wifi-2g'; // Fallback
                        connText = 'WIFI';
                    }
                } else if (device.connection === 'lan') {
                    connClass = 'conn-lan';
                    connText = 'LAN';
                } else {
                    connClass = 'conn-unknown';
                    connText = 'UNKNOWN';
                }
            } else {
                connClass = 'conn-offline';
                connText = 'OFFLINE';
                itemClass += ' status-offline';
            }
            
            html += `<div class="${itemClass}">
                <div class="device-info">
                    <div class="device-name">${device.hostname}</div>
                    <div class="device-ip">${device.ip}</div>
                </div>
                <span class="device-connection ${connClass}">${connText}</span>
            </div>`;
        });
        
        $('#devices-grid').html(html);
        $('#device-count').text(`${devices.length} KNOWN`);
    }

    function refresh() {
        updateCounter++;
        
        $.getJSON('/api/stats')
            .done(function(data) {
                consecutiveErrors = 0;
                $('#connection-indicator').removeClass('offline');
                
                if (data.status === "Online") {
                    // Update latency
                    let ping = parseInt(data.ping);
                    let pingClass = ping < 30 ? 'color-green' : ping < 70 ? 'color-yellow' : 'color-red';
                    $('#ping-val').text(ping).attr('class', 'value ' + pingClass);
                    
                    // Update CPU load
                    $('#load-val').text(data.load);
                    
                    // Update CPU temperature
                    if (data.temp !== "--") {
                        let temp = parseFloat(data.temp);
                        $('#temp-val').text(temp.toFixed(1) + '°');
                        $('#temp-fill').css({
                            'width': getTempWidth(temp) + '%',
                            'background-color': getTempColor(temp)
                        });
                        
                        if (temp > 80) {
                            $('#temp-status').html('⚠ HIGH - Monitor router cooling').css('color', 'var(--red)');
                        } else if (temp > 70) {
                            $('#temp-status').html('⚡ Warm but acceptable').css('color', 'var(--yellow)');
                        } else {
                            $('#temp-status').html('✓ Normal operating temp').css('color', 'var(--green)');
                        }
                    } else {
                        $('#temp-val').text('--');
                        $('#temp-fill').css('width', '0%');
                        $('#temp-status').html('✗ Sensor unavailable').css('color', 'var(--red)');
                    }
                    
                    // Update memory
                    $('#mem-val').text(data.memory + '%');
                    
                    // Update network speeds
                    $('#download-speed').html(formatSpeed(data.download_mbps) + ' <span class="unit" style="display: inline; margin: 0;">Mbps</span>');
                    $('#upload-speed').html(formatSpeed(data.upload_mbps) + ' <span class="unit" style="display: inline; margin: 0;">Mbps</span>');
                    $('#total-speed').html(formatSpeed(data.total_mbps) + ' <span class="unit" style="display: inline; margin: 0;">Mbps</span>');
                    
                    // Update time
                    $('#clock').text(data.time);

                    // Update active connections table
                    let rows = '';
                    data.iftop.forEach(f => {
                        rows += `<tr>
                            <td class="source-ip">${f.src}</td>
                            <td style="text-align:center; color: var(--comment);">↔</td>
                            <td class="dest-ip">${f.dst}</td>
                            <td class="bw-val">${f.last_2s}</td>
                        </tr>`;
                    });
                    $('#iftop-body').html(rows || '<tr><td colspan="4" style="text-align:center; color: var(--comment);">NO ACTIVE CONNECTIONS</td></tr>');
                    $('#conn-count').text(`${data.iftop.length} ACTIVE`);

                    // Update debug console
                    if (data.debug_logs) {
                        updateDebugConsole(data.debug_logs);
                    }

                    // Update connected devices
                    if (data.devices) {
                        updateDevices(data.devices);
                    }
                } else {
                    $('#connection-indicator').addClass('offline');
                }
            })
            .fail(function(jqXHR, textStatus, errorThrown) {
                consecutiveErrors++;
                $('#connection-indicator').addClass('offline');
                console.error('API Error:', textStatus, errorThrown);
            });
    }

    // Update every 2.5 seconds
    setInterval(refresh, 2500);
    refresh();
</script>
</body>
</html>
"""

def get_connected_devices():
    """
    Fetch connected devices with Band Detection.
    1. Loop through ALL wireless interfaces to find frequencies (2.4/5G).
    2. Map MAC addresses to these bands.
    3. Merge with ARP/DHCP to build complete list.
    """
    ssh_base = f"ssh -o ConnectTimeout=3 -o BatchMode=yes root@{ROUTER_IP}"
    
    try:
        # Complex command to:
        # 1. Get ARP table
        # 2. Iterate all wifi interfaces, get their freq, and dump their stations
        # 3. Get DHCP leases
        cmd = (
            f"{ssh_base} \""
            f"cat /proc/net/arp | grep -v 'IP address' | awk '{{print \\$1,\\$4,\\$6}}'; "
            f"echo '---WIFI_SCAN---'; "
            f"iw dev | grep Interface | awk '{{print \\$2}}' | while read iface; do "
            f"  freq=\\$(iw dev \\$iface info | grep -oE '[0-9]+ MHz' | head -n1 | awk '{{print \\$1}}'); "
            f"  echo \\\"IFACE \\$iface \\$freq\\\"; "
            f"  iw dev \\$iface station dump | grep Station | awk '{{print \\$2}}'; "
            f"done; "
            f"echo '---DHCP---'; "
            f"cat /tmp/dhcp.leases 2>/dev/null || echo ''"
            f"\""
        )
        
        result = subprocess.check_output(cmd, shell=True, timeout=10).decode().strip()
        lines = result.split('\n')
        
        # Data structures
        known_devices = {} # Key = MAC
        active_arp = {}    # Key = IP, Value = MAC
        
        # Wifi Mapping: Key = MAC, Value = Band ('2.4g' or '5g')
        wifi_mac_bands = {}
        
        section = 'arp'
        current_band = None
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            if '---WIFI_SCAN---' in line:
                section = 'wifi'
                continue
            elif '---DHCP---' in line:
                section = 'dhcp'
                continue
                
            if section == 'arp':
                # IP, MAC, Interface
                parts = line.split()
                if len(parts) >= 3:
                    ip, mac = parts[0], parts[1]
                    if mac != '00:00:00:00:00:00':
                        active_arp[ip] = mac
            
            elif section == 'wifi':
                # IFACE wlan0 2412
                if line.startswith('IFACE'):
                    parts = line.split()
                    if len(parts) >= 3:
                        freq = int(parts[2])
                        current_band = '5g' if freq > 4000 else '2.4g'
                else:
                    # It's a MAC address under the current interface
                    mac = line.lower()
                    if len(mac) == 17 and current_band:
                        wifi_mac_bands[mac] = current_band
                    
            elif section == 'dhcp':
                # timestamp, mac, ip, hostname
                parts = line.split()
                if len(parts) >= 4:
                    mac = parts[1].lower()
                    ip = parts[2]
                    hostname = parts[3]
                    if hostname == '*': hostname = f"Unknown ({ip.split('.')[-1]})"
                    
                    known_devices[mac] = {
                        'mac': mac,
                        'ip': ip,
                        'hostname': hostname,
                        'status': 'offline',
                        'connection': 'lan', # Default to LAN
                        'band': ''
                    }

        # MERGE LOGIC
        
        # 1. Check ARP actives (Determines Online status)
        for ip, mac in active_arp.items():
            if mac in known_devices:
                known_devices[mac]['status'] = 'online'
            else:
                # Device in ARP but not DHCP
                known_devices[mac] = {
                    'mac': mac,
                    'ip': ip,
                    'hostname': ip,
                    'status': 'online',
                    'connection': 'lan',
                    'band': ''
                }

        # 2. Check WiFi actives (Determines Connection Type and Band)
        # We loop through the wifi map we built from 'iw dev'
        for mac, band in wifi_mac_bands.items():
            if mac in known_devices:
                known_devices[mac]['status'] = 'online' # If in wifi dump, it is definitely online
                known_devices[mac]['connection'] = 'wifi'
                known_devices[mac]['band'] = band
            else:
                # In rare case a wifi device has no DHCP or ARP entry yet
                pass 

        # Convert to list
        device_list = list(known_devices.values())
        
        # Sorting
        device_list.sort(key=lambda x: (
            0 if x['status'] == 'online' else 1, 
            [int(p) for p in x['ip'].split('.')] if '.' in x['ip'] else 0
        ))
        
        return device_list
        
    except Exception as e:
        log_debug("WARNING", f"Could not fetch connected devices: {str(e)[:80]}")
        return []

def get_router_data():
    """Fetch all router metrics via SSH"""
    global last_state
    ssh_base = f"ssh -o ConnectTimeout=3 -o BatchMode=yes root@{ROUTER_IP}"
    
    cmd = (
        f"{ssh_base} \""
        f"cat /proc/loadavg | cut -d' ' -f1; "
        f"ping -c 1 8.8.8.8 | grep 'time=' | cut -d'=' -f4 | sed 's/ ms//' || echo 0; "
        f"grep {INTERFACE} /proc/net/dev | awk '{{print \\$2,\\$10}}'; "
        f"cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || "
        f"cat /sys/devices/virtual/thermal/thermal_zone0/temp 2>/dev/null || "
        f"cat /sys/class/hwmon/hwmon0/temp1_input 2>/dev/null || "
        f"echo 0; "
        f"awk '/MemTotal/ {{t=\\$2}} /MemAvailable/ {{a=\\$2}} END {{printf \\\"%d\\\", ((t-a)/t)*100}}' /proc/meminfo; "
        f"iftop -i {LAN_INTERFACE} -t -s 1 -n -N -P -L 12 2>/dev/null"
        f"\""
    )

    try:
        log_debug("INFO", f"Querying router at {ROUTER_IP}")
        raw = subprocess.check_output(cmd, shell=True, timeout=10).decode().strip().split('\n')
        
        # Parse metrics
        load = raw[0]
        ping = raw[1]
        
        # Parse RX and TX bytes
        net_stats = raw[2].split()
        current_rx = int(net_stats[0]) if len(net_stats) > 0 and net_stats[0].isdigit() else 0
        current_tx = int(net_stats[1]) if len(net_stats) > 1 and net_stats[1].isdigit() else 0
        
        # Parse temperature
        temp_raw = raw[3]
        if temp_raw.isdigit():
            temp_int = int(temp_raw)
            if temp_int < 200:
                temp = round(float(temp_int), 1)
            else:
                temp = round(temp_int / 1000, 1)
        else:
            temp = "--"
        
        # Parse memory
        memory = raw[4] if raw[4].isdigit() else "0"
        
        # Calculate speeds
        now = time.time()
        time_diff = now - last_state['time']
        
        if time_diff > 0:
            rx_diff = max(0, current_rx - last_state['rx_bytes'])
            tx_diff = max(0, current_tx - last_state['tx_bytes'])
            
            download_mbps = round(((rx_diff * 8) / 1024 / 1024) / time_diff, 2)
            upload_mbps = round(((tx_diff * 8) / 1024 / 1024) / time_diff, 2)
            total_mbps = round(download_mbps + upload_mbps, 2)
        else:
            download_mbps = upload_mbps = total_mbps = 0.0
        
        last_state = {
            "rx_bytes": current_rx,
            "tx_bytes": current_tx,
            "time": now
        }

        # Parse iftop data
        iftop_list = []
        traffic_lines = [l for l in raw if "=>" in l or "<=" in l]
        
        for i in range(0, len(traffic_lines) - 1, 2):
            try:
                out_parts = traffic_lines[i].split()
                in_parts = traffic_lines[i+1].split()
                iftop_list.append({
                    "src": out_parts[1],
                    "dst": out_parts[3],
                    "last_2s": in_parts[3] 
                })
            except:
                continue

        # Get connected devices
        devices = get_connected_devices()

        return {
            "status": "Online",
            "load": load,
            "ping": ping,
            "temp": str(temp),
            "memory": memory,
            "download_mbps": download_mbps,
            "upload_mbps": upload_mbps,
            "total_mbps": total_mbps,
            "iftop": iftop_list,
            "devices": devices,
            "time": datetime.now().strftime("%H:%M:%S"),
            "debug_logs": list(debug_logs)
        }
        
    except subprocess.TimeoutExpired:
        log_debug("ERROR", f"SSH timeout connecting to {ROUTER_IP}")
        return {"status": "Offline", "error": "Connection timeout", "debug_logs": list(debug_logs)}
    except Exception as e:
        error_msg = str(e)
        log_debug("ERROR", f"Failed to fetch data: {error_msg[:100]}")
        return {"status": "Offline", "error": error_msg, "debug_logs": list(debug_logs)}

@app.route('/')
def index():
    """Serve main dashboard"""
    return render_template_string(HTML_TEMPLATE, INTERFACE=INTERFACE)

@app.route('/api/stats')
def api_stats():
    """API endpoint for metrics"""
    return jsonify(get_router_data())

@app.route('/api/debug/clear')
def clear_debug():
    """Clear debug log"""
    debug_logs.clear()
    log_debug("INFO", "Debug log cleared by user")
    return jsonify({"status": "cleared"})

if __name__ == '__main__':
    log_debug("INFO", "Router Monitor V6 starting...")
    app.run(host='0.0.0.0', port=5000, debug=False)
