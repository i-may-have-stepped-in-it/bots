from threading import Thread
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
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
	def __init__(self, config_path, on_change):
		super().__init__()
		self.config_path = config_path
		self.on_change = on_change

	def on_modified(self, event):
		if event.src_path == self.config_path:
			logging.info("Config file has been modified. Exiting...")
			self.on_change()

def observe_config_changes(on_change_callback):

	handler = ConfigFileHandler(config_path, on_change_callback)
	observer = PollingObserver()
	observer.schedule(handler, os.path.dirname(config_path), recursive=False)
	observer.start()

	try:
		while True:
			observer.join(1)
	except KeyboardInterrupt:
		observer.stop()
		observer.join()

observer = None  # Ensure observer is defined globally

async def restart_bot():
	global observer
	logging.info("Restarting bot due to config change.")

	if observer is not None:
		observer.stop()
		observer.join()
		observer = None  # Reset observer to avoid issues

	logging.info("Restarting process...")
	os.execv(sys.executable, [sys.executable] + sys.argv)  # Restart process

def handle_config_change():
	logging.info("Exiting program due to config change.")
	
	# Ensure we are not in an active event loop
	try:
		asyncio.get_running_loop().stop()
	except RuntimeError:
		pass

	asyncio.run(restart_bot())  # ✅ Restart the bot properly

config_path = "./config/config.json"

def log_setup(config):
	log_level = config.get("LogLevel", "INFO")
	logging.basicConfig(
		level=log_level,
		format="%(asctime)s [%(levelname)s] %(message)s",
		handlers=[
			TimedRotatingFileHandler("app.log", when="midnight", backupCount=7, encoding='utf-8'),
			logging.StreamHandler(sys.stdout)
		]
	)