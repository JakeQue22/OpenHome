import json
import requests
from typing import Any, Dict, Optional

# Plugin metadata
__version__ = "1.0.0"
__author__ = "OpenHome"
__description__ = "WHM/cPanel API Integration for hosting management"

# Import OpenHome SDK
try:
    from openhome_ability_sdk import MatchingCapability, AgentWorker
except ImportError:
    # Fallback for dev/testing
    class MatchingCapability:
        def __init__(self, unique_name: str, matching_hotwords: list):
            self.unique_name = unique_name
            self.matching_hotwords = matching_hotwords
    
    class AgentWorker:
        pass

# Hardcoded fallback config — user should override via OpenHome dashboard/UI
# (sandbox prevents file/env loading; this is the only safe way)
DEFAULT_CONFIG = {
    "host": "your-server.example.com",
    "username": "root",
    "api_token": "YOUR_API_TOKEN_HERE",
    "verify_ssl": True,
    "unique_name": "whm_ability",
    "matching_hotwords": ["whm", "hosting", "cpanel", "server"]
}

# Global config — in real deployment, dashboard overrides these defaults
_config: Dict[str, Any] = DEFAULT_CONFIG.copy()


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
            raise ValueError(f"WHM API Error: {data.get('statusmsg', 'Unknown')}")
        
        if "result" in data and isinstance(data["result"], list):
            for item in data["result"]:
                if isinstance(item, dict) and item.get("status") == 0:
                    raise ValueError(f"WHM API Error: {item.get('statusmsg', 'Unknown')}")
        
        return data
        
    except requests.exceptions.SSLError as e:
        raise requests.RequestException(f"SSL Error: {str(e)}. Check verify_ssl setting.")
    except requests.exceptions.ConnectionError:
        raise requests.RequestException(f"Cannot reach host: {_config['host']}")
    except requests.exceptions.Timeout:
        raise requests.RequestException("Request timed out")
    except requests.exceptions.RequestException as e:
        raise requests.RequestException(f"API failed: {str(e)}")


def get_server_resources() -> Dict[str, Any]:
    load_data = _make_api_request("loadavg")
    disk_data = _make_api_request("getdiskinfo")
    
    result = {
        "cpu": {
            "load_1min": load_data.get("avg", [0, 0, 0])[0],
            "load_5min": load_data.get("avg", [0, 0, 0])[1],
            "load_15min": load_data.get("avg", [0, 0, 0])[2],
            "status": "ok" if load_data.get("avg", [0, 0, 0])[0] < 4 else "high"
        },
        "memory": {
            "total_mb": disk_data.get("full Disco", {}).get("total", 0) // (1024 * 1024),
            "used_mb": disk_data.get("full Disco", {}).get("used", 0) // (1024 * 1024),
            "free_mb": disk_data.get("full Disco", {}).get("free", 0) // (1024 * 1024),
            "percent_used": 0
        },
        "disk": {
            "total_gb": disk_data.get("full Disco", {}).get("total", 0) // (1024**3),
            "used_gb": disk_data.get("full Disco", {}).get("used", 0) // (1024**3),
            "free_gb": disk_data.get("full Disco", {}).get("free", 0) // (1024**3),
            "percent_used": 0
        }
    }
    
    total = disk_data.get("full Disco", {}).get("total", 1)
    if total > 0:
        result["disk"]["percent_used"] = round((disk_data.get("full Disco", {}).get("used", 0) / total) * 100, 2)
    
    return result


def list_domains() -> Dict[str, Any]:
    data = _make_api_request("listdomains")
    domains = []
    
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


def execute_command(command: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    command = command.lower().strip()
    cmd_map = {
        "get_server_resources": get_server_resources,
        "resources": get_server_resources,
        "list_domains": list_domains,
        "domains": list_domains,
        "get_disk_usage": get_disk_usage,
        "disk": get_disk_usage
    }
    
    func = cmd_map.get(command)
    if not func:
        raise ValueError(f"Unknown command '{command}'. Valid: {', '.join(cmd_map.keys())}")
    
    if func is get_disk_usage:
        if not args or "account" not in args or not isinstance(args["account"], str) or not args["account"].strip():
            raise ValueError("get_disk_usage requires non-empty 'account' string")
        return func(args["account"])
    
    return func()


class WhmCpanelControlCapability(MatchingCapability):
    @classmethod
    def register_capability(cls) -> "WHMAbility":
        # Keep this minimal — no imports, no logic, no file access
        # Platform auto-handles any UI-set config / hotwords
        return cls(
            unique_name=DEFAULT_CONFIG["unique_name"],
            matching_hotwords=DEFAULT_CONFIG["matching_hotwords"],
        )
    
    def call(self, worker: AgentWorker) -> str:
        try:
            return json.dumps({
                "status": "success",
                "resources": get_server_resources(),
                "domains": list_domains(),
                "version": __version__
            }, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)}, indent=2)


def initialize() -> Dict[str, Any]:
    return {
        "name": "WHM Ability",
        "version": __version__,
        "author": __author__,
        "description": __description__,
        "commands": [
            "get_server_resources / resources → server CPU/mem/disk",
            "list_domains / domains → hosted domains",
            "get_disk_usage / disk → needs {'account': 'username'}"
        ]
    }
