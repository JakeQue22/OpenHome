import json
import requests
from typing import Any, Dict, List, Optional

# Plugin metadata
__version__ = "1.0.0"
__author__ = "OpenHome"
__description__ = "WHM/cPanel API Integration for hosting management"

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
# (sandbox prevents file/env loading; this is the only safe way)
DEFAULT_CONFIG = {
    "host": "your-server.example.com",
    "username": "root",
    "api_token": "YOUR_API_TOKEN_HERE",
    "verify_ssl": True,
    "unique_name": "whm_ability",
    "matching_hotwords": [
        "whm", "hosting", "cpanel", "server", "accounts",
        "domains", "bandwidth", "ssl", "disk", "suspend"
    ]
}

# Global config — in real deployment, dashboard overrides these defaults
_config: Dict[str, Any] = DEFAULT_CONFIG.copy()


# ---------------------------------------------------------------------------
# WHM API helpers
# ---------------------------------------------------------------------------

def _get_api_headers() -> Dict[str, str]:
    return {
        "Authorization": f"whm {_config['username']}:{_config['api_token']}",
        "Content-Type": "application/json"
    }


def _make_api_request(
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    method: str = "GET"
) -> Dict[str, Any]:
    base_url = f"https://{_config['host']}:2087/json-api"
    url = f"{base_url}/{endpoint}"

    try:
        response = requests.request(
            method=method,
            url=url,
            params=params,
            headers=_get_api_headers(),
            verify=_config["verify_ssl"],
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and data.get("status") == 0:
            raise ValueError(
                f"WHM API Error: {data.get('statusmsg', 'Unknown')}"
            )

        if "result" in data and isinstance(data["result"], list):
            for item in data["result"]:
                if isinstance(item, dict) and item.get("status") == 0:
                    raise ValueError(
                        f"WHM API Error: {item.get('statusmsg', 'Unknown')}"
                    )

        return data

    except requests.exceptions.SSLError as e:
        raise requests.RequestException(
            f"SSL Error: {str(e)}. Check verify_ssl setting."
        )
    except requests.exceptions.ConnectionError:
        raise requests.RequestException(
            f"Cannot reach host: {_config['host']}"
        )
    except requests.exceptions.Timeout:
        raise requests.RequestException("Request timed out")
    except requests.exceptions.RequestException as e:
        raise requests.RequestException(f"API failed: {str(e)}")


# ---------------------------------------------------------------------------
# WHM API functions
# ---------------------------------------------------------------------------

def get_server_resources() -> Dict[str, Any]:
    """Get server CPU load, memory, and disk usage."""
    load_data = _make_api_request("loadavg")
    disk_data = _make_api_request("getdiskinfo")

    avg = load_data.get("avg", [0, 0, 0])
    disk = disk_data.get("partition", [{}])
    root_part = {}
    for part in disk if isinstance(disk, list) else []:
        if isinstance(part, dict) and part.get("mount", "") == "/":
            root_part = part
            break

    result = {
        "cpu": {
            "load_1min": avg[0] if len(avg) > 0 else 0,
            "load_5min": avg[1] if len(avg) > 1 else 0,
            "load_15min": avg[2] if len(avg) > 2 else 0,
            "status": "ok" if (avg[0] if len(avg) > 0 else 0) < 4 else "high"
        },
        "disk": {
            "total": root_part.get("total", "N/A"),
            "used": root_part.get("used", "N/A"),
            "available": root_part.get("available", "N/A"),
            "percent_used": root_part.get("percentage", "N/A"),
        }
    }
    return result


def list_accounts() -> Dict[str, Any]:
    """List all cPanel accounts on the server."""
    data = _make_api_request("listaccts", params={"api.version": "1"})
    accounts: List[Dict[str, Any]] = []

    for acct in data.get("acct", []):
        if isinstance(acct, dict):
            accounts.append({
                "user": acct.get("user", ""),
                "domain": acct.get("domain", ""),
                "email": acct.get("email", ""),
                "plan": acct.get("plan", ""),
                "suspended": acct.get("suspended", False),
                "disk_used": acct.get("diskused", "0M"),
                "disk_limit": acct.get("disklimit", "unlimited"),
            })

    return {"accounts": accounts, "total": len(accounts)}


def list_domains() -> Dict[str, Any]:
    """List all domains hosted on the server."""
    data = _make_api_request("listdomains")
    domains: List[Dict[str, Any]] = []

    for info in data.get("domain", []):
        if isinstance(info, dict):
            domains.append({
                "domain": info.get("domain", ""),
                "document_root": info.get("docroot", ""),
                "user": info.get("user", ""),
                "status": info.get("status", "active")
            })

    return {"domains": domains, "total": len(domains)}


def get_disk_usage(account: str) -> Dict[str, Any]:
    """Get disk usage for a specific cPanel account."""
    data = _make_api_request("getdiskusage", params={"user": account})
    result = data.get("result", [{}])[0] if data.get("result") else {}

    usage = result.get("diskquota", 0)
    limit = result.get("disklimit", 1)
    pct = round(usage / limit * 100, 2) if limit > 0 else 0

    return {
        "account": account,
        "disk_usage_bytes": usage,
        "disk_usage_mb": round(usage / (1024**2), 2),
        "disk_limit_bytes": limit,
        "disk_limit_mb": round(limit / (1024**2), 2),
        "percent_used": pct,
        "status": "ok" if pct < 80 else "warning" if pct < 90 else "critical"
    }


def suspend_account(account: str, reason: str = "") -> Dict[str, Any]:
    """Suspend a cPanel account."""
    params: Dict[str, Any] = {"user": account}
    if reason:
        params["reason"] = reason
    data = _make_api_request("suspendacct", params=params)
    return {
        "account": account,
        "action": "suspended",
        "result": data.get("result", [{}])[0] if data.get("result") else data,
    }


def unsuspend_account(account: str) -> Dict[str, Any]:
    """Unsuspend a cPanel account."""
    data = _make_api_request("unsuspendacct", params={"user": account})
    return {
        "account": account,
        "action": "unsuspended",
        "result": data.get("result", [{}])[0] if data.get("result") else data,
    }


def get_bandwidth(account: str = "") -> Dict[str, Any]:
    """Get bandwidth usage. If account provided, get per-account; else server-wide."""
    if account:
        data = _make_api_request("showbw", params={"searchtype": "user", "search": account})
    else:
        data = _make_api_request("showbw")

    bandwidth_entries: List[Dict[str, Any]] = []
    for entry in data.get("bandwidth", []):
        if isinstance(entry, dict):
            bandwidth_entries.append({
                "account": entry.get("acct", ""),
                "domain": entry.get("domain", ""),
                "bytes_used": entry.get("totalbytes", 0),
                "limit": entry.get("limit", "unlimited"),
            })

    return {"bandwidth": bandwidth_entries, "total_entries": len(bandwidth_entries)}


def get_hostname() -> Dict[str, Any]:
    """Get the server hostname."""
    data = _make_api_request("gethostname")
    return {"hostname": data.get("hostname", "unknown")}


def restart_service(service: str) -> Dict[str, Any]:
    """Restart a server service (e.g. httpd, exim, mysql, named, ftpd)."""
    allowed = {"httpd", "exim", "mysql", "named", "ftpd", "sshd", "cpsrvd"}
    if service not in allowed:
        raise ValueError(
            f"Service '{service}' not allowed. Valid: {', '.join(sorted(allowed))}"
        )
    data = _make_api_request("restartservice", params={"service": service})
    return {
        "service": service,
        "action": "restart",
        "result": data,
    }


# ---------------------------------------------------------------------------
# Command router
# ---------------------------------------------------------------------------

def execute_command(
    command: str, args: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Route a command string to the appropriate function."""
    command = command.lower().strip()
    cmd_map: Dict[str, Any] = {
        "get_server_resources": get_server_resources,
        "resources": get_server_resources,
        "list_accounts": list_accounts,
        "accounts": list_accounts,
        "list_domains": list_domains,
        "domains": list_domains,
        "get_disk_usage": get_disk_usage,
        "disk": get_disk_usage,
        "suspend_account": suspend_account,
        "suspend": suspend_account,
        "unsuspend_account": unsuspend_account,
        "unsuspend": unsuspend_account,
        "get_bandwidth": get_bandwidth,
        "bandwidth": get_bandwidth,
        "get_hostname": get_hostname,
        "hostname": get_hostname,
        "restart_service": restart_service,
        "restart": restart_service,
    }

    func = cmd_map.get(command)
    if not func:
        raise ValueError(
            f"Unknown command '{command}'. "
            f"Valid: {', '.join(sorted(cmd_map.keys()))}"
        )

    # Functions requiring an 'account' argument
    if func in (get_disk_usage, suspend_account, unsuspend_account):
        if (
            not args
            or "account" not in args
            or not isinstance(args["account"], str)
            or not args["account"].strip()
        ):
            raise ValueError(f"{command} requires a non-empty 'account' string")
        if func is suspend_account:
            return func(args["account"], args.get("reason", ""))
        return func(args["account"])

    # get_bandwidth optionally takes an account
    if func is get_bandwidth:
        return func(args.get("account", "") if args else "")

    # restart_service requires a 'service' argument
    if func is restart_service:
        if (
            not args
            or "service" not in args
            or not isinstance(args["service"], str)
            or not args["service"].strip()
        ):
            raise ValueError("restart_service requires a non-empty 'service' string")
        return func(args["service"])

    return func()


# ---------------------------------------------------------------------------
# OpenHome Capability (voice-interactive)
# ---------------------------------------------------------------------------

class WhmCpanelControlCapability(MatchingCapability):
    worker: AgentWorker = None
    capability_worker: CapabilityWorker = None

    @classmethod
    def register_capability(cls) -> "WhmCpanelControlCapability":
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
                "I can help with your WHM server. "
                "I can check resources, list accounts or domains, "
                "check disk or bandwidth usage, suspend or unsuspend accounts, "
                "get the hostname, or restart a service. What would you like?"
            )
            user_input = await self.capability_worker.user_response()

            intent = self._classify_intent(user_input)
            action = intent.get("action", "unknown")

            if action == "resources":
                data = get_server_resources()
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize this server resource data in 2-3 short sentences "
                    f"for a voice response: {json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "accounts":
                data = list_accounts()
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize this account list briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "domains":
                data = list_domains()
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize this domain list briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "disk":
                account = intent.get("account", "")
                if not account:
                    account = await self.capability_worker.run_io_loop(
                        "Which account should I check disk usage for?"
                    )
                data = get_disk_usage(account.strip())
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize this disk usage briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "bandwidth":
                data = get_bandwidth(intent.get("account", ""))
                summary = self.capability_worker.text_to_text_response(
                    f"Summarize this bandwidth data briefly for voice: "
                    f"{json.dumps(data)}"
                )
                await self.capability_worker.speak(summary)

            elif action == "suspend":
                account = intent.get("account", "")
                if not account:
                    account = await self.capability_worker.run_io_loop(
                        "Which account should I suspend?"
                    )
                confirmed = await self.capability_worker.run_confirmation_loop(
                    f"Are you sure you want to suspend {account.strip()}?"
                )
                if confirmed:
                    data = suspend_account(account.strip())
                    await self.capability_worker.speak(
                        f"Account {account.strip()} has been suspended."
                    )
                else:
                    await self.capability_worker.speak("Okay, no changes made.")

            elif action == "unsuspend":
                account = intent.get("account", "")
                if not account:
                    account = await self.capability_worker.run_io_loop(
                        "Which account should I unsuspend?"
                    )
                data = unsuspend_account(account.strip())
                await self.capability_worker.speak(
                    f"Account {account.strip()} has been unsuspended."
                )

            elif action == "hostname":
                data = get_hostname()
                await self.capability_worker.speak(
                    f"The server hostname is {data['hostname']}."
                )

            elif action == "restart":
                service = intent.get("service", "")
                if not service:
                    service = await self.capability_worker.run_io_loop(
                        "Which service? Options: httpd, exim, mysql, named, ftpd, sshd, cpsrvd."
                    )
                confirmed = await self.capability_worker.run_confirmation_loop(
                    f"Are you sure you want to restart {service.strip()}?"
                )
                if confirmed:
                    data = restart_service(service.strip())
                    await self.capability_worker.speak(
                        f"The {service.strip()} service has been restarted."
                    )
                else:
                    await self.capability_worker.speak("Okay, no changes made.")

            else:
                response = self.capability_worker.text_to_text_response(
                    f"The user said: '{user_input}'. I can check server resources, "
                    f"list accounts, list domains, check disk or bandwidth usage, "
                    f"suspend/unsuspend accounts, get the hostname, or restart a service. "
                    f"Suggest the best action in one short sentence."
                )
                await self.capability_worker.speak(response)

        except Exception as e:
            await self.capability_worker.speak(
                "Sorry, something went wrong with the WHM request. "
                "Please check your server connection and try again."
            )

        self.capability_worker.resume_normal_flow()

    def _classify_intent(self, user_input: str) -> Dict[str, str]:
        """Use the LLM to classify user intent into an action."""
        prompt = (
            "Classify this user input for a WHM server management assistant. "
            "Return ONLY valid JSON with no markdown fences.\n"
            '{"action": "resources|accounts|domains|disk|bandwidth|'
            'suspend|unsuspend|hostname|restart|unknown", '
            '"account": "username if mentioned else empty string", '
            '"service": "service name if mentioned else empty string"}\n\n'
            f"User: {user_input}"
        )
        raw = self.capability_worker.text_to_text_response(prompt)
        clean = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(clean)
        except (json.JSONDecodeError, TypeError):
            return {"action": "unknown", "account": "", "service": ""}


# ---------------------------------------------------------------------------
# Initialize helper
# ---------------------------------------------------------------------------

def initialize() -> Dict[str, Any]:
    return {
        "name": "WHM Ability",
        "version": __version__,
        "author": __author__,
        "description": __description__,
        "commands": [
            "get_server_resources / resources → server CPU/disk info",
            "list_accounts / accounts → all cPanel accounts",
            "list_domains / domains → hosted domains",
            "get_disk_usage / disk → needs {'account': 'username'}",
            "suspend_account / suspend → needs {'account': 'username'}",
            "unsuspend_account / unsuspend → needs {'account': 'username'}",
            "get_bandwidth / bandwidth → optional {'account': 'username'}",
            "get_hostname / hostname → server hostname",
            "restart_service / restart → needs {'service': 'name'}",
        ]
    }
