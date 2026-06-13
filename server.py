#!/usr/bin/env python3
import http.server
import json
import subprocess
import os
import re
import socket
import time
import base64
import signal
from urllib.parse import urlparse

PORT       = 4000
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Project directory structure ───────────────────────────────
#
#   nano-os/
#   ├── server.py
#   ├── index.html
#   ├── icons/              ← static panel icons
#   ├── noVNC/              ← noVNC git clone (websockify --web points here)
#   └── user-applications/
#       ├── apps.json       ← app registry
#       ├── icons/          ← saved icons
#       └── xstartups/      ← bash scripts built per app
#
APPS_DIR      = os.path.join(SCRIPT_DIR, "user-applications")
ICONS_DIR     = os.path.join(APPS_DIR,   "icons")
XSTARTUPS_DIR = os.path.join(APPS_DIR,   "xstartups")
NOVNC_DIR     = os.path.join(SCRIPT_DIR, "noVNC")
APPS_JSON     = os.path.join(APPS_DIR,   "apps.json")

for _d in [APPS_DIR, ICONS_DIR, XSTARTUPS_DIR]:
    os.makedirs(_d, exist_ok=True)


# ── Shell utility ─────────────────────────────────────────────

def run_cmd(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return None


# ── System stats ──────────────────────────────────────────────

def get_battery():
    out = run_cmd("termux-battery-status")
    if out:
        try:
            return json.loads(out)
        except Exception:
            pass
    return {"percentage": 0, "status": "UNKNOWN", "temperature": 0,
            "plugged": "UNPLUGGED", "health": "UNKNOWN"}

def get_wifi():
    out = run_cmd("termux-wifi-connectioninfo")
    if out:
        try:
            return json.loads(out)
        except Exception:
            pass
    return {"ssid": "unavailable", "ip": "unavailable", "rssi": 0}

def get_system():
    loadavg = "0 0 0"
    try:
        with open("/proc/loadavg") as f:
            loadavg = f.read().strip()
    except Exception:
        pass

    meminfo = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(":")] = int(parts[1])
    except Exception:
        pass

    mem_total     = meminfo.get("MemTotal", 0)
    mem_available = meminfo.get("MemAvailable", 0)
    mem_used      = mem_total - mem_available
    mem_pct       = round((mem_used / mem_total) * 100) if mem_total > 0 else 0

    storage = {"total": 0, "used": 0, "pct": 0}
    try:
        df_out = run_cmd("df /sdcard 2>/dev/null || df /data")
        if df_out:
            lines = df_out.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 4:
                    total_kb = int(parts[1])
                    used_kb  = int(parts[2])
                    pct      = round((used_kb / total_kb) * 100) if total_kb > 0 else 0
                    storage  = {
                        "total": round(total_kb / 1024 / 1024, 1),
                        "used":  round(used_kb  / 1024 / 1024, 1),
                        "pct":   pct,
                    }
    except Exception:
        pass

    load_parts = loadavg.split()
    return {
        "load1":        float(load_parts[0]) if load_parts else 0,
        "load5":        float(load_parts[1]) if len(load_parts) > 1 else 0,
        "load15":       float(load_parts[2]) if len(load_parts) > 2 else 0,
        "mem_total_mb": round(mem_total / 1024),
        "mem_used_mb":  round(mem_used  / 1024),
        "mem_pct":      mem_pct,
        "storage":      storage,
    }


# ── App management ────────────────────────────────────────────

def load_apps():
    try:
        with open(APPS_JSON) as f:
            return json.load(f)
    except Exception:
        return []

def save_apps(apps):
    with open(APPS_JSON, "w") as f:
        json.dump(apps, f, indent=2)

def _port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0

def find_free_display(start=1):
    """First free VNC display (:N → port 5900+N)."""
    for d in range(start, 30):
        if not _port_in_use(5900 + d):
            return d
    return None

