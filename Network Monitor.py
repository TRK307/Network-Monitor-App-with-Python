import subprocess
import time
import logging
from flask import Flask, render_template_string, jsonify, request
from datetime import datetime
from collections import deque

app = Flask(__name__)

# --- CONFIGURATION ---
ROUTER_IP = "10.0.0.1"
INTERFACE = "eth0"        # WAN
LAN_INTERFACE = "br-lan"  # For Traffic Analysis
CPU_CORES = 4             # ARMv7 quad-core — used to normalise load average to 0-100 %

# Enhanced state tracking
last_state = {
    "rx_bytes": 0,
    "tx_bytes": 0,
    "time": time.time()
}

# Debug log storage (keep last 25 entries)
debug_logs = deque(maxlen=25)

# Uptime tracking
start_time = time.time()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TRAFFIC CLASSIFICATION
# ---------------------------------------------------------------------------
# Well-known destination IPs / ranges mapped to service names.
# Checked in order — first match wins.
IP_SERVICE_MAP = [
    # YouTube
    ("142.250.",  "youtube"),
    ("172.217.",  "youtube"),
    ("173.194.",  "youtube"),
    ("216.58.",   "youtube"),
    # Netflix
    ("52.85.",    "netflix"),
    ("54.148.",   "netflix"),
    ("52.44.",    "netflix"),
    ("23.171.",   "netflix"),
    # Google (generic, after youtube so YT wins first)
    ("142.250.",  "google"),
    ("172.217.",  "google"),
    ("173.194.",  "google"),
    ("216.58.",   "google"),
    ("142.251.",  "google"),
    # Facebook / Meta
    ("31.13.",    "facebook"),
    ("157.240.",  "facebook"),
    ("173.252.",  "facebook"),
    ("204.79.",   "facebook"),
    # WhatsApp (owned by Meta, distinct IP blocks)
    ("182.16.",   "whatsapp"),
    ("184.89.",   "whatsapp"),
    # TikTok / ByteDance
    ("34.82.",    "tiktok"),
    ("52.8.",     "tiktok"),
    ("151.101.",  "tiktok"),
    # Spotify
    ("34.243.",   "spotify"),
    ("35.167.",   "spotify"),
    ("52.4.",     "spotify"),
    # Discord
    ("162.159.",  "discord"),
    ("104.16.",   "discord"),
    # Cloudflare (CDN — many sites ride on it)
    ("104.16.",   "cloudflare"),
    ("104.17.",   "cloudflare"),
    ("104.18.",   "cloudflare"),
    ("104.19.",   "cloudflare"),
    ("104.20.",   "cloudflare"),
    ("104.21.",   "cloudflare"),
    ("131.0.",    "cloudflare"),
    ("141.101.", "cloudflare"),
    ("172.64.",   "cloudflare"),
    ("190.93.",   "cloudflare"),
    # Amazon / AWS
    ("52.",       "amazon"),
    ("54.",       "amazon"),
    ("13.",       "amazon"),
    ("99.",       "amazon"),
    # Microsoft / Azure
    ("20.",       "microsoft"),
    ("40.",       "microsoft"),
    ("52.",       "microsoft"),
    # Apple
    ("17.",       "apple"),
]

# Well-known ports → traffic-type label.  Checked after IP classification.
PORT_SERVICE_MAP = {
    "443":  "HTTPS",
    "80":   "HTTP",
    "22":   "SSH",
    "53":   "DNS",
    "8443": "HTTPS",
    "8080": "HTTP",
    "993":  "IMAIL",
    "587":  "SMTP",
    "25":   "SMTP",
    "21":   "FTP",
    "3389": "RDP",
    "5000": "MONITOR",
}


def classify_connection(dst_ip, dst_port):
    """
    Return (label, css_class).
    Strategy:
      1. Try IP-range map for known services (YouTube, Netflix, etc.)
      2. Fall back to port-based protocol label (HTTPS, SSH, etc.)
      3. Default to UNKNOWN
    """
    # --- IP-based service detection ---
    for prefix, service in IP_SERVICE_MAP:
        if dst_ip.startswith(prefix):
            return service.upper(), f"svc-{service}"

    # --- Port-based protocol detection ---
    label = PORT_SERVICE_MAP.get(dst_port, None)
    if label:
        return label, f"proto-{label.lower()}"

    # Last resort: show the port number itself
    return f"PORT {dst_port}", "proto-other"


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


