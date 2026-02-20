"""
OpenHome Ability Plugin for WHM/cPanel API Integration

This plugin provides basic hosting management features through the WHM API.
It includes commands for server resource usage, listing domains, and checking disk usage.

Requirements:
    - Python 3
    - requests library

Configuration:
    All configuration is read from config.json in the same directory.
    Required fields: host, username, api_token, verify_ssl, unique_name, matching_hotwords
"""

from .main import (
    WHMAbility,
    execute_command,
    get_disk_usage,
    get_server_resources,
    initialize,
    list_domains,
)

# Plugin metadata
__version__ = "1.0.0"
__author__ = "OpenHome"
__description__ = "WHM/cPanel API Integration for hosting management"

__all__ = [
    "WHMAbility",
    "execute_command",
    "get_disk_usage",
    "get_server_resources",
    "initialize",
    "list_domains",
    "__version__",
    "__author__",
    "__description__",
]
