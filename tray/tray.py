import os
import subprocess
import sys
import threading
import atexit
import ctypes
from pathlib import Path
from PIL import Image
import pystray

# --- Configuration ---
APP_NAME = "shairport-sync-windows"
APP_DATA_DIR = Path(os.getenv('APPDATA')) / APP_NAME
CONFIG_FILE_NAME = "shairport-sync.conf"
CONFIG_FILE_PATH = APP_DATA_DIR / CONFIG_FILE_NAME
CORE_EXECUTABLE = "shairport-sync.exe"

# --- Default Config File Content ---
# This is the config file we create on first launch.
DEFAULT_CONFIG_CONTENT = """
// Default configuration for shairport-sync-windows
// This file is managed by the tray application.
// You can edit it by right-clicking the tray icon.

general = {
// This is the name your computer will broadcast on the network.
// %h = hostname (your computer's name)
name = "Shairport Sync on %h";

// This sets the audio backend.
// We compiled with "ao" (libao) for Windows support.
output_backend = "ao";
};

// Configuration for the "ao" (libao) backend.
// No special parameters are needed for Windows.
ao = {
// dev = "default"; // (default)
};

sessioncontrol = {
// This allows the connection to be interrupted by another user.
allow_session_interruption = "yes";
};
"""

def get_resource_path(relative_path):
""" Get absolute path to resource, works for dev and for PyInstaller """
try:
# PyInstaller creates a temp folder and stores path in _MEIPASS
base_path = sys._MEIPASS
except Exception:
base_path = os.path.abspath(".")

return os.path.join(base_path, relative_path)

# --- Class: ConfigManager ---
# Manages the shairport-sync.conf file in %APPDATA%
class ConfigManager:
def __init__(self, app_dir, config_path, default_content):
self.app_dir = app_dir
self.config_path = config_path
self.default_content = default_content

def ensure_config_exists(self):
"""Creates the config directory and default file if they don't exist."""
try:
self.app_dir.mkdir(parents=True, exist_ok=True)
if not self.config_path.exists():
with open(self.config_path, 'w', encoding='utf-8') as f:
f.write(self.default_content)
print(f"Created default config at {self.config_path}")
except Exception as e:
print(f"Error creating config file: {e}")
# We can still try to run, shairport-sync might find a default
pass

def open_config(self):
"""Opens the config file in the default text editor."""
try:
os.startfile(self.config_path)
except Exception as e:
print(f"Error opening config file: {e}")

# --- Class: ServerManager ---
# Manages the shairport-sync.exe subprocess
class ServerManager:
def __init__(self, core_exe_path, config_file_path):
self.core_exe_path = core_exe_path
self.config_file_path = str(config_file_path) # Must be a string for subprocess
self.process = None
self.running = False

def start(self):
if self.running or self.process:
print("Server already running.")
return

print(f"Starting {CORE_EXECUTABLE}...")
try:
# We must launch shairport-sync.exe using the --configfile flag [23, 24]
# We also hide the console window using CREATE_NO_WINDOW
self.process = subprocess.Popen(
[self.core_exe_path, "--configfile", self.config_file_path],
stdout=subprocess.PIPE,
stderr=subprocess.PIPE,
stdin=subprocess.PIPE,
creationflags=subprocess.CREATE_NO_WINDOW
)
self.running = True
print(f"Server started. PID: {self.process.pid}")
except Exception as e:
print(f"Failed to start server: {e}")
self.process = None
self.running = False

def stop(self):
if not self.running or not self.process:
print("Server not running.")
return

print("Stopping server...")
try:
self.process.terminate()
self.process.wait(timeout=5)
print("Server terminated.")
except subprocess.TimeoutExpired:
print("Server did not terminate, killing...")
self.process.kill()
self.process.wait()
print("Server killed.")
except Exception as e:
print(f"Error stopping server: {e}")
finally:
self.process = None
self.running = False

def restart(self):
print("Restarting server...")
self.stop()
# Short delay to ensure ports are freed
threading.Timer(1.0, self.start).start()

# --- Class: AutoStartManager ---
# Manages the "Run on Startup" registry key
# This is a direct adaptation from the uxplay-windows model
class AutoStartManager:
def __init__(self, app_name, app_path):
self.app_name = app_name
self.app_path = f'"{app_path}"' # Ensure path is quoted for registry
self.reg_key = r"Software\Microsoft\Windows\CurrentVersion\Run"

def _get_key(self, access):
import winreg
try:
return winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.reg_key, 0, access)
except Exception as e:
print(f"Error opening registry key: {e}")
return None

def is_enabled(self):
import winreg
key = self._get_key(winreg.KEY_READ)
if not key:
return False

