from threading import Thread
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileDeletedEvent, DirModifiedEvent # Import DirModifiedEvent
from logging.handlers import TimedRotatingFileHandler
import json
import logging
import os
import sys
import asyncio

def load_config(config_path):
	try:
		with open(config_path, "r") as file:
			config = json.load(file)
			return config
	except FileNotFoundError:
		logging.error("Config file not found. Please check the file path.")
	except PermissionError:
		logging.error("Permission denied. Unable to open Config file.")
	except Exception as e:
		logging.error("An error occurred while loading config: " + str(e))
	return None

class ConfigFileHandler(FileSystemEventHandler):
    def __init__(self, config_dir, on_change):
        super().__init__()
        self.config_dir = config_dir
        self.on_change = on_change

    def on_any_event(self, event):
        if event.src_path.startswith(self.config_dir):
            logging.info(f"Change detected in config directory: {event}")
            self.on_change()

def observe_config_changes(on_change_callback):
    config_dir = os.path.dirname(os.path.abspath(config_dir))  # Use absolute path for accuracy
    handler = ConfigFileHandler(config_dir, on_change_callback)
    
    observer = Observer()  # Regular Observer instead of PollingObserver
    observer.schedule(handler, config_dir, recursive=False)  # Watch directory
    observer.start()

    try:
        while True:
            # We could also check for events here but it's usually done by the observer's mechanism.
            pass  
    except KeyboardInterrupt:
        observer.stop()
    finally:
        observer.join()

observer = None

def restart_bot():
    global observer
    logging.info("Restarting bot due to config change.")

    if observer is not None:
        observer.stop()
        observer.join()
        observer = None

    logging.info("Restarting process...")
    os.execv(sys.executable, [sys.executable] + sys.argv)  # Restart process

def handle_config_change():
    logging.info("Exiting program due to config change.")
    restart_bot()

config_path = "./config/config.json"
config_dir = "./config"

def log_setup(config):
    log_level = config.get("LogLevel", "INFO")
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )