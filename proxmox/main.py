import json
import requests
from typing import Any, Dict, List, Optional

# Plugin metadata
__version__ = "1.0.0"
__author__ = "OpenHome"
__description__ = "Proxmox VE API Integration for virtual machine and container management"

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
    "host": "your-proxmox-host.example.com",
    "port": 8006,
    "username": "root@pam",
    "api_token_id": "your_token_id",
    "api_token_secret": "your_token_secret",
    "verify_ssl": True,
    "unique_name": "proxmox_ability",
    "matching_hotwords": [
        "proxmox", "virtual machine", "vm", "container",
        "node", "cluster", "hypervisor", "lxc", "qemu"
    ]
}

_config: Dict[str, Any] = DEFAULT_CONFIG.copy()


# ---------------------------------------------------------------------------
# Proxmox VE API helpers
# ---------------------------------------------------------------------------

def _get_api_headers() -> Dict[str, str]:
    return {
        "Authorization": (
            f"PVEAPIToken={_config['username']}!"
            f"{_config['api_token_id']}={_config['api_token_secret']}"
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
            f"Cannot reach Proxmox host: {_config['host']}"
        )
    except requests.exceptions.Timeout:
        raise requests.RequestException("Request timed out")
    except requests.exceptions.RequestException as e:
        raise requests.RequestException(f"Proxmox API failed: {str(e)}")


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def list_nodes() -> Dict[str, Any]:
    """List all nodes in the Proxmox cluster."""
    nodes_data = _make_api_request("nodes")
    nodes: List[Dict[str, Any]] = []

    for node in nodes_data if isinstance(nodes_data, list) else []:
        if isinstance(node, dict):
            nodes.append({
                "name": node.get("node", ""),
                "status": node.get("status", "unknown"),
                "cpu_usage": round(node.get("cpu", 0) * 100, 2),
                "memory_used": node.get("mem", 0),
                "memory_total": node.get("maxmem", 0),
                "memory_percent": round(
                    node.get("mem", 0) / max(node.get("maxmem", 1), 1) * 100, 2
                ),
                "uptime_seconds": node.get("uptime", 0),
                "disk_used": node.get("disk", 0),
                "disk_total": node.get("maxdisk", 0),
            })

    return {"nodes": nodes, "total": len(nodes)}


def get_node_status(node: str) -> Dict[str, Any]:
    """Get detailed status for a specific node."""
    data = _make_api_request(f"nodes/{node}/status")

    if not isinstance(data, dict):
        return {"node": node, "status": "unknown"}

    cpu_info = data.get("cpuinfo", {})
    memory = data.get("memory", {})
    root_fs = data.get("rootfs", {})
    ksm = data.get("ksm", {})

    return {
        "node": node,
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
            "total_bytes": root_fs.get("total", 0),
            "used_bytes": root_fs.get("used", 0),
            "free_bytes": root_fs.get("avail", 0),
            "percent_used": round(
                root_fs.get("used", 0) / max(root_fs.get("total", 1), 1) * 100, 2
            ),
        },
        "ksm": {
            "shared": ksm.get("shared", 0),
        },
        "kernel_version": data.get("kversion", ""),
        "pve_version": data.get("pveversion", ""),
    }


# ---------------------------------------------------------------------------
# VM (QEMU) functions
# ---------------------------------------------------------------------------

def list_vms(node: str) -> Dict[str, Any]:
    """List all QEMU virtual machines on a node."""
    vms_data = _make_api_request(f"nodes/{node}/qemu")
    vms: List[Dict[str, Any]] = []

    for vm in vms_data if isinstance(vms_data, list) else []:
        if isinstance(vm, dict):
            vms.append({
                "vmid": vm.get("vmid", 0),
                "name": vm.get("name", ""),
                "status": vm.get("status", "unknown"),
                "cpu_usage": round(vm.get("cpu", 0) * 100, 2),
                "memory_used": vm.get("mem", 0),
                "memory_total": vm.get("maxmem", 0),
                "disk_used": vm.get("disk", 0),
                "disk_total": vm.get("maxdisk", 0),
                "uptime_seconds": vm.get("uptime", 0),
            })

    return {"node": node, "vms": vms, "total": len(vms)}