# ---------------------------------------------------------------------------
# HTML / CSS / JS — single-page template
# ---------------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Network Monitor</title>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        /* ============================================================
           DRACULA THEME — base palette
           ============================================================ */
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
        .card:hover { border-color: var(--purple); }

        .full-width  { grid-column: span 4; }
        .half-width  { grid-column: span 2; }

        /* ---- Typography & card headers ---- */
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

        .color-purple { color: var(--purple); }
        .color-cyan   { color: var(--cyan); }
        .color-green  { color: var(--green); }
        .color-orange { color: var(--orange); }
        .color-pink   { color: var(--pink); }
        .color-red    { color: var(--red); }
        .color-yellow { color: var(--yellow); }

        /* ---- Status tags ---- */
        .status-tag {
            font-size: 0.55rem;
            padding: 3px 8px;
            border: 1px solid var(--card-border);
            border-radius: 3px;
            background: var(--bg-darker);
            color: var(--cyan);
            font-weight: 500;
        }

        /* ---- Tables ---- */
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
        .dest-ip   { color: var(--cyan); }
        .bw-val    { color: var(--green); text-align: right; font-weight: 600; }

        /* ============================================================
           TRAFFIC-TYPE BADGES  (colour-coded labels on iftop rows)
           ============================================================ */
        .traffic-badge {
            display: inline-block;
            font-size: 0.52rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            padding: 2px 7px;
            border-radius: 3px;
            margin-left: 6px;
            vertical-align: middle;
        }
        /* --- known services --- */
        .svc-youtube   { background: #ff0000; color: #fff; }
        .svc-netflix   { background: #e50914; color: #fff; }
        .svc-facebook  { background: #1877f2; color: #fff; }
        .svc-whatsapp  { background: #25d366; color: #1e1f29; }
        .svc-tiktok    { background: #010101; color: #fff; border: 1px solid #3d4054; }
        .svc-spotify   { background: #1db954; color: #1e1f29; }
        .svc-discord   { background: #5865f2; color: #fff; }
        .svc-google    { background: #4285f4; color: #fff; }
        .svc-amazon    { background: #ff9900; color: #1e1f29; }
        .svc-microsoft { background: #0078d4; color: #fff; }
        .svc-apple     { background: #555555; color: #fff; }
        .svc-cloudflare{ background: #f48120; color: #1e1f29; }
        /* --- protocol labels --- */
        .proto-https   { background: var(--green);  color: var(--bg); }
        .proto-http    { background: var(--yellow); color: var(--bg); }
        .proto-ssh     { background: var(--purple); color: var(--bg); }
        .proto-dns     { background: var(--cyan);   color: var(--bg); }
        .proto-imail   { background: var(--pink);   color: var(--bg); }
        .proto-smtp    { background: var(--pink);   color: var(--bg); }
        .proto-ftp     { background: var(--orange); color: var(--bg); }
        .proto-rdp     { background: var(--red);    color: #fff; }
        .proto-monitor { background: var(--comment);color: var(--text); }
        .proto-other   { background: var(--bg-darker); color: var(--text-muted); border: 1px solid var(--card-border); }

        /* ============================================================
           ACTION BUTTONS  (inline in header — Dracula palette)
           ============================================================ */
        .action-btn {
            font-family: inherit;
            font-size: 0.52rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            padding: 4px 10px;
            border-radius: 4px;
            border: 1px solid transparent;
            cursor: pointer;
            transition: opacity 0.2s, transform 0.1s;
        }
        .action-btn:hover  { opacity: 0.8; }
        .action-btn:active { transform: scale(0.95); }
        .action-btn:disabled { opacity: 0.3; cursor: not-allowed; transform: none; }

        .btn-flush {
            background: var(--cyan);
            color: var(--bg);
        }
        .btn-soft-reboot {
            background: var(--purple);
            color: var(--bg);
        }

        .action-status {
            font-size: 0.52rem;
            color: var(--comment);
            font-style: italic;
            white-space: nowrap;
        }
        .action-status.ok   { color: var(--green); }
        .action-status.err  { color: var(--red); }

        /* ============================================================
           CONFIRMATION MODAL
           ============================================================ */
        .modal-overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.6);
            z-index: 100;
            justify-content: center;
            align-items: center;
        }
        .modal-overlay.show { display: flex; }

        .modal {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 28px 32px;
            max-width: 380px;
            width: 90%;
            box-shadow: 0 8px 32px rgba(0,0,0,0.5);
        }
        .modal h3 {
            margin: 0 0 8px;
            font-size: 0.85rem;
            color: var(--text);
            font-weight: 700;
        }
        .modal p {
            margin: 0 0 20px;
            font-size: 0.75rem;
            color: var(--comment);
            line-height: 1.5;
        }
        .modal-buttons {
            display: flex;
            gap: 10px;
            justify-content: flex-end;
        }
        .btn-cancel {
            font-family: inherit;
            font-size: 0.6rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            padding: 6px 14px;
            border-radius: 4px;
            border: 1px solid var(--card-border);
            background: var(--bg-darker);
            color: var(--text-muted);
            cursor: pointer;
        }
        .btn-cancel:hover { border-color: var(--comment); }

        .btn-confirm {
            font-family: inherit;
            font-size: 0.6rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            padding: 6px 14px;
            border-radius: 4px;
            border: none;
            cursor: pointer;
            color: #fff;
        }
        .btn-confirm.danger  { background: var(--purple); color: var(--bg); }
        .btn-confirm.warning { background: var(--cyan);   color: var(--bg); }

        /* ============================================================
           DEBUG CONSOLE
           ============================================================ */
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
        .debug-entry:last-child { border-bottom: none; }
        .debug-time    { color: var(--comment); min-width: 70px; }
        .debug-level   { min-width: 50px; font-weight: 600; }
        .debug-level.INFO    { color: var(--cyan); }
        .debug-level.SUCCESS { color: var(--green); }
        .debug-level.WARNING { color: var(--orange); }
        .debug-level.ERROR   { color: var(--red); }
        .debug-message { color: var(--text); flex: 1; }

        .debug-console::-webkit-scrollbar       { width: 6px; }
        .debug-console::-webkit-scrollbar-track  { background: var(--bg); }
        .debug-console::-webkit-scrollbar-thumb  { background: var(--comment); border-radius: 3px; }
        .debug-console::-webkit-scrollbar-thumb:hover { background: var(--purple); }

        /* ============================================================
           SPEED METRICS
           ============================================================ */
        .speed-container {
            display: flex;
            justify-content: space-between;
            gap: 20px;
        }
        .speed-metric { flex: 1; }
        .speed-metric .value { font-size: 3.2rem; font-weight: 700; }
        .speed-metric .unit-label {
            font-size: 0.75rem;
            color: var(--comment);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            font-weight: 600;
        }

        /* ============================================================
           CPU GRID
           ============================================================ */
        .cpu-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-top: 10px;
        }
        .cpu-metric { display: flex; flex-direction: column; }
        .cpu-metric .metric-label {
            font-size: 0.65rem;
            color: var(--comment);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
            font-weight: 600;
        }
        .cpu-metric .metric-value { font-size: 2.2rem; font-weight: 700; line-height: 1; }
        .cpu-metric .metric-unit  { font-size: 0.7rem; color: var(--text-muted); margin-top: 4px; }

        .temp-bar, .load-bar {
            height: 6px;
            background: var(--bg-darker);
            border-radius: 3px;
            margin-top: 8px;
            overflow: hidden;
        }
        .temp-fill, .load-fill {
            height: 100%;
            border-radius: 3px;
            transition: width 0.5s ease, background-color 0.5s ease;
        }

        /* ============================================================
           CONNECTED DEVICES GRID
           ============================================================ */
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
        .device-item.status-offline { opacity: 0.5; border-style: dashed; }
        .device-item:hover { border-color: var(--purple); opacity: 1; }

        .device-info   { flex: 1; min-width: 0; }
        .device-name   { font-size: 0.85rem; font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .device-ip     { font-size: 0.7rem; color: var(--comment); font-family: 'Monaco', monospace; }
        .device-connection { font-size: 0.55rem; padding: 2px 6px; border-radius: 3px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }

        .conn-wifi-5g  { background: var(--purple); color: var(--bg); }
        .conn-wifi-2g  { background: var(--orange); color: var(--bg); }
        .conn-lan      { background: var(--cyan);   color: var(--bg); }
        .conn-offline  { background: var(--card-border); color: var(--text-muted); }
        .conn-unknown  { background: var(--comment); color: var(--bg); }

        /* ============================================================
           HTOP PROCESS TABLE
           ============================================================ */
        .proc-table td { font-size: 0.75rem; padding: 7px 8px; }
        .proc-table .proc-name { color: var(--cyan); font-weight: 600; font-family: 'Fira Code', monospace; }
        .proc-table .proc-mem  { color: var(--orange); text-align: right; font-weight: 600; }
        .proc-table .proc-pid  { color: var(--comment); text-align: right; }
        .proc-table .proc-state { font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.5px; }
        .proc-table .state-S   { color: var(--green); }
        .proc-table .state-R   { color: var(--yellow); }
        .proc-table .state-D   { color: var(--red); }
        .proc-table .state-Z   { color: var(--red); }

        /* ============================================================
           HEADER
           ============================================================ */
        .connection-status {
            display: inline-block;
            width: 8px; height: 8px;
            border-radius: 50%;
            background: var(--green);
            animation: pulse 2s infinite;
            margin-right: 6px;
        }
        .connection-status.offline { background: var(--red); animation: none; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50%      { opacity: 0.5; }
        }

        .header-stats { display: flex; gap: 15px; align-items: center; }
        .mini-stat { display: flex; align-items: center; gap: 6px; font-size: 0.55rem; color: var(--comment); }
        .mini-stat-value { color: var(--cyan); font-weight: 600; }

        /* ============================================================
           FOOTER
           ============================================================ */
        .footer {
            grid-column: span 4;
            text-align: center;
            padding-top: 25px;
            font-size: 0.6rem;
            color: var(--comment);
            text-transform: uppercase;
            letter-spacing: 4px;
        }
    </style>
</head>
<body>
<div class="dashboard">

    <!-- ======================================================
         HEADER BAR  — status · router uptime · action buttons · clock
         ====================================================== -->
    <div class="card full-width" style="padding: 12px 18px;">
        <h2 style="margin: 0;">
            <span>
                <span id="connection-indicator" class="connection-status"></span>
                ROUTER MONITOR V7
            </span>
            <span class="header-stats">
                <span class="mini-stat">
                    <span>ROUTER UPTIME:</span>
                    <span class="mini-stat-value" id="router-uptime">--</span>
                </span>
                <button class="action-btn btn-flush" id="btn-flush-dhcp" onclick="confirmAction('flush-dhcp')">⟳ Flush DHCP</button>
                <button class="action-btn btn-soft-reboot" id="btn-reboot" onclick="confirmAction('reboot')">⏻ Soft Reboot</button>
                <span id="flush-status"  class="action-status"></span>
                <span id="reboot-status" class="action-status"></span>
                <span id="clock" class="status-tag">00:00:00</span>
            </span>
        </h2>
    </div>

    <!-- ======================================================
         TOP METRIC CARDS — Latency | Memory | CPU (half)
         ====================================================== -->
    <div class="card">
        <h2>Latency <span class="status-tag">LIVE</span></h2>
        <div id="ping-val" class="value color-purple">--</div>
        <div class="unit">MS / GOOGLE DNS</div>
    </div>

    <div class="card">
        <h2>Memory <span class="status-tag">HTOP LOGIC</span></h2>
        <div id="mem-val" class="value color-green">--</div>
        <div class="unit">USAGE % (NO CACHE)</div>
    </div>

    <div class="card half-width">
        <h2>CPU & System Metrics <span class="status-tag">LIVE</span></h2>
        <div class="cpu-grid">
            <div class="cpu-metric">
                <div class="metric-label">CPU Load</div>
                <div id="load-val" class="metric-value color-cyan">--</div>
                <div class="metric-unit">LOAD % (4-CORE AVG)</div>
                <div class="load-bar"><div id="load-fill" class="load-fill" style="width:0%"></div></div>
            </div>
            <div class="cpu-metric">
                <div class="metric-label">CPU Temp</div>
                <div id="temp-val" class="metric-value color-orange">--</div>
                <div class="metric-unit">°C / ROUTER THERMAL</div>
                <div class="temp-bar"><div id="temp-fill" class="temp-fill" style="width:0%"></div></div>
            </div>
        </div>
        <div id="temp-status" class="unit" style="margin-top:12px; color:var(--comment); text-align:center;">Reading sensors...</div>
    </div>

    <!-- ======================================================
         NETWORK THROUGHPUT
         ====================================================== -->
    <div class="card full-width">
        <h2>Network Throughput <span class="status-tag">{{ INTERFACE }}</span></h2>
        <div class="speed-container">
            <div class="speed-metric">
                <div class="unit-label">⬇ DOWNLOAD</div>
                <div id="download-speed" class="value color-green">0.00 <span class="unit" style="display:inline;margin:0;font-size:1.2rem;">Mbps</span></div>
            </div>
            <div class="speed-metric">
                <div class="unit-label">⬆ UPLOAD</div>
                <div id="upload-speed" class="value color-pink">0.00 <span class="unit" style="display:inline;margin:0;font-size:1.2rem;">Mbps</span></div>
            </div>
            <div class="speed-metric">
                <div class="unit-label">⇅ TOTAL</div>
                <div id="total-speed" class="value color-yellow">0.00 <span class="unit" style="display:inline;margin:0;font-size:1.2rem;">Mbps</span></div>
            </div>
        </div>
    </div>

    <!-- ======================================================
         CONNECTED DEVICES
         ====================================================== -->
    <div class="card full-width">
        <h2>Connected Devices <span class="status-tag" id="device-count">0 DEVICES</span></h2>
        <div class="devices-grid" id="devices-grid">
            <div class="device-item">
                <div class="device-info">
                    <div class="device-name">Loading...</div>
                    <div class="device-ip">Scanning network</div>
                </div>
            </div>
        </div>
    </div>

    <!-- ======================================================
         ACTIVE SOCKET CONNECTIONS  (iftop + traffic badges)
         ====================================================== -->
    <div class="card full-width">
        <h2>Active Socket Connections <span class="status-tag" id="conn-count">0 ACTIVE</span></h2>
        <table>
            <thead>
                <tr>
                    <th width="22%">Source</th>
                    <th width="3%" style="text-align:center"></th>
                    <th width="35%">Destination</th>
                    <th width="20%">Traffic Type</th>
                    <th width="20%" style="text-align:right">Bandwidth</th>
                </tr>
            </thead>
            <tbody id="iftop-body">
                <tr><td colspan="5" style="text-align:center; color:var(--comment);">Initializing...</td></tr>
            </tbody>
        </table>
    </div>

    <!-- ======================================================
         SYSTEM PROCESSES
         ====================================================== -->
    <div class="card full-width">
        <h2>System Processes <span class="status-tag" id="proc-count">0 PROCESSES</span></h2>
        <table class="proc-table">
            <thead>
                <tr>
                    <th width="8%">PID</th>
                    <th width="28%">Process</th>
                    <th width="10%">State</th>
                    <th width="14%" style="text-align:right">Memory</th>
                    <th width="40%">Command</th>
                </tr>
            </thead>
            <tbody id="proc-body">
                <tr><td colspan="5" style="text-align:center; color:var(--comment);">Loading processes...</td></tr>
            </tbody>
        </table>
    </div>

    <!-- ======================================================
         DEBUG CONSOLE
         ====================================================== -->
    <div class="card full-width">
        <h2>System Debug Console <span class="status-tag" id="debug-count">0 ENTRIES</span></h2>
        <div class="debug-console" id="debug-console">
            <div class="debug-entry">
                <span class="debug-time">--:--:--</span>
                <span class="debug-level INFO">INFO</span>
                <span class="debug-message">Waiting for data...</span>
            </div>
        </div>
    </div>

    <!-- ======================================================
         CONFIRMATION MODAL  (shared by both action buttons)
         ====================================================== -->
    <div class="modal-overlay" id="modal-overlay">
        <div class="modal">
            <h3 id="modal-title">Confirm Action</h3>
            <p id="modal-body">Are you sure?</p>
            <div class="modal-buttons">
                <button class="btn-cancel" onclick="closeModal()">Cancel</button>
                <button class="btn-confirm danger" id="modal-confirm" onclick="executeAction()">Confirm</button>
            </div>
        </div>
    </div>

    <div class="footer">
        GL-AX1800 // MONITOR_V7 // DRACULA_THEME // TRAFFIC CLASSIFICATION
    </div>
</div>

<!-- ============================================================
     JAVASCRIPT
     ============================================================ -->
<script>
    let updateCounter = 0;
    let consecutiveErrors = 0;
    const monitorStartTime = Date.now();

    // --- Modal / Action state ---
    let pendingAction = null;   // 'flush-dhcp' | 'reboot'

    // ---- helpers ----
    function formatSpeed(mbps) { return parseFloat(mbps).toFixed(2); }

    function getTempColor(t)  { return t<50?'var(--green)':t<70?'var(--yellow)':t<85?'var(--orange)':'var(--red)'; }
    function getTempWidth(t)  { return Math.min(100, t); }
    function getLoadColor(l)  { return l<50?'var(--green)':l<75?'var(--yellow)':l<90?'var(--orange)':'var(--red)'; }
    function getLoadWidth(l)  { return Math.min(100, l); }

    function formatUptime(seconds) {
        const d = Math.floor(seconds/86400),
              h = Math.floor((seconds%86400)/3600),
              m = Math.floor((seconds%3600)/60);
        if (d > 0) return d+'d '+h+'h '+m+'m';
        if (h > 0) return h+'h '+m+'m';
        return m+'m';
    }

    // ---- Modal logic ----
    const modalCfg = {
        'flush-dhcp': {
            title: 'Flush DHCP Leases',
            body:  'This will clear all current DHCP leases on the router. All connected devices will need to re-acquire an IP address. The router will NOT restart.',
            confirmClass: 'warning',
            confirmText:  'Flush Leases'
        },
        'reboot': {
            title: 'Soft Reboot Router',
            body:  'This sends a soft reboot command via SSH. All network connections will drop for 30–60 seconds while the router restarts. Proceed only when necessary.',
            confirmClass: 'danger',
            confirmText:  'Soft Reboot'
        }
    };

    function confirmAction(action) {
        pendingAction = action;
        const cfg = modalCfg[action];
        $('#modal-title').text(cfg.title);
        $('#modal-body').text(cfg.body);
        $('#modal-confirm').attr('class', 'btn-confirm ' + cfg.confirmClass).text(cfg.confirmText);
        $('#modal-overlay').addClass('show');
    }

    function closeModal() {
        $('#modal-overlay').removeClass('show');
        pendingAction = null;
    }

    function executeAction() {
        closeModal();
        if (!pendingAction) return;

        const action = pendingAction;
        pendingAction = null;

        // Disable the button while request is in-flight
        const btnId   = action === 'flush-dhcp' ? '#btn-flush-dhcp' : '#btn-reboot';
        const statusId = action === 'flush-dhcp' ? '#flush-status'   : '#reboot-status';

        $(btnId).prop('disabled', true);
        $(statusId).text('Processing...').attr('class', 'action-status');

        $.ajax({
            url:  '/api/action/' + action,
            type: 'POST',
            success: function(data) {
                $(btnId).prop('disabled', false);
                $(statusId).text(data.message).attr('class', 'action-status ok');
                // auto-clear after 6 s
                setTimeout(function(){ $(statusId).text(''); }, 6000);
            },
            error: function(xhr) {
                $(btnId).prop('disabled', false);
                const msg = xhr.responseJSON ? xhr.responseJSON.error : 'Request failed';
                $(statusId).text(msg).attr('class', 'action-status err');
                setTimeout(function(){ $(statusId).text(''); }, 6000);
            }
        });
    }

    // Close modal if user clicks outside
    $('#modal-overlay').on('click', function(e) {
        if ($(e.target).is('#modal-overlay')) closeModal();
    });

    // ---- Render helpers ----
    function updateDebugConsole(logs) {
        let html = '';
        logs.slice().reverse().forEach(function(log) {
            html += '<div class="debug-entry">' +
                '<span class="debug-time">'+log.time+'</span>' +
                '<span class="debug-level '+log.level+'">'+log.level+'</span>' +
                '<span class="debug-message">'+log.message+'</span>' +
                '</div>';
        });
        $('#debug-console').html(html || '<div class="debug-entry"><span class="debug-message">No logs</span></div>');
        $('#debug-count').text(logs.length + ' ENTRIES');
    }

    function updateDevices(devices) {
        if (!devices || !devices.length) {
            $('#devices-grid').html('<div class="device-item" style="grid-column:1/-1;"><div class="device-info" style="text-align:center;color:var(--comment);">No devices detected</div></div>');
            $('#device-count').text('0 DEVICES');
            return;
        }
        devices.sort(function(a,b){ return (a.status==='online'?0:1) - (b.status==='online'?0:1); });
        const onlineCount = devices.filter(function(d){ return d.status==='online'; }).length;

        let html = '';
        devices.forEach(function(dev) {
            let connClass, connText, itemClass = 'device-item';
            if (dev.status === 'online') {
                if (dev.connection === 'wifi') {
                    connClass = dev.band==='5g' ? 'conn-wifi-5g' : 'conn-wifi-2g';
                    connText  = dev.band==='5g' ? '5G WIFI'      : '2.4G WIFI';
                } else if (dev.connection === 'lan') {
                    connClass = 'conn-lan'; connText = 'LAN';
                } else {
                    connClass = 'conn-unknown'; connText = 'UNKNOWN';
                }
            } else {
                connClass = 'conn-offline'; connText = 'OFFLINE'; itemClass += ' status-offline';
            }
            html += '<div class="'+itemClass+'">' +
                '<div class="device-info"><div class="device-name">'+dev.hostname+'</div><div class="device-ip">'+dev.ip+'</div></div>' +
                '<span class="device-connection '+connClass+'">'+connText+'</span></div>';
        });
        $('#devices-grid').html(html);
        $('#device-count').text(onlineCount+'/'+devices.length+' ONLINE');
    }

    function updateProcesses(procs) {
        if (!procs || !procs.length) {
            $('#proc-body').html('<tr><td colspan="5" style="text-align:center;color:var(--comment);">No process data</td></tr>');
            $('#proc-count').text('0 PROCESSES');
            return;
        }
        let html = '';
        procs.forEach(function(p) {
            const stateClass = 'state-' + (p.state || 'S');
            html += '<tr>' +
                '<td class="proc-pid">'+p.pid+'</td>' +
                '<td class="proc-name">'+p.name+'</td>' +
                '<td class="proc-state '+stateClass+'">'+p.state+'</td>' +
                '<td class="proc-mem">'+p.rss_mb+' MB</td>' +
                '<td style="color:var(--comment);font-size:0.65rem;font-family:Fira Code,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="'+p.cmd+'">'+p.cmd+'</td>' +
                '</tr>';
        });
        $('#proc-body').html(html);
        $('#proc-count').text(procs.length + ' PROCESSES');
    }

    // ---- Main polling loop ----
    function refresh() {
        updateCounter++;

        $.getJSON('/api/stats').done(function(data) {
            consecutiveErrors = 0;
            $('#connection-indicator').removeClass('offline');

            if (data.status !== 'Online') { $('#connection-indicator').addClass('offline'); return; }

            // Latency
            let ping = parseInt(data.ping);
            $('#ping-val').text(ping).attr('class','value '+(ping<30?'color-green':ping<70?'color-yellow':'color-red'));

            // CPU load
            let load = parseFloat(data.load);
            $('#load-val').text(load.toFixed(1)+'%');
            $('#load-fill').css({ width: getLoadWidth(load)+'%', 'background-color': getLoadColor(load) });

            // Temperature
            if (data.temp !== '--') {
                let temp = parseFloat(data.temp);
                $('#temp-val').text(temp.toFixed(1)+'°');
                $('#temp-fill').css({ width: getTempWidth(temp)+'%', 'background-color': getTempColor(temp) });
                $('#temp-status').html(
                    temp>80 ? '⚠ HIGH – Monitor router cooling' :
                    temp>70 ? '⚡ Warm but acceptable' :
                              '✓ Normal operating temp'
                ).css('color', getTempColor(temp));
            } else {
                $('#temp-val').text('--');
                $('#temp-fill').css('width','0%');
                $('#temp-status').html('✗ Sensor unavailable').css('color','var(--red)');
            }

            // Memory
            $('#mem-val').text(data.memory+'%');

            // Throughput
            $('#download-speed').html(formatSpeed(data.download_mbps)+' <span class="unit" style="display:inline;margin:0;font-size:1.2rem;">Mbps</span>');
            $('#upload-speed').html(formatSpeed(data.upload_mbps)+' <span class="unit" style="display:inline;margin:0;font-size:1.2rem;">Mbps</span>');
            $('#total-speed').html(formatSpeed(data.total_mbps)+' <span class="unit" style="display:inline;margin:0;font-size:1.2rem;">Mbps</span>');

            // Uptime / clock
            if (data.router_uptime) $('#router-uptime').text(data.router_uptime);
            $('#clock').text(data.time);

            // ---- Active connections with traffic badges ----
            let rows = '';
            data.iftop.slice(0,10).forEach(function(f) {
                rows += '<tr>' +
                    '<td class="source-ip">'+f.src+'</td>' +
                    '<td style="text-align:center;color:var(--comment);">↔</td>' +
                    '<td class="dest-ip">'+f.dst+'</td>' +
                    '<td><span class="traffic-badge '+f.badge_class+'">'+f.label+'</span></td>' +
                    '<td class="bw-val">'+f.last_2s+'</td>' +
                    '</tr>';
            });
            $('#iftop-body').html(rows || '<tr><td colspan="5" style="text-align:center;color:var(--comment);">NO ACTIVE CONNECTIONS</td></tr>');
            $('#conn-count').text(data.iftop.length+' TOTAL (TOP 10)');

            // ---- Processes ----
            if (data.processes) updateProcesses(data.processes);

            // ---- Debug ----
            if (data.debug_logs) updateDebugConsole(data.debug_logs);

            // ---- Devices ----
            if (data.devices) updateDevices(data.devices);

        }).fail(function() {
            consecutiveErrors++;
            $('#connection-indicator').addClass('offline');
        });
    }

    setInterval(refresh, 2500);
    refresh();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# BACKEND — data fetchers
# ---------------------------------------------------------------------------

def get_router_uptime():
    ssh_base = f"ssh -o ConnectTimeout=3 -o BatchMode=yes root@{ROUTER_IP}"
    try:
        result = subprocess.check_output(
            f"{ssh_base} \"cat /proc/uptime | cut -d' ' -f1\"",
            shell=True, timeout=5
        ).decode().strip()
        s = int(float(result))
        d, h, m = s // 86400, (s % 86400) // 3600, (s % 3600) // 60
        if d > 0: return f"{d}d {h}h {m}m"
        if h > 0: return f"{h}h {m}m"
        return f"{m}m"
    except Exception as e:
        log_debug("WARNING", f"Router uptime: {str(e)[:40]}")
        return "--"


def get_connected_devices():
    ssh_base = f"ssh -o ConnectTimeout=3 -o BatchMode=yes root@{ROUTER_IP}"
    try:
        log_debug("INFO", "Scanning network devices...")
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

        known_devices, active_arp, wifi_mac_bands = {}, {}, {}
        section, current_band = 'arp', None

        for line in result.split('\n'):
            line = line.strip()
            if not line: continue
            if '---WIFI_SCAN---' in line: section = 'wifi'; continue
            if '---DHCP---'     in line: section = 'dhcp'; continue

            if section == 'arp':
                parts = line.split()
                if len(parts) >= 3:
                    ip, mac = parts[0], parts[1]
                    if mac != '00:00:00:00:00:00':
                        active_arp[ip] = mac

            elif section == 'wifi':
                if line.startswith('IFACE'):
                    parts = line.split()
                    if len(parts) >= 3:
                        current_band = '5g' if int(parts[2]) > 4000 else '2.4g'
                else:
                    mac = line.lower()
                    if len(mac) == 17 and current_band:
                        wifi_mac_bands[mac] = current_band

            elif section == 'dhcp':
                parts = line.split()
                if len(parts) >= 4:
                    mac, ip, hostname = parts[1].lower(), parts[2], parts[3]
                    if hostname == '*': hostname = f"Unknown ({ip.split('.')[-1]})"
                    known_devices[mac] = { 'mac': mac, 'ip': ip, 'hostname': hostname,
                                           'status': 'offline', 'connection': 'lan', 'band': '' }

        for ip, mac in active_arp.items():
            if mac in known_devices:
                known_devices[mac]['status'] = 'online'
            else:
                known_devices[mac] = { 'mac': mac, 'ip': ip, 'hostname': ip,
                                       'status': 'online', 'connection': 'lan', 'band': '' }

        for mac, band in wifi_mac_bands.items():
            if mac in known_devices:
                known_devices[mac]['status'] = 'online'
                known_devices[mac]['connection'] = 'wifi'
                known_devices[mac]['band'] = band

        device_list = sorted(known_devices.values(),
                             key=lambda x: (0 if x['status']=='online' else 1,
                                            [int(p) for p in x['ip'].split('.') if p.isdigit()]))
        online = sum(1 for d in device_list if d['status']=='online')
        log_debug("SUCCESS", f"Found {len(device_list)} devices ({online} online)")
        return device_list

    except Exception as e:
        log_debug("ERROR", f"Device scan failed: {str(e)[:60]}")
        return []


def get_processes():
    """
    Pull top-15 processes sorted by RSS (memory) via BusyBox ps on OpenWrt.
    BusyBox ps on OpenWrt 21.02 does NOT support 'auxo' or keyword field lists.
    We use 'ps -eo' with the short column names it actually understands.
    """
    ssh_base = f"ssh -o ConnectTimeout=3 -o BatchMode=yes root@{ROUTER_IP}"
    try:
        # BusyBox ps -eo columns: pid, vsz, rss, stat, comm, args
        # We sort by rss descending (highest memory consumers first) and take 16 lines (header + 15)
        cmd = (f'{ssh_base} "'
               f'ps -eo pid,vsz,rss,stat,comm,args 2>/dev/null | sort -t\\  -k3 -rn | head -16'
               f'"')
        raw = subprocess.check_output(cmd, shell=True, timeout=5).decode().strip().split('\n')

        # Log first two lines so we can see the actual header/format if something goes wrong
        if len(raw) > 0:
            log_debug("INFO", f"ps header: {raw[0][:70]}")
        if len(raw) > 1:
            log_debug("INFO", f"ps first: {raw[1][:70]}")

        procs = []
        for line in raw:
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 5)
            if len(parts) < 5:
                continue
            # Skip header line (first token will be the column name, not a number)
            if not parts[0].isdigit():
                continue

            pid, vsz, rss_kb, state, name = parts[0], parts[1], parts[2], parts[3], parts[4]
            cmd_str = parts[5] if len(parts) > 5 else name

            try:
                rss_mb = round(int(rss_kb) / 1024, 1)
            except ValueError:
                rss_mb = 0

            procs.append({
                'pid':   pid,
                'state': state[0] if state else 'S',
                'name':  name,
                'cmd':   cmd_str,
                'rss_mb': rss_mb
            })

        log_debug("SUCCESS", f"Fetched {len(procs)} processes")
        return procs
    except Exception as e:
        log_debug("ERROR", f"Process fetch failed: {str(e)[:60]}")
        return []


def get_router_data():
    """Fetch all router metrics via SSH"""
    global last_state
    ssh_base = f"ssh -o ConnectTimeout=3 -o BatchMode=yes root@{ROUTER_IP}"

    # --- Core metrics (single SSH round-trip) ---
    cmd = (
        f"{ssh_base} \""
        f"cat /proc/loadavg | cut -d' ' -f1; "
        f"ping -c 1 8.8.8.8 | grep 'time=' | cut -d'=' -f4 | sed 's/ ms//' || echo 0; "
        f"grep {INTERFACE} /proc/net/dev | awk '{{print \\$2,\\$10}}'; "
        f"cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || "
        f"cat /sys/devices/virtual/thermal/thermal_zone0/temp 2>/dev/null || "
        f"cat /sys/class/hwmon/hwmon0/temp1_input 2>/dev/null || "
        f"echo 0; "
        f"awk '/MemTotal/ {{t=\\$2}} /MemAvailable/ {{a=\\$2}} END {{printf \\\"%d\\\", ((t-a)/t)*100}}' /proc/meminfo"
        f"\""
    )

    try:
        log_debug("INFO", f"SSH query to {ROUTER_IP}...")
        raw = subprocess.check_output(cmd, shell=True, timeout=10).decode().strip().split('\n')
        log_debug("SUCCESS", "Router responded successfully")

        # load_raw is the 1-min load average.  On a 4-core system it can reach 4.0.
        # Divide by core count so the bar and percentage are always 0–100.
        load_percentage = round((float(raw[0]) / CPU_CORES) * 100, 1)
        ping = raw[1]
        log_debug("INFO", f"Latency: {ping}ms")

        net_stats = raw[2].split()
        current_rx = int(net_stats[0]) if len(net_stats) > 0 and net_stats[0].isdigit() else 0
        current_tx = int(net_stats[1]) if len(net_stats) > 1 and net_stats[1].isdigit() else 0

        temp_raw = raw[3]
        if temp_raw.isdigit():
            t = int(temp_raw)
            temp = round(float(t) if t < 200 else t / 1000, 1)
        else:
            temp = "--"

        memory = raw[4] if raw[4].isdigit() else "0"

        # Speed calc
        now = time.time()
        time_diff = now - last_state['time']
        if time_diff > 0:
            rx_diff = max(0, current_rx - last_state['rx_bytes'])
            tx_diff = max(0, current_tx - last_state['tx_bytes'])
            download_mbps = round(((rx_diff * 8) / 1024 / 1024) / time_diff, 2)
            upload_mbps   = round(((tx_diff * 8) / 1024 / 1024) / time_diff, 2)
            total_mbps    = round(download_mbps + upload_mbps, 2)
            if total_mbps > 0.1:
                log_debug("INFO", f"Traffic: ↓{download_mbps}Mbps ↑{upload_mbps}Mbps")
        else:
            download_mbps = upload_mbps = total_mbps = 0.0

        last_state = { "rx_bytes": current_rx, "tx_bytes": current_tx, "time": now }

        # --- iftop (separate SSH call, isolated output) ---
        log_debug("INFO", f"Polling iftop on {LAN_INTERFACE}...")
        iftop_cmd = (
            f"{ssh_base} \""
            f"iftop -i {LAN_INTERFACE} -t -s 2 -n -N -P -L 20 2>/dev/null"
            f"\""
        )
        iftop_list = []
        try:
            iftop_raw   = subprocess.check_output(iftop_cmd, shell=True, timeout=8).decode()
            iftop_lines = iftop_raw.strip().split('\n')
            log_debug("SUCCESS", f"iftop returned {len(iftop_lines)} lines")

            i = 0
            while i < len(iftop_lines) - 1:
                out_line = iftop_lines[i]
                in_line  = iftop_lines[i + 1]

                if '=>' in out_line and '<=' in in_line:
                    try:
                        left, right = out_line.split('=>')
                        src = left.strip()
                        right_parts = right.split()
                        # right_parts[0] = dst_ip  right_parts[1] = dst_port (because -P flag)
                        # With -P the format is  ip:port  but some builds use space-separated.
                        # Handle both "ip:port" and "ip port" formats.
                        dst_token = right_parts[0]
                        if ':' in dst_token:
                            dst_ip, dst_port = dst_token.rsplit(':', 1)
                        elif len(right_parts) > 1 and right_parts[1].isdigit():
                            dst_ip, dst_port = dst_token, right_parts[1]
                        else:
                            dst_ip, dst_port = dst_token, '443'   # default guess HTTPS

                        # Also strip port from src if present
                        if ':' in src:
                            src = src.rsplit(':', 1)[0]

                        in_parts = in_line.split()
                        bw_2s = in_parts[-1] if in_parts else '0'

                        # Classify the connection
                        label, badge_class = classify_connection(dst_ip, dst_port)

                        if src and dst_ip:
                            iftop_list.append({
                                "src":        src,
                                "dst":        dst_ip,
                                "last_2s":    bw_2s,
                                "label":      label,
                                "badge_class": badge_class
                            })
                    except:
                        pass
                    i += 2
                else:
                    i += 1

            if iftop_list:
                log_debug("SUCCESS", f"Parsed {len(iftop_list)} connections")
            else:
                log_debug("WARNING", "iftop returned no connection pairs")

        except subprocess.TimeoutExpired:
            log_debug("WARNING", "iftop timed out")
        except Exception as e:
            log_debug("ERROR", f"iftop parse: {str(e)[:60]}")

        # --- Processes ---
        processes = get_processes()

        # --- Devices ---
        devices = get_connected_devices()
        router_uptime = get_router_uptime()

        return {
            "status":         "Online",
            "load":           str(load_percentage),
            "ping":           ping,
            "temp":           str(temp),
            "memory":         memory,
            "download_mbps":  download_mbps,
            "upload_mbps":    upload_mbps,
            "total_mbps":     total_mbps,
            "iftop":          iftop_list,
            "devices":        devices,
            "processes":      processes,
            "router_uptime":  router_uptime,
            "time":           datetime.now().strftime("%H:%M:%S"),
            "debug_logs":     list(debug_logs)
        }

    except subprocess.TimeoutExpired:
        log_debug("ERROR", f"SSH timeout to {ROUTER_IP}")
        return {"status": "Offline", "error": "Connection timeout", "debug_logs": list(debug_logs)}
    except Exception as e:
        log_debug("ERROR", f"Query failed: {str(e)[:80]}")
        return {"status": "Offline", "error": str(e), "debug_logs": list(debug_logs)}


# ---------------------------------------------------------------------------
# FLASK ROUTES
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, INTERFACE=INTERFACE)

@app.route('/api/stats')
def api_stats():
    return jsonify(get_router_data())

@app.route('/api/debug/clear')
def clear_debug():
    debug_logs.clear()
    log_debug("INFO", "Debug log cleared")
    return jsonify({"status": "cleared"})

@app.route('/api/action/flush-dhcp', methods=['POST'])
def action_flush_dhcp():
    """Clear DHCP leases on the router without restarting it."""
    ssh_base = f"ssh -o ConnectTimeout=3 -o BatchMode=yes root@{ROUTER_IP}"
    try:
        log_debug("WARNING", "Flushing DHCP leases...")
        # Remove the lease file and signal dnsmasq to reload
        cmd = (f'{ssh_base} "'
               f'> /tmp/dhcp.leases; '
               f'/etc/init.d/dnsmasq restart'
               f'"')
        subprocess.check_output(cmd, shell=True, timeout=10)
        log_debug("SUCCESS", "DHCP leases flushed — dnsmasq restarted")
        return jsonify({"message": "✓ DHCP leases flushed successfully"})
    except Exception as e:
        log_debug("ERROR", f"DHCP flush failed: {str(e)[:60]}")
        return jsonify({"error": f"Flush failed: {str(e)[:60]}"}), 500

@app.route('/api/action/reboot', methods=['POST'])
def action_reboot():
    """Reboot the router (non-blocking — fire and forget)."""
    ssh_base = f"ssh -o ConnectTimeout=3 -o BatchMode=yes root@{ROUTER_IP}"
    try:
        log_debug("WARNING", "Router reboot requested...")
        # Use sleep 1 so the SSH session has time to close cleanly before the reboot fires
        subprocess.Popen(
            f'{ssh_base} "sleep 1 && reboot"',
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        log_debug("SUCCESS", "Reboot command sent — router rebooting...")
        return jsonify({"message": "✓ Reboot command sent — router is rebooting"})
    except Exception as e:
        log_debug("ERROR", f"Reboot failed: {str(e)[:60]}")
        return jsonify({"error": f"Reboot failed: {str(e)[:60]}"}), 500


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    log_debug("INFO",    "Router Monitor V7 starting...")
    log_debug("SUCCESS", f"Monitoring {ROUTER_IP} on {INTERFACE}")
    log_debug("INFO",    f"iftop tracking on {LAN_INTERFACE} with traffic classification")
    app.run(host='0.0.0.0', port=5000, debug=False)
