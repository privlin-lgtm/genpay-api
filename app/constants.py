"""Well-known ApiClient names, shared between seed_data.py (which creates them)
and the services that need to look one up (e.g. to attribute a webhook-originated
authorization to the "processor-webhook" system actor)."""

INTERNAL_ADMIN_CLIENT_NAME = "internal-admin"
PROCESSOR_WEBHOOK_CLIENT_NAME = "processor-webhook"
# The read-only MCP server (mcp_server/) calls the API with this client's key,
# so anything it does is attributed to it and never to internal-admin.
MCP_AGENT_CLIENT_NAME = "mcp-agent"

# Clients that may only use safe methods (GET/HEAD/OPTIONS). Enforced by
# require_api_key, so a leaked mcp-agent key can read but never write, whatever
# tools the MCP server happens to expose.
READ_ONLY_CLIENT_NAMES = frozenset({MCP_AGENT_CLIENT_NAME})
