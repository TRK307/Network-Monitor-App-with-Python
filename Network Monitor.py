import subprocess
import time
import re
from flask import Flask, render_template_string, jsonify
from datetime import datetime

app = Flask(__name__)

# --- CONFIGURATION ---
ROUTER_IP = "10.0.0.1"
INTERFACE = "eth0"
BRIDGE_INTERFACE = "br-lan"
last_state = {"bytes": 0, "time": time.time()}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>NETWORK DASHBOARD</title>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0d0d0f;
            --card-bg: #16161a;
            --border: #232328;
            --panel-accent: #2c2c34; /* Toned down border color */

            /* Muted Semantic Colors */
            --accent-blue: #5baede;
            --accent-purple: #9b87bd;
            --accent-yellow: #d9b86b;
            --accent-orange: #d18e5e;
            --accent-green: #68a67d;
            --accent-red: #b35d5d;
            --accent-pink: #bf6b9b;

            --text-main: #e0e0e4;
            --text-dim: #7a7a82;
        }

        * { box-sizing: border-box; }
        body {
            background-color: var(--bg);
            color: var(--text-main);
            font-family: 'Outfit', sans-serif;
            margin: 0; padding: 40px;
            background-image: radial-gradient(circle at 50% 50%, #1a1a20 0%, #0d0d0f 100%);
            min-height: 100vh;
        }

        .header-bar {
            max-width: 1400px;
            margin: 0 auto 30px auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .status-badge {
            display: flex;
            align-items: center;
            background: #1c1c22;
            padding: 8px 16px;
            border-radius: 30px;
            font-size: 0.85rem;
            font-weight: 600;
            border: 1px solid var(--border);
        }

        .status-dot { width: 8px; height: 8px; border-radius: 50%; margin-right: 10px; }
        .online .status-dot { background: var(--accent-green); opacity: 0.8; }
        .offline .status-dot { background: var(--accent-red); opacity: 0.8; }

        .dashboard-wrapper {
            max-width: 1400px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 24px;
        }

        .panel {
            background: var(--card-bg);
            border: 1px solid var(--panel-accent); /* Toned down border */
            padding: 32px;
            border-radius: 24px;
        }

        h2 {
            font-size: 0.85rem;
            color: var(--text-dim);
            margin: 0 0 20px 0;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            font-weight: 600;
        }

        .value-display { font-size: 5rem; font-weight: 300; letter-spacing: -2px; line-height: 1; transition: color 0.5s ease; }
        .unit { font-size: 1.2rem; color: var(--text-dim); margin-left: 8px; }

        /* Muted Semantic State Classes */
        .color-good { color: var(--accent-green); }
        .color-warn { color: var(--accent-orange); }
        .color-bad { color: var(--accent-red); }

        .meta-grid { display: flex; gap: 30px; margin-top: 20px; border-top: 1px solid var(--border); padding-top: 20px; }
        .meta-item { display: flex; flex-direction: column; }
        .meta-label { font-size: 0.7rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; }
        .meta-val { font-size: 1.1rem; color: var(--text-main); font-weight: 600; }

        .client-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; margin-top: 10px; }
        .client-item {
            background: #1c1c22; padding: 16px; border-radius: 16px; border: 1px solid var(--border);
            display: flex; flex-direction: column; gap: 8px;
        }

        .badge { font-size: 0.6rem; padding: 2px 8px; border-radius: 8px; font-weight: 600; text-transform: uppercase; }
        .badge-conn { background: rgba(91, 174, 222, 0.1); color: var(--accent-blue); }
        .badge-type { background: rgba(255, 255, 255, 0.03); color: var(--text-dim); }

        /* Traffic Streams */
        .iftop-table { width: 100%; border-collapse: collapse; }
        .iftop-row { border-bottom: 1px solid var(--border); }
        .iftop-cell { padding: 12px 0; }
        .iftop-host { color: var(--text-main); font-weight: 500; font-size: 0.8rem; font-family: monospace; }
        .iftop-rate { color: var(--accent-pink); font-family: monospace; text-align: right; font-weight: 600; }

        .tag { font-size: 0.6rem; padding: 1px 5px; border-radius: 4px; font-weight: 700; margin-left: 6px; color: #16161a; }
        .tag-https { background: var(--accent-green); opacity: 0.9; }
        .tag-ssh { background: var(--accent-orange); opacity: 0.9; }
        .tag-speed { background: var(--accent-yellow); opacity: 0.9; }

        .col-span-2 { grid-column: span 2; }
    </style>
</head>
<body>

<div class="header-bar">
    <div style="font-weight: 600; letter-spacing: 1px; color: var(--text-dim);">STATUS</div>
    <div id="status-container" class="status-badge online">
        <div class="status-dot"></div>
        <span id="status-text">ONLINE</span>
    </div>
</div>

<div id="dashboard" class="dashboard-wrapper">
    <div class="panel col-span-2">
        <h2>SPEED</h2>
        <div class="value-display" style="color: var(--accent-green)">
            <span id="mbps">0.00</span><span class="unit">Mbps</span>
        </div>
        <div class="meta-grid">
            <div class="meta-item">
                <span class="meta-label">System Load</span>
                <span class="meta-val" id="load" style="color:var(--accent-purple)">--</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Hardware Link</span>
                <span class="meta-val" id="speed" style="color: var(--accent-blue)">...</span>
            </div>
        </div>
    </div>

    <div class="panel">
        <h2>Latency</h2>
        <div id="ping-display" class="value-display">--</div>
        <span class="meta-label" style="margin-top: 12px; display: block;">Ms to 8.8.8.8</span>
    </div>

    <div class="panel">
        <h2>Live Traffic Streams</h2>
        <div id="iftop-area"></div>
    </div>

    <div class="panel col-span-2">
        <h2>Connected Devices</h2>
        <div class="client-grid" id="client-area"></div>
    </div>
</div>

<script>
    function update() {
        $.getJSON('/api/stats', function(data) {
            if (data.status === "Online") {
                $('#mbps').text(data.total_mbps);
                $('#load').text(data.load);
                $('#speed').text(data.speed);

                const p = parseFloat(data.ping);
                const pingEl = $('#ping-display');
                pingEl.text(p).removeClass('color-good color-warn color-bad');
                if (p < 50) pingEl.addClass('color-good');
                else if (p < 150) pingEl.addClass('color-warn');
                else pingEl.addClass('color-bad');

                let clientHtml = '';
                data.clients.forEach(c => {
                    clientHtml += `
                    <div class="client-item">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-weight:600; font-size:0.95rem;">${c.name}</span>
                            <span class="badge badge-conn">${c.conn}</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
                            <span style="font-family:monospace; color:var(--text-dim); font-size:0.8rem;">${c.ip}</span>
                            <span class="badge badge-type">${c.type}</span>
                        </div>
                    </div>`;
                });
                $('#client-area').html(clientHtml);

                let iftopHtml = '<table class="iftop-table">';
                data.iftop.forEach(f => {
                    let tagHtml = '';
                    if (f.service === 'HTTPS') tagHtml = '<span class="tag tag-https">HTTPS</span>';
                    if (f.service === 'SSH') tagHtml = '<span class="tag tag-ssh">SSH</span>';
                    if (f.service === 'SPEED') tagHtml = '<span class="tag tag-speed">SPEED</span>';

                    iftopHtml += `
                    <tr class="iftop-row">
                        <td class="iftop-cell">
                            <div><span class="iftop-host">${f.source}</span>${tagHtml}</div>
                            <div style="font-size:0.7rem; color:var(--text-dim); margin-top:2px;">${f.dest}</div>
                        </td>
                        <td class="iftop-cell iftop-rate">${f.rate}</td>
                    </tr>`;
                });
                iftopHtml += '</table>';
                $('#iftop-area').html(iftopHtml);
            }
        });
    }
    setInterval(update, 3000);
    update();
</script>
</body>
</html>
"""

def identify_service(host_port):
    hp = host_port.lower()
    if ':443' in hp: return "HTTPS"
    if ':22' in hp: return "SSH"
    if ':8080' in hp or 'ookla' in hp: return "SPEED"
    return None

def guess_device_type(name):
    name = name.lower()
    if any(k in name for k in ['iphone', 'android', 'phone']): return "Mobile"
    if any(k in name for k in ['desktop', 'pc', 'laptop']): return "PC"
    return "Generic"

def get_router_data():
    global last_state
    ssh_base = f"ssh -o ConnectTimeout=2 -o BatchMode=yes root@{ROUTER_IP}"
    cmd = f"{ssh_base} \"ethtool {INTERFACE} 2>/dev/null | grep Speed; cat /proc/loadavg; ping -c 1 8.8.8.8 | grep 'time='; grep {INTERFACE} /proc/net/dev; iw station dump; cat /tmp/dhcp.leases; iftop -t -s 1 -L 8 -i {BRIDGE_INTERFACE} -P 2>/dev/null\""

    try:
        raw_output = subprocess.check_output(cmd, shell=True, timeout=10).decode(errors='ignore')

        speed = (re.search(r'Speed:\s+(\d+\w+/s)', raw_output) or re.search(r'', '')).group(1) if 'Speed:' in raw_output else "Unknown"
        load = (re.search(r'(\d+\.\d+)', raw_output) or re.search(r'', '')).group(1) if raw_output else "0.00"
        ping = (re.search(r'time=(\d+\.?\d*)', raw_output) or re.search(r'', '')).group(1) if 'time=' in raw_output else "0"

        byte_match = re.search(rf'{INTERFACE}:\s*(\d+)', raw_output)
        current_bytes = int(byte_match.group(1)) if byte_match else 0
        wifi_macs = set(re.findall(r'Station ([a-f0-9:]{17})', raw_output.lower()))

        clients = []
        lease_matches = re.findall(r'\d+\s+([a-f0-9:]{17})\s+(\d+\.\d+\.\d+\.\d+)\s+(\S+)', raw_output.lower())
        for mac, ip, name in lease_matches:
            clean_name = name.replace('"', '').title() if name != "*" else "Unknown Device"
            clients.append({"ip": ip, "name": clean_name, "conn": "WiFi" if mac in wifi_macs else "LAN", "type": guess_device_type(clean_name)})

        iftop_results = []
        lines = raw_output.splitlines()
        for i in range(len(lines)):
            if "=>" in lines[i] and i+1 < len(lines):
                src_parts = re.split(r'\s+', lines[i].strip())
                if len(src_parts) > 3:
                    iftop_results.append({
                        "source": src_parts[1],
                        "dest": re.split(r'\s+', lines[i+1].strip())[1],
                        "rate": src_parts[-3].replace('[', '').replace(']', ''),
                        "service": identify_service(src_parts[1])
                    })

        now = time.time()
        time_diff = now - last_state['time']
        byte_diff = max(0, current_bytes - last_state['bytes'])
        total_mbps = round(((byte_diff * 8) / 1024 / 1024) / time_diff, 2) if last_state['bytes'] > 0 else 0.00
        last_state = {"bytes": current_bytes, "time": now}

        return {"status": "Online", "speed": speed, "load": load, "ping": ping, "total_mbps": total_mbps, "clients": clients, "iftop": iftop_results}
    except Exception as e:
        return {"status": "Offline", "error": str(e)}

@app.route('/api/stats')
def api_stats(): return jsonify(get_router_data())

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