def get_vm_status(node: str, vmid: int) -> Dict[str, Any]:
    """Get detailed status for a specific VM."""
    data = _make_api_request(f"nodes/{node}/qemu/{vmid}/status/current")

    if not isinstance(data, dict):
        return {"node": node, "vmid": vmid, "status": "unknown"}

    return {
        "node": node,
        "vmid": vmid,
        "name": data.get("name", ""),
        "status": data.get("status", "unknown"),
        "cpu_usage": round(data.get("cpu", 0) * 100, 2),
        "cpus": data.get("cpus", 0),
        "memory_used": data.get("mem", 0),
        "memory_total": data.get("maxmem", 0),
        "disk_used": data.get("disk", 0),
        "disk_total": data.get("maxdisk", 0),
        "uptime_seconds": data.get("uptime", 0),
        "pid": data.get("pid", None),
        "qmp_status": data.get("qmpstatus", ""),
    }


def start_vm(node: str, vmid: int) -> Dict[str, Any]:
    """Start a VM."""
    data = _make_api_request(
        f"nodes/{node}/qemu/{vmid}/status/start", method="POST"
    )
    return {"node": node, "vmid": vmid, "action": "start", "task_id": data}


def stop_vm(node: str, vmid: int) -> Dict[str, Any]:
    """Stop a VM."""
    data = _make_api_request(
        f"nodes/{node}/qemu/{vmid}/status/stop", method="POST"
    )
    return {"node": node, "vmid": vmid, "action": "stop", "task_id": data}


def reboot_vm(node: str, vmid: int) -> Dict[str, Any]:
    """Reboot a VM (ACPI reboot)."""
    data = _make_api_request(
        f"nodes/{node}/qemu/{vmid}/status/reboot", method="POST"
    )
    return {"node": node, "vmid": vmid, "action": "reboot", "task_id": data}


def shutdown_vm(node: str, vmid: int) -> Dict[str, Any]:
    """Gracefully shut down a VM (ACPI shutdown)."""
    data = _make_api_request(
        f"nodes/{node}/qemu/{vmid}/status/shutdown", method="POST"
    )
    return {"node": node, "vmid": vmid, "action": "shutdown", "task_id": data}


# ---------------------------------------------------------------------------
# Container (LXC) functions
# ---------------------------------------------------------------------------

def list_containers(node: str) -> Dict[str, Any]:
    """List all LXC containers on a node."""
    ct_data = _make_api_request(f"nodes/{node}/lxc")
    containers: List[Dict[str, Any]] = []

    for ct in ct_data if isinstance(ct_data, list) else []:
        if isinstance(ct, dict):
            containers.append({
                "vmid": ct.get("vmid", 0),
                "name": ct.get("name", ""),
                "status": ct.get("status", "unknown"),
                "cpu_usage": round(ct.get("cpu", 0) * 100, 2),
                "memory_used": ct.get("mem", 0),
                "memory_total": ct.get("maxmem", 0),
                "disk_used": ct.get("disk", 0),
                "disk_total": ct.get("maxdisk", 0),
                "uptime_seconds": ct.get("uptime", 0),
            })

    return {"node": node, "containers": containers, "total": len(containers)}


def start_container(node: str, vmid: int) -> Dict[str, Any]:
    """Start an LXC container."""
    data = _make_api_request(
        f"nodes/{node}/lxc/{vmid}/status/start", method="POST"
    )
    return {"node": node, "vmid": vmid, "action": "start", "task_id": data}


def stop_container(node: str, vmid: int) -> Dict[str, Any]:
    """Stop an LXC container."""
    data = _make_api_request(
        f"nodes/{node}/lxc/{vmid}/status/stop", method="POST"
    )
    return {"node": node, "vmid": vmid, "action": "stop", "task_id": data}


def reboot_container(node: str, vmid: int) -> Dict[str, Any]:
    """Reboot an LXC container."""
    data = _make_api_request(
        f"nodes/{node}/lxc/{vmid}/status/reboot", method="POST"
    )
    return {"node": node, "vmid": vmid, "action": "reboot", "task_id": data}