def find_free_ws_port(start=6081):
    """First free port for websockify (starts at 6081, 6080 is the main noVNC port)."""
    for port in range(start, 6200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    return None

def create_xstartup(app_id, commands):
    """
    Builds the bash startup script from user-provided commands.

    The user writes the script body (exports, WM, app exec…).
    Only the shebang is inserted automatically — everything else is from the user,
    which ensures high compatibility without unnecessary config files.

    Example `commands`:
        export GTK_THEME=Adwaita:dark
        openbox &
        exec pcmanfm
    """
    lines = ["#!/data/data/com.termux/files/usr/bin/bash", ""]
    lines += commands.strip().splitlines()

    path = os.path.join(XSTARTUPS_DIR, f"{app_id}.sh")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(path, 0o755)
    return path

def create_app(data):
    app_id      = f"app_{int(time.time() * 1000)}"
    name        = data.get("name",        "App").strip()
    description = data.get("description", "").strip()
    commands    = data.get("commands",    "").strip()   # bash script body
    icon_b64    = data.get("icon",        "")           # "data:image/png;base64,..."

    if not commands:
        raise ValueError("Commands are required")

    # ── Save the icon ─────────────────────────────────────────
    icon_url = None
    if icon_b64 and "," in icon_b64:
        header, raw = icon_b64.split(",", 1)
        ext = "png" if "png" in header else "jpg"
        with open(os.path.join(ICONS_DIR, f"{app_id}.{ext}"), "wb") as f:
            f.write(base64.b64decode(raw))
        icon_url = f"/api/apps/{app_id}/icon"

    # ── Build the xstartup (bash script) ──────────────────────
    xstartup = create_xstartup(app_id, commands)

    # ── Find free ports ───────────────────────────────────────
    display  = find_free_display()
    ws_port  = find_free_ws_port()
    if display is None or ws_port is None:
        raise RuntimeError("No free display or websockify port available")
    vnc_port = 5900 + display

    # ── Start the VNC server ──────────────────────────────────
    # -SecurityTypes None → no password (remove if you prefer to use vncpasswd)
    subprocess.Popen(
        ["vncserver", f":{display}",
         "-xstartup", xstartup,
         "-geometry", "1280x720",
         "-depth", "24",
         "-SecurityTypes", "None"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)   # wait for Xvnc to be ready

    # ── Start websockify pointing to the project's noVNC ──────
    # websockify --web ./noVNC  WS_PORT  localhost:VNC_PORT
    ws_proc = subprocess.Popen(
        ["websockify", "--web", NOVNC_DIR,
         str(ws_port), f"localhost:{vnc_port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid,   # own group → killpg works correctly
    )

    app = {
        "id":          app_id,
        "name":        name,
        "description": description,
        "commands":    commands,
        "icon":        icon_url,
        "display":     display,
        "vnc_port":    vnc_port,
        "ws_port":     ws_port,
        "ws_pid":      ws_proc.pid,
    }
    apps = load_apps()
    apps.append(app)
    save_apps(apps)
    return app

def delete_app(app_id):
    apps = load_apps()
    app  = next((a for a in apps if a["id"] == app_id), None)
    if not app:
        return {"error": "App not found"}

    # Kill websockify by group id
    try:
        os.killpg(os.getpgid(app["ws_pid"]), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass

    # Kill the VNC server by display number
    run_cmd(f"vncserver -kill :{app['display']} 2>/dev/null")

    # Remove app files
    for p in [
        os.path.join(ICONS_DIR,     f"{app_id}.png"),
        os.path.join(ICONS_DIR,     f"{app_id}.jpg"),
        os.path.join(XSTARTUPS_DIR, f"{app_id}.sh"),
    ]:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass

    save_apps([a for a in apps if a["id"] != app_id])
    return {"ok": True}


# ── HTTP Handler ──────────────────────────────────────────────

class Handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type",                "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length",              len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type",   content_type)
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if   path == "/api/battery": self.send_json(get_battery())
        elif path == "/api/wifi":    self.send_json(get_wifi())
        elif path == "/api/system":  self.send_json(get_system())
        elif path == "/api/all":
            self.send_json({
                "battery": get_battery(),
                "wifi":    get_wifi(),
                "system":  get_system(),
            })
        elif path == "/api/apps":
            self.send_json(load_apps())

        elif re.match(r"^/api/apps/[^/]+/icon$", path):
            app_id = path.split("/")[3]
            for ext in ["png", "jpg"]:
                icon_path = os.path.join(ICONS_DIR, f"{app_id}.{ext}")
                if os.path.exists(icon_path):
                    self.send_file(icon_path, f"image/{'png' if ext == 'png' else 'jpeg'}")
                    return
            self.send_response(404)
            self.end_headers()

        elif path.startswith("/icons/"):
            icon_path = os.path.join(SCRIPT_DIR, path.lstrip("/"))
            if os.path.isfile(icon_path):
                ext = os.path.splitext(icon_path)[1].lower()
                mime_types = {
                    ".png": "image/png", ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg", ".gif": "image/gif",
                    ".svg": "image/svg+xml", ".webp": "image/webp",
                    ".ico": "image/x-icon",
                }
                self.send_file(icon_path, mime_types.get(ext, "application/octet-stream"))
                return
            self.send_response(404)
            self.end_headers()

        else:
            self.send_file(os.path.join(SCRIPT_DIR, "index.html"),
                           "text/html; charset=utf-8")

    def do_POST(self):
        if urlparse(self.path).path == "/api/apps":
            try:
                length = int(self.headers.get("Content-Length", 0))
                data   = json.loads(self.rfile.read(length))
                app    = create_app(data)
                self.send_json(app, 201)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        m = re.match(r"^/api/apps/([^/]+)$", urlparse(self.path).path)
        if m:
            self.send_json(delete_app(m.group(1)))
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Dashboard running at http://0.0.0.0:{PORT}")
    server.serve_forever()
