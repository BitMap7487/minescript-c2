"""
Download all dependencies to lib/ folder
Run this once: python setup.py
"""

import subprocess
import sys
import os

# Define lib directory relative to this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(BASE_DIR, "lib")

if not os.path.exists(LIB_DIR):
    os.makedirs(LIB_DIR)

# We need BOTH libraries: one for client mode, one for server mode
dependencies = [
    "websocket-client", # For connecting to external relays
    "websocket-server", # For hosting local dashboard
]

print(f"Installing to: {LIB_DIR}")

for dep in dependencies:
    print(f"Downloading {dep}...")
    try:
        subprocess.run([
            sys.executable, "-m", "pip", "install",
            "--target", str(LIB_DIR),
            "--upgrade",
            "--no-user", # Force install to target, ignore user scope
            dep
        ], check=True)
        print(f"Installed {dep}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to install {dep}")

print("Setup complete! You can now run your dashboard.")