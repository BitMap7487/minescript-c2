# 🎮 Minescript C2 (Command & Control)

**Minescript C2** is a powerful, web-based dashboard for [Minescript](https://www.google.com/search?q=https://github.com/Minescript/minescript) that allows you to control your Minecraft automation scripts remotely.

It features a modern "Command and Control" interface with live chat, real-time inventory monitoring, and one-click script execution—all from your browser.

## ✨ Features

  * **Two Operating Modes:**
      * **🏠 Internal Mode:** Hosts the dashboard directly from your Minecraft client (localhost).
      * **☁️ External Mode:** Connects to a remote relay server, allowing you to control your player from anywhere (e.g., via ngrok or a VPS).
  * **📂 Script Manager:** Automatically detects and loads Python scripts from your `scripts/` folder.
  * **💬 Live Communication:** View and send chat messages from the web interface.
  * **🎒 Real-time Inventory:** Monitor your player's inventory updates live.
  * **🛑 Emergency Stop:** Kill all running automation jobs instantly.
  * **📦 Auto-Dependency Management:** Self-contained `lib/` folder installation.

## 📦 Installation

1.  **Download the Code:** Clone this repository or download the source code.

2.  **Install Dependencies:** Run the setup script **once** to install necessary libraries (`websocket-server` and `websocket-client`) into the local `lib/` folder.

    ```python
    # In your Minescript console
    \setup
    ```

    *Note: The dashboard is self-contained. It installs dependencies locally so you don't need to mess with your global Python environment.*

## 🚀 Usage

### Option 1: Internal Mode (Localhost)

Best for single-player or local testing. The dashboard runs on your PC.

1.  Create a `start.py` file:
    ```python
    from dashboard import Dashboard

    # Starts Web Server on port 8000 and WebSocket on 8999
    dash = Dashboard(
        external=False, 
        script_folder="./scripts",
        auto_open=True # Automatically opens your browser
    )
    dash.start()
    ```
2.  Run `\start` in Minecraft.
3.  Your browser will open to `http://localhost:8000`.

### Option 2: External Mode (Remote Control)

Best for controlling your account remotely or sharing access.

1.  **Start the Relay Server** on your PC or VPS (standard Python, not inside Minecraft):
    ```bash
    python relay_server.py
    ```
2.  **Start the Minecraft Client**:
    ```python
    from dashboard import Dashboard

    dash = Dashboard(
        external=True,
        host="localhost", # Or your VPS IP / ngrok URL
        port=9000,        # Relay WebSocket port
        script_folder="./scripts"
    )
    dash.start()
    ```
3.  Open `http://localhost:3000` (or your relay URL) to control your Minecraft client.

## 📂 Project Structure

```text
minescript-c2/
├── dashboard.py       # Core library (Web & WebSocket servers)
├── job_manager.py     # Handles loading and running background jobs
├── setup.py           # Dependency installer
├── relay_server.py    # (Optional) Standalone server for External Mode
├── ui/                # (Generated) Web frontend files
├── lib/               # (Generated) Local Python dependencies
└── scripts/           # PUT YOUR SCRIPTS HERE
    ├── mining.py
    ├── fishing.py
    └── ...
```

## 🛠️ Creating Custom Scripts

Add any `.py` file to the `scripts/` folder. It must have a `run(stop_event)` function.

**Example: `scripts/hello.py`**

```python
import minescript
import time

def run(stop_event):
    minescript.echo("Job started!")
    
    while not stop_event.is_set():
        # Do work here
        minescript.echo("Working...")
        
        # Use wait() on the event instead of time.sleep() for responsive stopping
        if stop_event.wait(5): 
            break
            
    minescript.echo("Job stopped.")
```

## 🤝 Contributing

Feel free to submit issues or pull requests.
