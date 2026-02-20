"""
OpenHome Ability Plugin for Proxmox VE API Integration

This plugin provides comprehensive Proxmox Virtual Environment management
including nodes, VMs (QEMU), containers (LXC), storage, cluster status,
and task monitoring.

Requirements:
    - Python 3
    - requests library

Configuration:
    All configuration is managed via hardcoded defaults (overridden by OpenHome dashboard).
    Required fields: host, port, username, api_token_id, api_token_secret,
                     verify_ssl, unique_name, matching_hotwords
"""

from .main import (
    ProxmoxCapability,
    execute_command,
    initialize,
    list_nodes,
    get_node_status,
    list_vms,
    get_vm_status,
    start_vm,
    stop_vm,
    reboot_vm,
    shutdown_vm,
    list_containers,
    start_container,
    stop_container,
    reboot_container,
    list_storage,
    get_cluster_status,
    list_cluster_resources,
    list_tasks,
)

# Plugin metadata
__version__ = "1.0.0"
__author__ = "OpenHome"
__description__ = "Proxmox VE API Integration for virtual machine and container management"

__all__ = [
    "ProxmoxCapability",
    "execute_command",
    "initialize",
    "list_nodes",
    "get_node_status",
    "list_vms",
    "get_vm_status",
    "start_vm",
    "stop_vm",
    "reboot_vm",
    "shutdown_vm",
    "list_containers",
    "start_container",
    "stop_container",
    "reboot_container",
    "list_storage",
    "get_cluster_status",
    "list_cluster_resources",
    "list_tasks",
    "__version__",
    "__author__",
    "__description__",
]
