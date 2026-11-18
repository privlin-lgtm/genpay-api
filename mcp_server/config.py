import os
from dataclasses import dataclass

DEFAULT_API_URL = "http://127.0.0.1:8000"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class McpConfig:
    api_url: str
    api_key: str
    timeout_seconds: float = 10.0


def load_config(env: dict[str, str] | None = None) -> McpConfig:
    """Read the server's settings from the environment, failing fast on a missing key."""
    source = os.environ if env is None else env
    api_key = source.get("GENPAY_MCP_API_KEY", "").strip()
    if not api_key:
        raise ConfigError(
            "GENPAY_MCP_API_KEY is not set: the MCP server needs the mcp-agent client's API key "
            "(MCP_AGENT_API_KEY on the API side; 'change-me-mcp' in dev)."
        )
    return McpConfig(
        api_url=source.get("GENPAY_API_URL", DEFAULT_API_URL).rstrip("/"),
        api_key=api_key,
        timeout_seconds=float(source.get("GENPAY_MCP_TIMEOUT_SECONDS", "10")),
    )