# ---------------------------------------------------------------------------
# Storage functions
# ---------------------------------------------------------------------------

def list_storage(node: str) -> Dict[str, Any]:
    """List storage resources on a node."""
    st_data = _make_api_request(f"nodes/{node}/storage")
    storages: List[Dict[str, Any]] = []

    for st in st_data if isinstance(st_data, list) else []:
        if isinstance(st, dict):
            total = st.get("total", 0)
            used = st.get("used", 0)
            storages.append({
                "storage": st.get("storage", ""),
                "type": st.get("type", ""),
                "content": st.get("content", ""),
                "status": st.get("status", ""),
                "active": st.get("active", 0),
                "total_bytes": total,
                "used_bytes": used,
                "available_bytes": st.get("avail", 0),
                "percent_used": round(
                    used / max(total, 1) * 100, 2
                ),
            })

    return {"node": node, "storage": storages, "total": len(storages)}


# ---------------------------------------------------------------------------
# Cluster functions
# ---------------------------------------------------------------------------

def get_cluster_status() -> Dict[str, Any]:
    """Get the overall cluster status."""
    data = _make_api_request("cluster/status")
    entries: List[Dict[str, Any]] = []

    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict):
            entries.append({
                "name": item.get("name", ""),
                "type": item.get("type", ""),
                "online": item.get("online", 0),
                "nodeid": item.get("nodeid", None),
                "ip": item.get("ip", ""),
                "level": item.get("level", ""),
                "local": item.get("local", 0),
            })

    return {"cluster": entries, "total": len(entries)}


def list_cluster_resources(resource_type: str = "") -> Dict[str, Any]:
    """List cluster resources, optionally filtered by type (vm, storage, node)."""
    params: Dict[str, Any] = {}
    if resource_type:
        params["type"] = resource_type
    data = _make_api_request("cluster/resources", params=params)
    resources: List[Dict[str, Any]] = []

    for res in data if isinstance(data, list) else []:
        if isinstance(res, dict):
            resources.append({
                "id": res.get("id", ""),
                "type": res.get("type", ""),
                "node": res.get("node", ""),
                "name": res.get("name", ""),
                "status": res.get("status", ""),
                "cpu": res.get("cpu", 0),
                "maxcpu": res.get("maxcpu", 0),
                "mem": res.get("mem", 0),
                "maxmem": res.get("maxmem", 0),
                "disk": res.get("disk", 0),
                "maxdisk": res.get("maxdisk", 0),
                "uptime": res.get("uptime", 0),
            })

    return {"resources": resources, "total": len(resources)}


# ---------------------------------------------------------------------------
# Task functions
# ---------------------------------------------------------------------------

