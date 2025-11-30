import sys
import os
import json
import http.server
import socketserver
import threading
import re

# --- PATH SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(BASE_DIR, "lib")
if os.path.exists(LIB_DIR) and LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

try:
    from websocket_server import WebsocketServer
except ImportError:
    print("❌ Error: 'websocket-server' not found.")
    print(f"   Ensure 'lib' folder exists or run: pip install websocket-server")
    sys.exit(1)

# --- CONFIGURATION ---
WS_PORT = 8999
WS_HOST = "0.0.0.0" # IPv4 Only. Clients must connect via 127.0.0.1 (not localhost)
HTTP_PORT = 8000 

# Track the specific Minescript client
minescript_client = None
clients = []

# --- 1. WebSocket Logic ---
def new_client(client, server):
    print(f"[{client['id']}] Client connected from {client['address']}")
    clients.append(client)
    
    # Unlike before, we do NOT say "connected" yet.
    # We check if Minescript is already here.
    if minescript_client is not None:
         server.send_message(client, json.dumps({"type": "STATUS", "payload": "connected"}))
    else:
         server.send_message(client, json.dumps({"type": "STATUS", "payload": "disconnected"}))

def client_left(client, server):
    global minescript_client
    if client in clients:
        clients.remove(client)
    
    # If the disconnected client was Minescript, tell everyone!
    if minescript_client == client:
        print(f"[{client['id']}] 🚨 Minescript Disconnected!")
        minescript_client = None
        server.send_message_to_all(json.dumps({"type": "STATUS", "payload": "disconnected"}))
    else:
        print(f"[{client['id']}] Web Client Disconnected")

def message_received(client, server, message):
    global minescript_client
    try:
        data = json.loads(message)
        
        # LOGIC MATCHING NODE.JS:
        # Check if this message is the "I am Minescript" handshake
        if data.get("type") == "STATUS" and data.get("payload") == "connected":
            print(f"[{client['id']}] ✅ Minescript Identified!")
            minescript_client = client
            # Now tell everyone (Web UI) that we are Online
            server.send_message_to_all(message)
            return

    except: pass
    
    # Broadcast all other messages (Commands, Inventory, Chat)
    server.send_message_to_all(message)

def run_websocket():
    print(f"🔌 WS Relay listening on {WS_HOST}:{WS_PORT}")
    print(f"   ⚠️  NOTE: Minecraft Client MUST connect to '127.0.0.1' (not localhost)")
    try:
        server = WebsocketServer(host=WS_HOST, port=WS_PORT)
        server.set_fn_new_client(new_client)
        server.set_fn_client_left(client_left)
        server.set_fn_message_received(message_received)
        server.run_forever()
    except OSError as e:
        print(f"❌ WebSocket Error: Port {WS_PORT} busy. Stop Node.js first.")
        os._exit(1)

# --- 2. Web Server Logic ---
def run_http():
    web_root = BASE_DIR
    if os.path.exists(os.path.join(BASE_DIR, "ui", "index.html")):
        web_root = os.path.join(BASE_DIR, "ui")
    
    os.chdir(web_root)

    class RelayHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/" or self.path == "/index.html":
                try:
                    if os.path.exists("index.html"):
                        with open("index.html", "r", encoding="utf-8") as f:
                            content = f.read()
                        
                        # Inject correct port for the browser
                        patch = f"new WebSocket('ws://' + window.location.hostname + ':{WS_PORT}')"
                        content = re.sub(r"new WebSocket\(['\"].*?['\"]\)", patch, content)
                        
                        self.send_response(200)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        self.wfile.write(content.encode("utf-8"))
                        return
                except Exception: pass
            super().do_GET()

    print(f"🌍 Website running at http://localhost:{HTTP_PORT}")
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", HTTP_PORT), RelayHandler) as httpd:
            httpd.serve_forever()
    except OSError:
        print(f"❌ HTTP Error: Port {HTTP_PORT} is busy.")
        os._exit(1)

if __name__ == "__main__":
    t = threading.Thread(target=run_websocket, daemon=True)
    t.start()
    run_http()