try:
winreg.QueryValueEx(key, self.app_name)
winreg.CloseKey(key)
return True
except FileNotFoundError:
winreg.CloseKey(key)
return False
except Exception as e:
print(f"Error querying registry: {e}")
winreg.CloseKey(key)
return False

def set_enabled(self, enabled):
import winreg
key = self._get_key(winreg.KEY_WRITE)
if not key:
return

try:
if enabled:
winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, self.app_path)
print("Autostart enabled.")
else:
winreg.DeleteValue(key, self.app_name)
print("Autostart disabled.")
winreg.CloseKey(key)
except Exception as e:
print(f"Error setting registry value: {e}")
winreg.CloseKey(key)

# --- Class: TrayIcon ---
# Manages the pystray icon and its menu
class TrayIcon:
def __init__(self, server_manager, config_manager, autostart_manager):
self.server_manager = server_manager
self.config_manager = config_manager
self.autostart_manager = autostart_manager

self.icon_path = get_resource_path("icon.ico")
try:
    self.icon_image = Image.open(self.icon_path)
except FileNotFoundError:
    # Create a dummy 16x16 white image as a placeholder
    self.icon_image = Image.new('RGB', (16, 16), color = 'white')

self.icon = pystray.Icon(APP_NAME, self.icon_image, APP_NAME, menu=self.create_menu())

# Ensure server is stopped when tray icon exits
atexit.register(self.server_manager.stop)

def create_menu(self):
return pystray.Menu(
pystray.MenuItem("Start Server", self.on_start, enabled=lambda item: not self.server_manager.running),
pystray.MenuItem("Stop Server", self.on_stop, enabled=lambda item: self.server_manager.running),
pystray.MenuItem("Restart Server", self.on_restart),
pystray.Menu.SEPARATOR,
pystray.MenuItem("Edit Configuration", self.on_edit_config),
pystray.MenuItem("Run on Startup", self.on_toggle_autostart, checked=lambda item: self.autostart_manager.is_enabled()),
pystray.Menu.SEPARATOR,
pystray.MenuItem("Exit", self.on_exit)
)

def update_menu(self):
"""Refreshes the menu items to update enabled/disabled state."""
self.icon.menu = self.create_menu()
self.icon.update_menu()

def on_start(self, icon, item):
self.server_manager.start()
self.update_menu()

def on_stop(self, icon, item):
self.server_manager.stop()
self.update_menu()

def on_restart(self, icon, item):
self.server_manager.restart()
# We need a slight delay to update the menu after the restart thread kicks in
threading.Timer(1.5, self.update_menu).start()

def on_edit_config(self, icon, item):
self.config_manager.open_config()

def on_toggle_autostart(self, icon, item):
current_state = self.autostart_manager.is_enabled()
self.autostart_manager.set_enabled(not current_state)

def on_exit(self, icon, item):
print("Exiting...")
self.server_manager.stop()
icon.stop()

def run(self):
print("Tray icon running.")
self.server_manager.start() # Start server on launch
self.icon.run()

# --- Main Execution ---
def main():
# Ensure only one instance is running
# This is a direct adaptation from the uxplay-windows model
try:
mutex = ctypes.windll.kernel32.CreateMutexW(None, True, APP_NAME)
if ctypes.windll.kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
print("Another instance is already running. Exiting.")
sys.exit(0)
except Exception as e:
print(f"Mutex check failed: {e}")
# Not fatal, continue anyway

# Determine executable paths
# sys.executable is the path to shairport-sync-windows.exe (built by PyInstaller)
# CORE_EXECUTABLE (shairport-sync.exe) is in the *same directory*.
executable_path = sys.executable
base_install_dir = Path(executable_path).parent
core_exe_path = base_install_dir / CORE_EXECUTABLE

if not core_exe_path.exists():
print(f"FATAL: Core executable not found at {core_exe_path}")
print("This app must be run from its installation directory.")
sys.exit(1)

print(f"App Name: {APP_NAME}")
print(f"App Path: {executable_path}")
print(f"Core Exe Path: {core_exe_path}")
print(f"Config Dir: {APP_DATA_DIR}")

# Initialize managers
config_mgr = ConfigManager(APP_DATA_DIR, CONFIG_FILE_PATH, DEFAULT_CONFIG_CONTENT)
server_mgr = ServerManager(core_exe_path, CONFIG_FILE_PATH)
autostart_mgr = AutoStartManager(APP_NAME, executable_path)

# Prepare config and start tray
config_mgr.ensure_config_exists()
tray = TrayIcon(server_mgr, config_mgr, autostart_mgr)
tray.run()

if __name__ == "__main__":
main()
