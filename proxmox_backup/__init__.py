"""
OpenHome Ability Plugin for Proxmox Backup Server (PBS) API Integration

This plugin provides comprehensive Proxmox Backup Server management
including node status, datastores, snapshots, backup groups,
sync jobs, verify jobs, garbage collection, and task monitoring.

Requirements:
    - Python 3
    - requests library

Configuration:
    All configuration is managed via hardcoded defaults (overridden by OpenHome dashboard).
    Required fields: host, port, username, api_token_id, api_token_secret,
                     verify_ssl, unique_name, matching_hotwords
"""

from .main import (
    ProxmoxBackupCapability,
    execute_command,
    initialize,
    get_node_status,
    list_datastores,
    get_datastore_status,
    list_datastore_snapshots,
    list_backup_groups,
    list_sync_jobs,
    run_sync_job,
    list_verify_jobs,
    run_verify_job,
    run_garbage_collection,
    run_prune,
    list_tasks,
    get_task_status,
)

# Plugin metadata
__version__ = "1.0.0"
__author__ = "OpenHome"
__description__ = "Proxmox Backup Server API Integration for backup management"

__all__ = [
    "ProxmoxBackupCapability",
    "execute_command",
    "initialize",
    "get_node_status",
    "list_datastores",
    "get_datastore_status",
    "list_datastore_snapshots",
    "list_backup_groups",
    "list_sync_jobs",
    "run_sync_job",
    "list_verify_jobs",
    "run_verify_job",
    "run_garbage_collection",
    "run_prune",
    "list_tasks",
    "get_task_status",
    "__version__",
    "__author__",
    "__description__",
]
