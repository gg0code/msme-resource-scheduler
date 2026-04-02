"""app/core/config.py — thin re-export from app.config"""
from app.config import settings  # noqa: F401

def get_settings():
    return settings