def list_tasks(node: str, limit: int = 20) -> Dict[str, Any]:
    """List recent tasks on a node."""
    data = _make_api_request(
        f"nodes/{node}/tasks", params={"limit": limit}
    )
    tasks: List[Dict[str, Any]] = []

    for task in data if isinstance(data, list) else []:
        if isinstance(task, dict):
            tasks.append({
                "upid": task.get("upid", ""),
                "type": task.get("type", ""),
                "status": task.get("status", ""),
                "user": task.get("user", ""),
                "starttime": task.get("starttime", 0),
                "endtime": task.get("endtime", 0),
                "node": task.get("node", ""),
            })

    return {"node": node, "tasks": tasks, "total": len(tasks)}


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
        "list_nodes": list_nodes,
        "nodes": list_nodes,
        "get_node_status": get_node_status,
        "node_status": get_node_status,
        "list_vms": list_vms,
        "vms": list_vms,
        "get_vm_status": get_vm_status,
        "vm_status": get_vm_status,
        "start_vm": start_vm,
        "stop_vm": stop_vm,
        "reboot_vm": reboot_vm,
        "shutdown_vm": shutdown_vm,
        "list_containers": list_containers,
        "containers": list_containers,
        "start_container": start_container,
        "stop_container": stop_container,
        "reboot_container": reboot_container,
        "list_storage": list_storage,
        "storage": list_storage,
        "get_cluster_status": get_cluster_status,
        "cluster": get_cluster_status,
        "list_cluster_resources": list_cluster_resources,
        "cluster_resources": list_cluster_resources,
        "list_tasks": list_tasks,
        "tasks": list_tasks,
    }

    func = cmd_map.get(command)
    if not func:
        raise ValueError(
            f"Unknown command '{command}'. "
            f"Valid: {', '.join(sorted(cmd_map.keys()))}"
        )

    # No-argument commands
    if func in (list_nodes, get_cluster_status):
        return func()

    # Node-only commands
    node = args.get("node", "")
    if not node and func not in (list_cluster_resources,):
        raise ValueError(f"{command} requires a 'node' argument")

    if func is list_cluster_resources:
        return func(args.get("type", ""))

    if func in (get_node_status,):
        return func(node)

    if func in (list_vms, list_containers, list_storage):
        return func(node)

    if func is list_tasks:
        return func(node, args.get("limit", 20))

    # VM/container commands requiring vmid
    vmid = args.get("vmid")
    if vmid is None:
        raise ValueError(f"{command} requires a 'vmid' argument")
    vmid = int(vmid)

    if func in (get_vm_status, start_vm, stop_vm, reboot_vm, shutdown_vm):
        return func(node, vmid)

    if func in (start_container, stop_container, reboot_container):
        return func(node, vmid)

    return func()


# ---------------------------------------------------------------------------
# OpenHome Capability (voice-interactive)
# ---------------------------------------------------------------------------

