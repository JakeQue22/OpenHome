"""
OpenHome Ability Plugin for WHM/cPanel API Integration

This plugin provides comprehensive hosting management features through the WHM API.
It includes commands for server resources, accounts, domains, disk usage,
bandwidth, SSL, services, and more.

Requirements:
    - Python 3
    - requests library

Configuration:
    All configuration is managed via hardcoded defaults (overridden by OpenHome dashboard).
    Required fields: host, username, api_token, verify_ssl, unique_name, matching_hotwords
"""

from .main import (
    WhmCpanelControlCapability,
    execute_command,
    get_disk_usage,
    get_server_resources,
    initialize,
    list_domains,
    list_accounts,
    suspend_account,
    unsuspend_account,
    get_bandwidth,
    get_hostname,
    restart_service,
)

# Plugin metadata
__version__ = "1.0.0"
__author__ = "OpenHome"
__description__ = "WHM/cPanel API Integration for hosting management"

__all__ = [
    "WhmCpanelControlCapability",
    "execute_command",
    "get_disk_usage",
    "get_server_resources",
    "initialize",
    "list_domains",
    "list_accounts",
    "suspend_account",
    "unsuspend_account",
    "get_bandwidth",
    "get_hostname",
    "restart_service",
    "__version__",
    "__author__",
    "__description__",
]
