import os

DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
PORT = int(os.environ.get("PORT", 8080))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