class ProxmoxCapability(MatchingCapability):
    worker: AgentWorker = None
    capability_worker: CapabilityWorker = None

    @classmethod
    def register_capability(cls) -> "ProxmoxCapability":
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
                "I can help manage your Proxmox environment. "
                "I can list nodes, check node status, manage VMs and containers, "
                "view storage, check cluster status, or list recent tasks. "
                "What would you like?"
            )
            user_input = await self.capability_worker.user_response()

            intent = self._classify_intent(user_input)
            action = intent.get("action", "unknown")
            node = intent.get("node", "")
            vmid_str = intent.get("vmid", "")

            if action == "list_nodes":
                data = list_nodes()
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize this Proxmox node list in 2-3 short sentences "
                    f"for a voice response: {json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "node_status":
                if not node:
                    node = await self.capability_worker.run_io_loop(
                        "Which node should I check?"
                    )
                data = get_node_status(node.strip())
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize this node status briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "list_vms":
                if not node:
                    node = await self.capability_worker.run_io_loop(
                        "Which node should I list VMs for?"
                    )
                data = list_vms(node.strip())
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize this VM list briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "list_containers":
                if not node:
                    node = await self.capability_worker.run_io_loop(
                        "Which node should I list containers for?"
                    )
                data = list_containers(node.strip())
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize this container list briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action in ("start_vm", "stop_vm", "reboot_vm", "shutdown_vm"):
                if not node:
                    node = await self.capability_worker.run_io_loop(
                        "Which node is the VM on?"
                    )
                if not vmid_str:
                    vmid_str = await self.capability_worker.run_io_loop(
                        "What is the VM ID?"
                    )
                vmid = int(vmid_str.strip())
                verb = action.replace("_vm", "")
                confirmed = await self.capability_worker.run_confirmation_loop(
                    f"Are you sure you want to {verb} VM {vmid} on {node.strip()}?"
                )
                if confirmed:
                    func_map = {
                        "start_vm": start_vm,
                        "stop_vm": stop_vm,
                        "reboot_vm": reboot_vm,
                        "shutdown_vm": shutdown_vm,
                    }
                    data = func_map[action](node.strip(), vmid)
                    await self.capability_worker.speak(
                        f"VM {vmid} {verb} command sent successfully."
                    )
                else:
                    await self.capability_worker.speak("Okay, no changes made.")

            elif action in (
                "start_container", "stop_container", "reboot_container"
            ):
                if not node:
                    node = await self.capability_worker.run_io_loop(
                        "Which node is the container on?"
                    )
                if not vmid_str:
                    vmid_str = await self.capability_worker.run_io_loop(
                        "What is the container ID?"
                    )
                vmid = int(vmid_str.strip())
                verb = action.replace("_container", "")
                confirmed = await self.capability_worker.run_confirmation_loop(
                    f"Are you sure you want to {verb} container {vmid} "
                    f"on {node.strip()}?"
                )
                if confirmed:
                    func_map = {
                        "start_container": start_container,
                        "stop_container": stop_container,
                        "reboot_container": reboot_container,
                    }
                    data = func_map[action](node.strip(), vmid)
                    await self.capability_worker.speak(
                        f"Container {vmid} {verb} command sent successfully."
                    )
                else:
                    await self.capability_worker.speak("Okay, no changes made.")

            elif action == "storage":
                if not node:
                    node = await self.capability_worker.run_io_loop(
                        "Which node should I check storage for?"
                    )
                data = list_storage(node.strip())
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize this storage info briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "cluster":
                data = get_cluster_status()
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize this cluster status briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "tasks":
                if not node:
                    node = await self.capability_worker.run_io_loop(
                        "Which node should I list tasks for?"
                    )
                data = list_tasks(node.strip())
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize these recent tasks briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            else:
                response = self.capability_worker.text_to_text_response(
                    f"The user said: '{user_input}'. I can manage Proxmox nodes, "
                    f"VMs, containers, storage, cluster, and tasks. "
                    f"Suggest the best action in one short sentence."
                )
                await self.capability_worker.speak(response)

        except Exception as e:
            await self.capability_worker.speak(
                "Sorry, something went wrong with the Proxmox request. "
                "Please check your server connection and try again."
            )

        self.capability_worker.resume_normal_flow()

    def _classify_intent(self, user_input: str) -> Dict[str, str]:
        """Use the LLM to classify user intent into an action."""
        prompt = (
            "Classify this user input for a Proxmox VE management assistant. "
            "Return ONLY valid JSON with no markdown fences.\n"
            '{"action": "list_nodes|node_status|list_vms|list_containers|'
            "start_vm|stop_vm|reboot_vm|shutdown_vm|"
            "start_container|stop_container|reboot_container|"
            'storage|cluster|tasks|unknown", '
            '"node": "node name if mentioned else empty string", '
            '"vmid": "vm or container id if mentioned else empty string"}\n\n'
            f"User: {user_input}"
        )
        raw = self.capability_worker.text_to_text_response(prompt)
        clean = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(clean)
        except (json.JSONDecodeError, TypeError):
            return {"action": "unknown", "node": "", "vmid": ""}


# ---------------------------------------------------------------------------
# Initialize helper
# ---------------------------------------------------------------------------

def initialize() -> Dict[str, Any]:
    return {
        "name": "Proxmox VE Ability",
        "version": __version__,
        "author": __author__,
        "description": __description__,
        "commands": [
            "list_nodes / nodes → all cluster nodes",
            "get_node_status / node_status → needs {'node': 'name'}",
            "list_vms / vms → needs {'node': 'name'}",
            "get_vm_status / vm_status → needs {'node': 'name', 'vmid': 100}",
            "start_vm → needs {'node': 'name', 'vmid': 100}",
            "stop_vm → needs {'node': 'name', 'vmid': 100}",
            "reboot_vm → needs {'node': 'name', 'vmid': 100}",
            "shutdown_vm → needs {'node': 'name', 'vmid': 100}",
            "list_containers / containers → needs {'node': 'name'}",
            "start_container → needs {'node': 'name', 'vmid': 100}",
            "stop_container → needs {'node': 'name', 'vmid': 100}",
            "reboot_container → needs {'node': 'name', 'vmid': 100}",
            "list_storage / storage → needs {'node': 'name'}",
            "get_cluster_status / cluster → cluster overview",
            "list_cluster_resources / cluster_resources → optional {'type': 'vm'}",
            "list_tasks / tasks → needs {'node': 'name'}",
        ],
    }
