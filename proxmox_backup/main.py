import json
import requests
from typing import Any, Dict, List, Optional

# Plugin metadata
__version__ = "1.0.0"
__author__ = "OpenHome"
__description__ = "Proxmox Backup Server API Integration for backup management"

# Import OpenHome SDK — sandbox-safe, no os/sys/pathlib
try:
    from src.agent.capability import MatchingCapability
    from src.main import AgentWorker
    from src.agent.capability_worker import CapabilityWorker
except ImportError:
    # Fallback for dev/testing outside the OpenHome platform
    class MatchingCapability:
        def __init__(self, unique_name: str, matching_hotwords: list):
            self.unique_name = unique_name
            self.matching_hotwords = matching_hotwords

    class AgentWorker:
        pass

    class CapabilityWorker:
        def __init__(self, worker):
            pass

# Hardcoded fallback config — user should override via OpenHome dashboard/UI
DEFAULT_CONFIG = {
    "host": "your-pbs-host.example.com",
    "port": 8007,
    "username": "root@pam",
    "api_token_id": "your_token_id",
    "api_token_secret": "your_token_secret",
    "verify_ssl": True,
    "unique_name": "proxmox_backup_ability",
    "matching_hotwords": [
        "proxmox backup", "backup server", "pbs", "datastore",
        "backup", "restore", "snapshot", "backup job"
    ]
}

_config: Dict[str, Any] = DEFAULT_CONFIG.copy()


# ---------------------------------------------------------------------------
# PBS API helpers
# ---------------------------------------------------------------------------

