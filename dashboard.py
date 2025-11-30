import sys
import os
import threading
import time
import json
import http.server
import socketserver
import webbrowser

# --- 1. Path Setup ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(BASE_DIR, "lib")

if os.path.exists(LIB_DIR) and LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

try:
    import minescript
except ImportError:
    class MockMine:
        def echo(self, m): print(f"[MS] {m}")
        def player_inventory(self): return []
        def chat(self, m): print(f"[Chat] {m}")
    minescript = MockMine()

import job_manager

class Dashboard:
    # Changed default host to 0.0.0.0 to fix Windows connection issues
    def __init__(self, external=False, script_folder="scripts", host="0.0.0.0", port=8999, http_port=8000, auto_open=False):
        self.external = external
        self.host = host
        self.port = port
        self.http_port = http_port
        self.auto_open = auto_open
        
        # Path logic
        if os.path.isabs(script_folder):
            self.script_folder = script_folder
        else:
            self.script_folder = os.path.abspath(os.path.join(BASE_DIR, script_folder))
        
        self.running = False 
        
        self.job_mgr = job_manager.JobManager(script_dir=self.script_folder, send_callback=self.send_to_ui)
        self.dependencies_ready = self._check_deps()

    def _check_deps(self):
        try:
            if self.external:
                import websocket
                self.websocket_lib = websocket
            else:
                from websocket_server import WebsocketServer
                self.WebsocketServer = WebsocketServer
            return True
        except ImportError as e:
            minescript.echo(f"❌ [Dash] Missing Library: {e.name if hasattr(e, 'name') else e}")
            minescript.echo("👉 Run 'setup.py' to install missing libraries.")
            return False

    def start(self):
        if not self.dependencies_ready:
            minescript.echo("🛑 [Dash] Startup Aborted: Missing dependencies.")
            return

        self.running = True
        minescript.echo(f"🚀 [Dash] Starting...")

        if self.external:
            t = threading.Thread(target=self._run_external_client, daemon=True)
            t.start()
        else:
            self._ensure_ui_files()
            t_http = threading.Thread(target=self._run_http_server, daemon=True)
            t_http.start()
            
            t_ws = threading.Thread(target=self._run_internal_server, daemon=True)
            t_ws.start()
            
            # --- AUTO OPEN BROWSER ---
            if self.auto_open:
                # Use localhost for the browser URL, but the server listens on 0.0.0.0
                url = f"http://localhost:{self.http_port}"
                minescript.echo(f"🌍 [Dash] Opening {url} ...")
                threading.Timer(0.5, lambda: webbrowser.open(url)).start()

        minescript.echo("✅ [Dash] Running. Type '\\killjob' to stop.")
        self._main_loop()

    def send_to_ui(self, msg_type, payload):
        try:
            msg = json.dumps({"type": msg_type, "payload": payload})
            if self.external:
                if hasattr(self, 'ws_client') and self.ws_client and self.ws_client.sock and self.ws_client.sock.connected:
                    self.ws_client.send(msg)
            else:
                if hasattr(self, 'ws_server') and self.ws_server:
                    self.ws_server.send_message_to_all(msg)
        except: pass

    def _get_ui_dir(self):
        return os.path.join(BASE_DIR, "ui")

    def _run_http_server(self):
        ui_dir = self._get_ui_dir()
        
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=ui_dir, **kwargs)
            def log_message(self, format, *args): pass
            
        try:
            socketserver.TCPServer.allow_reuse_address = True
            with socketserver.TCPServer(("", self.http_port), Handler) as httpd:
                minescript.echo(f"🌍 [Dash] Web: http://localhost:{self.http_port}")
                httpd.serve_forever()
        except OSError as e:
            minescript.echo(f"❌ [Dash] HTTP Port busy: {e}")

    def _run_internal_server(self):
        def new_client(client, server):
            server.send_message(client, json.dumps({"type": "STATUS", "payload": "connected"}))
            server.send_message(client, json.dumps({"type": "UI_CONFIG", "payload": self.job_mgr.get_ui_config()}))

        def msg_received(client, server, message):
            try:
                self.job_mgr.handle_task(json.loads(message))
            except: pass

        try:
            # Host 0.0.0.0 ensures we listen on all interfaces (IPv4)
            self.ws_server = self.WebsocketServer(host=self.host, port=self.port)
            self.ws_server.set_fn_new_client(new_client)
            self.ws_server.set_fn_message_received(msg_received)
            minescript.echo(f"🔌 [Dash] WS: ws://{self.host}:{self.port}")
            self.ws_server.run_forever()
        except Exception as e:
            minescript.echo(f"❌ [Dash] WS Error: {e}")

    def _run_external_client(self):
        def on_message(ws, message):
            try:
                self.job_mgr.handle_task(json.loads(message))
            except: pass

        def on_open(ws):
            ws.send(json.dumps({"type": "STATUS", "payload": "connected"}))
            ws.send(json.dumps({"type": "UI_CONFIG", "payload": self.job_mgr.get_ui_config()}))
            minescript.echo("✅ [Dash] Connected to Relay.")

        try:
            self.ws_client = self.websocket_lib.WebSocketApp(
                f"ws://{self.host}:{self.port}/",
                on_message=on_message,
                on_open=on_open
            )
            self.ws_client.run_forever()
        except Exception as e:
            minescript.echo(f"❌ [Dash] Conn Error: {e}")

    def _main_loop(self):
        last_inv_scan = 0
        try:
            while self.running:
                if time.time() - last_inv_scan > 1.0:
                    self._scan_inventory()
                    last_inv_scan = time.time()
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    def _scan_inventory(self):
        try:
            inv = minescript.player_inventory()
            data = []
            for item in inv:
                if item:
                    name = getattr(item, 'item', 'air').replace('minecraft:', '')
                    data.append({"name": name, "count": getattr(item, 'count', 1)})
            self.send_to_ui("INVENTORY", data)
        except: pass

    def stop(self):
        self.running = False
        self.job_mgr.stop_all_jobs()
        minescript.echo("👋 [Dash] Stopped.")

    def _ensure_ui_files(self):
        ui_dir = self._get_ui_dir()
        if not os.path.exists(ui_dir): os.makedirs(ui_dir)
        
        index_path = os.path.join(ui_dir, "index.html")
        
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(self._get_default_html())
    
    def _get_default_html(self):
        html = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Minescript C2</title>
    <style>
        :root {
            --bg-dark: #121212;
            --bg-panel: #1e1e1e;
            --accent: #bb86fc;
            --text-main: #e0e0e0;
            --text-dim: #a0a0a0;
            --success: #03dac6;
            --danger: #cf6679;
            --border: #333;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Inter', system-ui, sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-main);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        /* --- Header --- */
        header {
            background: var(--bg-panel);
            padding: 15px 25px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        h1 { font-size: 20px; font-weight: 600; letter-spacing: -0.5px; }
        
        .status-badge {
            font-size: 13px; font-weight: 500;
            padding: 5px 12px; border-radius: 20px;
            background: rgba(255,255,255,0.05);
            display: flex; align-items: center; gap: 8px;
        }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--danger); }
        .connected .dot { background: var(--success); box-shadow: 0 0 8px var(--success); }

        /* --- Main Layout --- */
        .dashboard-grid {
            display: grid;
            grid-template-columns: 300px 1fr 300px; /* 3 Columns */
            gap: 1px; /* Gap for borders */
            background: var(--border); /* Creates border effect */
            height: 100%;
        }

        .column {
            background: var(--bg-dark);
            padding: 20px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        h2 { 
            font-size: 14px; text-transform: uppercase; letter-spacing: 1px; 
            color: var(--text-dim); margin-bottom: 10px; border-bottom: 1px solid var(--border);
            padding-bottom: 8px;
        }

        /* --- Script Cards --- */
        .script-group { margin-bottom: 25px; }
        .script-group-title { font-size: 14px; color: var(--accent); margin-bottom: 10px; font-weight: bold;}
        
        .script-card {
            background: var(--bg-panel);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: transform 0.2s;
        }
        .script-card:hover { border-color: var(--accent); }
        .script-name { font-weight: 600; font-size: 15px; }
        
        .btn {
            border: none; padding: 8px 16px; border-radius: 6px; 
            font-size: 13px; font-weight: 600; cursor: pointer; color: #121212;
            transition: opacity 0.2s;
        }
        .btn:hover { opacity: 0.9; }
        .btn-start { background: var(--success); }
        .btn-stop { background: var(--danger); color: white; }
        .btn-warn { background: #ffb74d; }
        
        /* --- Chat & Logs Tabs --- */
        .tab-container { flex: 1; display: flex; flex-direction: column; background: var(--bg-panel); border-radius: 8px; overflow: hidden; border: 1px solid var(--border); }
        .tabs { display: flex; background: #151515; border-bottom: 1px solid var(--border); }
        .tab {
            flex: 1; padding: 15px; text-align: center; cursor: pointer;
            color: var(--text-dim); font-weight: 600; font-size: 14px;
            transition: background 0.2s;
        }
        .tab.active { background: var(--bg-panel); color: var(--accent); border-bottom: 2px solid var(--accent); }
        .tab:hover:not(.active) { background: #222; }

        .console-view {
            flex: 1; padding: 15px; overflow-y: auto;
            font-family: 'Consolas', monospace; font-size: 13px; line-height: 1.5;
        }
        .console-view div { margin-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 2px;}
        .timestamp { color: var(--text-dim); margin-right: 8px; font-size: 11px; }
        
        .log-sys { color: #aaa; }
        .log-chat { color: #fff; }

        .chat-input-area {
            padding: 10px; background: #151515; border-top: 1px solid var(--border);
            display: flex; gap: 10px;
        }
        input[type="text"] {
            flex: 1; background: #222; border: 1px solid #444; color: white;
            padding: 10px; border-radius: 4px; outline: none;
        }
        input:focus { border-color: var(--accent); }

        /* --- Inventory Grid --- */
        .inv-grid {
            display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
        }
        .inv-slot {
            background: var(--bg-panel); border: 1px solid var(--border);
            aspect-ratio: 1; border-radius: 6px;
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            position: relative;
        }
        .inv-slot img { width: 32px; height: 32px; image-rendering: pixelated; }
        .inv-count {
            position: absolute; bottom: 2px; right: 4px;
            font-size: 11px; color: white; text-shadow: 1px 1px 0 #000; font-weight: bold;
        }
        .inv-tooltip {
            position: absolute; top: -30px; background: #000; color: white;
            padding: 4px 8px; font-size: 10px; border-radius: 4px;
            display: none; z-index: 10; pointer-events: none; white-space: nowrap;
        }
        .inv-slot:hover .inv-tooltip { display: block; }

        /* --- Utility --- */
        .hidden { display: none; }
        .disabled-ui { opacity: 0.5; pointer-events: none; filter: grayscale(1); }

    </style>
</head>
<body>

    <header>
        <h1>Minescript C2</h1>
        <div id="statusBadge" class="status-badge">
            <div class="dot"></div> <span id="statusText">Connecting...</span>
        </div>
    </header>

    <div id="mainLayout" class="dashboard-grid disabled-ui">
        
        <div class="column">
            <h2>Automation Scripts</h2>
            <div id="scriptsContainer">
                </div>
            
            <div style="margin-top: auto;">
                <h2>System Controls</h2>
                <div class="script-card" style="border-color: var(--danger);">
                    <span class="script-name" style="color: var(--danger)">Emergency</span>
                    <button class="btn btn-stop" onclick="sendJson('JOB', {action: 'stop_all'})">STOP ALL</button>
                </div>
                <div class="script-card">
                    <span class="script-name">Listener</span>
                    <button class="btn btn-warn" onclick="sendJson('EXIT', {})">Kill</button>
                </div>
            </div>
        </div>

        <div class="column">
            <h2>Communication Center</h2>
            
            <div class="tab-container">
                <div class="tabs">
                    <div class="tab active" onclick="switchTab('chat')">💬 Global Chat</div>
                    <div class="tab" onclick="switchTab('logs')">📜 System Logs</div>
                </div>

                <div id="view-chat" class="console-view">
                    <div style="color: var(--text-dim); text-align: center; padding-top: 20px;">
                        Waiting for messages...
                    </div>
                </div>

                <div id="view-logs" class="console-view hidden">
                    <div style="color: var(--text-dim);">System initialized.</div>
                </div>

                <div class="chat-input-area">
                    <input type="text" id="chatInput" placeholder="Type a message..." onkeypress="if(event.key==='Enter') sendChat()">
                    <button class="btn btn-start" onclick="sendChat()">Send</button>
                </div>
            </div>
        </div>

        <div class="column">
            <h2>Player Inventory</h2>
            <div id="inventoryGrid" class="inv-grid">
                </div>
        </div>

    </div>

    <script>
        let ws;
        let reconnectInterval;

        const ASSET_BASE_URL = "https://minecraft-api.vercel.app/images/items/";

        function connect() {
            // Updated to use window.location.hostname so it works for 127.0.0.1 and localhost
            ws = new WebSocket('ws://' + window.location.hostname + ':__PORT__');

            ws.onopen = () => {
                setStatus(false, 'Relay Connected');
                clearInterval(reconnectInterval);
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    switch(data.type) {
                        case 'STATUS':
                            if (data.payload === 'connected') {
                                setStatus(true, 'Online');
                            } else {
                                setStatus(false, 'Disconnected');
                                clearUI();
                            }
                            break;
                        
                        case 'UI_CONFIG':
                            renderScripts(data.payload);
                            logMsg('System', 'UI Configuration loaded.');
                            break;

                        case 'INVENTORY':
                            renderInventory(data.payload);
                            break;

                        case 'CHAT_MSG':
                            addMessage('chat', data.payload);
                            break;

                        case 'LOG_MSG':
                            addMessage('logs', data.payload);
                            break;
                            
                        case 'ALERT':
                            alert(data.payload); // Simple alert for now, keeps UI clean
                            break;
                    }
                } catch(e) { console.error(e); }
            };

            ws.onclose = () => {
                setStatus(false, 'Connection Lost');
                reconnectInterval = setInterval(connect, 3000);
            };
        }

        /* --- UI RENDERERS --- */

        function renderScripts(config) {
            const container = document.getElementById('scriptsContainer');
            container.innerHTML = '';

            config.forEach(group => {
                if(group.group.includes("System") || group.group.includes("Controls")) return;

                const groupDiv = document.createElement('div');
                groupDiv.className = 'script-group';
                
                const title = document.createElement('div');
                title.className = 'script-group-title';
                title.innerText = group.group;
                groupDiv.appendChild(title);

                group.buttons.forEach(btn => {
                    if(btn.action === 'stop') return; 

                    const card = document.createElement('div');
                    card.className = 'script-card';
                    
                    const cleanName = btn.label.replace('▶ ', '').replace('Start ', '');
                    const scriptId = btn.payload.script;

                    card.innerHTML = `
                        <span class="script-name">${cleanName}</span>
                        <div style="display:flex; gap:5px">
                            <button class="btn btn-start" onclick="sendJson('JOB', {script: '${scriptId}', action: 'start'})">Start</button>
                        </div>
                    `;
                    groupDiv.appendChild(card);
                });

                container.appendChild(groupDiv);
            });
        }

        function renderInventory(items) {
            const grid = document.getElementById('inventoryGrid');
            grid.innerHTML = '';

            if(items.length === 0) {
                grid.innerHTML = '<div style="grid-column:1/-1; color:#666; text-align:center">Empty</div>';
                return;
            }

            items.forEach(item => {
                const slot = document.createElement('div');
                slot.className = 'inv-slot';
                
                const img = document.createElement('img');
                img.src = `${ASSET_BASE_URL}${item.name}.png`;
                img.onerror = function() { this.style.display='none'; }; 

                slot.innerHTML = `
                    <div class="inv-tooltip">${item.name}</div>
                    <span class="inv-count">${item.count > 1 ? item.count : ''}</span>
                `;
                slot.prepend(img); 
                grid.appendChild(slot);
            });
        }

        function addMessage(target, msg) {
            const view = document.getElementById(target === 'chat' ? 'view-chat' : 'view-logs');
            const div = document.createElement('div');
            const time = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
            
            div.className = target === 'chat' ? 'log-chat' : 'log-sys';
            div.innerHTML = `<span class="timestamp">[${time}]</span> ${msg}`;
            
            view.appendChild(div);
            view.scrollTop = view.scrollHeight;
        }

        /* --- LOGIC --- */

        function switchTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.console-view').forEach(v => v.classList.add('hidden'));
            
            if(tab === 'chat') {
                document.querySelector('.tab:first-child').classList.add('active');
                document.getElementById('view-chat').classList.remove('hidden');
            } else {
                document.querySelector('.tab:last-child').classList.add('active');
                document.getElementById('view-logs').classList.remove('hidden');
            }
        }

        function setStatus(online, text) {
            const badge = document.getElementById('statusBadge');
            const txt = document.getElementById('statusText');
            const layout = document.getElementById('mainLayout');
            
            txt.innerText = text;
            if(online) {
                badge.classList.add('connected');
                layout.classList.remove('disabled-ui');
            } else {
                badge.classList.remove('connected');
                layout.classList.add('disabled-ui');
            }
        }

        function clearUI() {
            document.getElementById('scriptsContainer').innerHTML = '';
            document.getElementById('inventoryGrid').innerHTML = '';
        }

        function sendChat() {
            const input = document.getElementById('chatInput');
            const val = input.value.trim();
            if(val) {
                sendJson('SAY', val);
                input.value = '';
            }
        }

        function sendJson(type, payload) {
            if(ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type, payload }));
            }
        }

        function logMsg(src, msg) {
            addMessage('logs', `[${src}] ${msg}`);
        }

        connect();
    </script>
</body>
</html>"""
        return html.replace("__PORT__", str(self.port))