def _get_api_headers() -> Dict[str, str]:
    return {
        "Authorization": (
            f"PBSAPIToken={_config['username']}!"
            f"{_config['api_token_id']}:{_config['api_token_secret']}"
        ),
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    return f"https://{_config['host']}:{_config['port']}/api2/json"


def _make_api_request(
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = f"{_base_url()}/{endpoint}"

    try:
        response = requests.request(
            method=method,
            url=url,
            params=params,
            json=data,
            headers=_get_api_headers(),
            verify=_config["verify_ssl"],
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        return result.get("data", result)

    except requests.exceptions.SSLError as e:
        raise requests.RequestException(
            f"SSL Error: {str(e)}. Check verify_ssl setting."
        )
    except requests.exceptions.ConnectionError:
        raise requests.RequestException(
            f"Cannot reach PBS host: {_config['host']}"
        )
    except requests.exceptions.Timeout:
        raise requests.RequestException("Request timed out")
    except requests.exceptions.RequestException as e:
        raise requests.RequestException(f"PBS API failed: {str(e)}")


# ---------------------------------------------------------------------------
# Node / system functions
# ---------------------------------------------------------------------------

def get_node_status() -> Dict[str, Any]:
    """Get the PBS node status including CPU, memory, and disk."""
    data = _make_api_request("nodes/localhost/status")

    if not isinstance(data, dict):
        return {"status": "unknown"}

    cpu_info = data.get("cpuinfo", {})
    memory = data.get("memory", {})
    root = data.get("root", {})
    info = data.get("info", {})

    return {
        "uptime_seconds": data.get("uptime", 0),
        "cpu": {
            "model": cpu_info.get("model", ""),
            "cores": cpu_info.get("cores", 0),
            "sockets": cpu_info.get("sockets", 0),
            "usage_percent": round(data.get("cpu", 0) * 100, 2),
            "load_average": data.get("loadavg", []),
        },
        "memory": {
            "total_bytes": memory.get("total", 0),
            "used_bytes": memory.get("used", 0),
            "free_bytes": memory.get("free", 0),
            "percent_used": round(
                memory.get("used", 0) / max(memory.get("total", 1), 1) * 100, 2
            ),
        },
        "disk": {
            "total_bytes": root.get("total", 0),
            "used_bytes": root.get("used", 0),
            "available_bytes": root.get("avail", 0),
            "percent_used": round(
                root.get("used", 0) / max(root.get("total", 1), 1) * 100, 2
            ),
        },
        "version": info.get("version", ""),
        "kernel_version": data.get("kversion", ""),
    }


# ---------------------------------------------------------------------------
# Datastore functions
# ---------------------------------------------------------------------------

def list_datastores() -> Dict[str, Any]:
    """List all datastores on the PBS server."""
    ds_data = _make_api_request("admin/datastore")
    datastores: List[Dict[str, Any]] = []

    for ds in ds_data if isinstance(ds_data, list) else []:
        if isinstance(ds, dict):
            datastores.append({
                "name": ds.get("name", ""),
                "path": ds.get("path", ""),
                "comment": ds.get("comment", ""),
            })

    return {"datastores": datastores, "total": len(datastores)}


def get_datastore_status(datastore: str) -> Dict[str, Any]:
    """Get status and usage for a specific datastore."""
    data = _make_api_request(f"admin/datastore/{datastore}")

    if not isinstance(data, dict):
        data = {}

    usage = _make_api_request(f"status/datastore-usage")
    ds_usage = {}
    for item in usage if isinstance(usage, list) else []:
        if isinstance(item, dict) and item.get("store") == datastore:
            ds_usage = item
            break

    total = ds_usage.get("total", 0)
    used = ds_usage.get("used", 0)
    avail = ds_usage.get("avail", 0)

    return {
        "datastore": datastore,
        "path": data.get("path", ""),
        "comment": data.get("comment", ""),
        "total_bytes": total,
        "used_bytes": used,
        "available_bytes": avail,
        "percent_used": round(used / max(total, 1) * 100, 2),
        "gc_schedule": data.get("gc-schedule", ""),
        "prune_schedule": data.get("prune-schedule", ""),
    }


def list_datastore_snapshots(
    datastore: str, backup_type: str = "", backup_id: str = ""
) -> Dict[str, Any]:
    """List snapshots (backup groups) in a datastore."""
    params: Dict[str, Any] = {}
    if backup_type:
        params["backup-type"] = backup_type
    if backup_id:
        params["backup-id"] = backup_id

    data = _make_api_request(
        f"admin/datastore/{datastore}/snapshots", params=params
    )
    snapshots: List[Dict[str, Any]] = []

    for snap in data if isinstance(data, list) else []:
        if isinstance(snap, dict):
            snapshots.append({
                "backup_type": snap.get("backup-type", ""),
                "backup_id": snap.get("backup-id", ""),
                "backup_time": snap.get("backup-time", 0),
                "size": snap.get("size", 0),
                "owner": snap.get("owner", ""),
                "verification": snap.get("verification", {}),
                "protected": snap.get("protected", False),
            })

    return {
        "datastore": datastore,
        "snapshots": snapshots,
        "total": len(snapshots),
    }


def list_backup_groups(datastore: str) -> Dict[str, Any]:
    """List backup groups in a datastore."""
    data = _make_api_request(f"admin/datastore/{datastore}/groups")
    groups: List[Dict[str, Any]] = []

    for grp in data if isinstance(data, list) else []:
        if isinstance(grp, dict):
            groups.append({
                "backup_type": grp.get("backup-type", ""),
                "backup_id": grp.get("backup-id", ""),
                "last_backup": grp.get("last-backup", 0),
                "backup_count": grp.get("backup-count", 0),
                "owner": grp.get("owner", ""),
            })

    return {
        "datastore": datastore,
        "groups": groups,
        "total": len(groups),
    }


# ---------------------------------------------------------------------------
# Sync job functions
# ---------------------------------------------------------------------------

def list_sync_jobs() -> Dict[str, Any]:
    """List all sync jobs."""
    data = _make_api_request("admin/sync")
    jobs: List[Dict[str, Any]] = []

    for job in data if isinstance(data, list) else []:
        if isinstance(job, dict):
            jobs.append({
                "id": job.get("id", ""),
                "store": job.get("store", ""),
                "remote": job.get("remote", ""),
                "remote_store": job.get("remote-store", ""),
                "schedule": job.get("schedule", ""),
                "comment": job.get("comment", ""),
                "remove_vanished": job.get("remove-vanished", False),
            })

    return {"sync_jobs": jobs, "total": len(jobs)}


def run_sync_job(job_id: str) -> Dict[str, Any]:
    """Trigger a sync job to run now."""
    data = _make_api_request(f"admin/sync/{job_id}/run", method="POST")
    return {"job_id": job_id, "action": "run", "task_id": data}


# ---------------------------------------------------------------------------
# Verify job functions
# ---------------------------------------------------------------------------

def list_verify_jobs() -> Dict[str, Any]:
    """List all verify jobs."""
    data = _make_api_request("admin/verify")
    jobs: List[Dict[str, Any]] = []

    for job in data if isinstance(data, list) else []:
        if isinstance(job, dict):
            jobs.append({
                "id": job.get("id", ""),
                "store": job.get("store", ""),
                "schedule": job.get("schedule", ""),
                "comment": job.get("comment", ""),
                "ignore_verified": job.get("ignore-verified", False),
                "outdated_after": job.get("outdated-after", ""),
            })

    return {"verify_jobs": jobs, "total": len(jobs)}


def run_verify_job(job_id: str) -> Dict[str, Any]:
    """Trigger a verification job to run now."""
    data = _make_api_request(f"admin/verify/{job_id}/run", method="POST")
    return {"job_id": job_id, "action": "run", "task_id": data}


# ---------------------------------------------------------------------------
# Garbage collection
# ---------------------------------------------------------------------------

def run_garbage_collection(datastore: str) -> Dict[str, Any]:
    """Trigger garbage collection on a datastore."""
    data = _make_api_request(
        f"admin/datastore/{datastore}/gc", method="POST"
    )
    return {"datastore": datastore, "action": "gc", "task_id": data}


# ---------------------------------------------------------------------------
# Prune functions
# ---------------------------------------------------------------------------

def run_prune(
    datastore: str,
    backup_type: str,
    backup_id: str,
    keep_last: int = 0,
    keep_daily: int = 0,
    keep_weekly: int = 0,
    keep_monthly: int = 0,
    keep_yearly: int = 0,
) -> Dict[str, Any]:
    """Run a prune operation on a backup group in a datastore."""
    prune_data: Dict[str, Any] = {
        "backup-type": backup_type,
        "backup-id": backup_id,
    }
    if keep_last > 0:
        prune_data["keep-last"] = keep_last
    if keep_daily > 0:
        prune_data["keep-daily"] = keep_daily
    if keep_weekly > 0:
        prune_data["keep-weekly"] = keep_weekly
    if keep_monthly > 0:
        prune_data["keep-monthly"] = keep_monthly
    if keep_yearly > 0:
        prune_data["keep-yearly"] = keep_yearly

    data = _make_api_request(
        f"admin/datastore/{datastore}/prune",
        method="POST",
        data=prune_data,
    )
    return {"datastore": datastore, "action": "prune", "result": data}


# ---------------------------------------------------------------------------
# Task functions
# ---------------------------------------------------------------------------

def list_tasks(limit: int = 20) -> Dict[str, Any]:
    """List recent tasks on the PBS server."""
    data = _make_api_request("nodes/localhost/tasks", params={"limit": limit})
    tasks: List[Dict[str, Any]] = []

    for task in data if isinstance(data, list) else []:
        if isinstance(task, dict):
            tasks.append({
                "upid": task.get("upid", ""),
                "worker_type": task.get("worker_type", ""),
                "worker_id": task.get("worker_id", ""),
                "status": task.get("status", ""),
                "user": task.get("user", ""),
                "starttime": task.get("starttime", 0),
                "endtime": task.get("endtime", 0),
            })

    return {"tasks": tasks, "total": len(tasks)}


def get_task_status(upid: str) -> Dict[str, Any]:
    """Get the status of a specific task."""
    data = _make_api_request(f"nodes/localhost/tasks/{upid}/status")

    if not isinstance(data, dict):
        return {"upid": upid, "status": "unknown"}

    return {
        "upid": upid,
        "status": data.get("status", "unknown"),
        "exitstatus": data.get("exitstatus", ""),
        "type": data.get("type", ""),
        "starttime": data.get("starttime", 0),
        "endtime": data.get("endtime", 0),
    }


# ---------------------------------------------------------------------------
# Command router
# ---------------------------------------------------------------------------

def execute_command(
    command: str, args: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Route a command string to the appropriate function."""
    command = command.lower().strip()
    args = args or {}

    cmd_map: Dict[str, Any] = {
        "get_node_status": get_node_status,
        "node_status": get_node_status,
        "list_datastores": list_datastores,
        "datastores": list_datastores,
        "get_datastore_status": get_datastore_status,
        "datastore_status": get_datastore_status,
        "list_snapshots": list_datastore_snapshots,
        "snapshots": list_datastore_snapshots,
        "list_backup_groups": list_backup_groups,
        "backup_groups": list_backup_groups,
        "list_sync_jobs": list_sync_jobs,
        "sync_jobs": list_sync_jobs,
        "run_sync_job": run_sync_job,
        "list_verify_jobs": list_verify_jobs,
        "verify_jobs": list_verify_jobs,
        "run_verify_job": run_verify_job,
        "run_gc": run_garbage_collection,
        "gc": run_garbage_collection,
        "run_prune": run_prune,
        "prune": run_prune,
        "list_tasks": list_tasks,
        "tasks": list_tasks,
        "get_task_status": get_task_status,
        "task_status": get_task_status,
    }

    func = cmd_map.get(command)
    if not func:
        raise ValueError(
            f"Unknown command '{command}'. "
            f"Valid: {', '.join(sorted(cmd_map.keys()))}"
        )

    # No-argument commands
    if func in (
        get_node_status, list_datastores, list_sync_jobs, list_verify_jobs
    ):
        return func()

    if func is list_tasks:
        return func(args.get("limit", 20))

    # Datastore-required commands
    datastore = args.get("datastore", "")
    if func in (
        get_datastore_status,
        list_datastore_snapshots,
        list_backup_groups,
        run_garbage_collection,
    ):
        if not datastore:
            raise ValueError(f"{command} requires a 'datastore' argument")
        if func is list_datastore_snapshots:
            return func(
                datastore,
                args.get("backup_type", ""),
                args.get("backup_id", ""),
            )
        if func is list_backup_groups:
            return func(datastore)
        if func is run_garbage_collection:
            return func(datastore)
        return func(datastore)

    # run_prune requires datastore, backup_type, backup_id
    if func is run_prune:
        if not datastore:
            raise ValueError("prune requires a 'datastore' argument")
        backup_type = args.get("backup_type", "")
        backup_id = args.get("backup_id", "")
        if not backup_type or not backup_id:
            raise ValueError(
                "prune requires 'backup_type' and 'backup_id' arguments"
            )
        return func(
            datastore,
            backup_type,
            backup_id,
            args.get("keep_last", 0),
            args.get("keep_daily", 0),
            args.get("keep_weekly", 0),
            args.get("keep_monthly", 0),
            args.get("keep_yearly", 0),
        )

    # Job ID commands
    job_id = args.get("job_id", "")
    if func in (run_sync_job, run_verify_job):
        if not job_id:
            raise ValueError(f"{command} requires a 'job_id' argument")
        return func(job_id)

    # Task status
    if func is get_task_status:
        upid = args.get("upid", "")
        if not upid:
            raise ValueError("task_status requires a 'upid' argument")
        return func(upid)

    return func()


# ---------------------------------------------------------------------------
# OpenHome Capability (voice-interactive)
# ---------------------------------------------------------------------------

class ProxmoxBackupCapability(MatchingCapability):
    worker: AgentWorker = None
    capability_worker: CapabilityWorker = None

    @classmethod
    def register_capability(cls) -> "ProxmoxBackupCapability":
        return cls(
            unique_name=DEFAULT_CONFIG["unique_name"],
            matching_hotwords=DEFAULT_CONFIG["matching_hotwords"],
        )

    def call(self, worker: AgentWorker):
        self.worker = worker
        self.capability_worker = CapabilityWorker(self.worker)
        self.worker.session_tasks.create(self.run())

    async def run(self):
        try:
            await self.capability_worker.speak(
                "I can help manage your Proxmox Backup Server. "
                "I can check node status, list datastores and their usage, "
                "view backup snapshots and groups, manage sync and verify jobs, "
                "run garbage collection, or list recent tasks. "
                "What would you like?"
            )
            user_input = await self.capability_worker.user_response()

            intent = self._classify_intent(user_input)
            action = intent.get("action", "unknown")
            datastore = intent.get("datastore", "")

            if action == "node_status":
                data = get_node_status()
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize this PBS node status in 2-3 short sentences "
                    f"for a voice response: {json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "datastores":
                data = list_datastores()
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize this datastore list briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "datastore_status":
                if not datastore:
                    datastore = await self.capability_worker.run_io_loop(
                        "Which datastore should I check?"
                    )
                data = get_datastore_status(datastore.strip())
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize this datastore status briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "snapshots":
                if not datastore:
                    datastore = await self.capability_worker.run_io_loop(
                        "Which datastore should I list snapshots for?"
                    )
                data = list_datastore_snapshots(datastore.strip())
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize these backup snapshots briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "backup_groups":
                if not datastore:
                    datastore = await self.capability_worker.run_io_loop(
                        "Which datastore should I list backup groups for?"
                    )
                data = list_backup_groups(datastore.strip())
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize these backup groups briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "sync_jobs":
                data = list_sync_jobs()
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize these sync jobs briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "run_sync":
                job_id = intent.get("job_id", "")
                if not job_id:
                    job_id = await self.capability_worker.run_io_loop(
                        "Which sync job ID should I run?"
                    )
                confirmed = await self.capability_worker.run_confirmation_loop(
                    f"Are you sure you want to run sync job {job_id.strip()}?"
                )
                if confirmed:
                    data = run_sync_job(job_id.strip())
                    await self.capability_worker.speak(
                        f"Sync job {job_id.strip()} has been started."
                    )
                else:
                    await self.capability_worker.speak("Okay, no changes made.")

            elif action == "verify_jobs":
                data = list_verify_jobs()
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize these verify jobs briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "run_verify":
                job_id = intent.get("job_id", "")
                if not job_id:
                    job_id = await self.capability_worker.run_io_loop(
                        "Which verify job ID should I run?"
                    )
                confirmed = await self.capability_worker.run_confirmation_loop(
                    f"Are you sure you want to run verify job {job_id.strip()}?"
                )
                if confirmed:
                    data = run_verify_job(job_id.strip())
                    await self.capability_worker.speak(
                        f"Verify job {job_id.strip()} has been started."
                    )
                else:
                    await self.capability_worker.speak("Okay, no changes made.")

            elif action == "gc":
                if not datastore:
                    datastore = await self.capability_worker.run_io_loop(
                        "Which datastore should I run garbage collection on?"
                    )
                confirmed = await self.capability_worker.run_confirmation_loop(
                    f"Run garbage collection on datastore {datastore.strip()}?"
                )
                if confirmed:
                    data = run_garbage_collection(datastore.strip())
                    await self.capability_worker.speak(
                        f"Garbage collection started on {datastore.strip()}."
                    )
                else:
                    await self.capability_worker.speak("Okay, no changes made.")

            elif action == "tasks":
                data = list_tasks()
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize these recent tasks briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            else:
                response = self.capability_worker.text_to_text_response(
                    f"The user said: '{user_input}'. I can manage Proxmox "
                    f"Backup Server datastores, snapshots, backup groups, "
                    f"sync/verify jobs, garbage collection, and tasks. "
                    f"Suggest the best action in one short sentence."
                )
                await self.capability_worker.speak(response)

        except Exception as e:
            await self.capability_worker.speak(
                "Sorry, something went wrong with the Proxmox Backup Server "
                "request. Please check your connection and try again."
            )

        self.capability_worker.resume_normal_flow()

    def _classify_intent(self, user_input: str) -> Dict[str, str]:
        """Use the LLM to classify user intent into an action."""
        prompt = (
            "Classify this user input for a Proxmox Backup Server assistant. "
            "Return ONLY valid JSON with no markdown fences.\n"
            '{"action": "node_status|datastores|datastore_status|snapshots|'
            "backup_groups|sync_jobs|run_sync|verify_jobs|run_verify|"
            'gc|tasks|unknown", '
            '"datastore": "datastore name if mentioned else empty string", '
            '"job_id": "job id if mentioned else empty string"}\n\n'
            f"User: {user_input}"
        )
        raw = self.capability_worker.text_to_text_response(prompt)
        clean = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(clean)
        except (json.JSONDecodeError, TypeError):
            return {"action": "unknown", "datastore": "", "job_id": ""}


# ---------------------------------------------------------------------------
# Initialize helper
# ---------------------------------------------------------------------------

def initialize() -> Dict[str, Any]:
    return {
        "name": "Proxmox Backup Server Ability",
        "version": __version__,
        "author": __author__,
        "description": __description__,
        "commands": [
            "get_node_status / node_status → PBS server status",
            "list_datastores / datastores → all datastores",
            "get_datastore_status / datastore_status → needs {'datastore': 'name'}",
            "list_snapshots / snapshots → needs {'datastore': 'name'}",
            "list_backup_groups / backup_groups → needs {'datastore': 'name'}",
            "list_sync_jobs / sync_jobs → all sync jobs",
            "run_sync_job → needs {'job_id': 'id'}",
            "list_verify_jobs / verify_jobs → all verify jobs",
            "run_verify_job → needs {'job_id': 'id'}",
            "run_gc / gc → needs {'datastore': 'name'}",
            "run_prune / prune → needs {'datastore', 'backup_type', 'backup_id'}",
            "list_tasks / tasks → recent tasks",
            "get_task_status / task_status → needs {'upid': 'task_upid'}",
        ],
    }
