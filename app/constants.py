"""Well-known ApiClient names, shared between seed_data.py (which creates them)
and the services that need to look one up (e.g. to attribute a webhook-originated
authorization to the "processor-webhook" system actor)."""

INTERNAL_ADMIN_CLIENT_NAME = "internal-admin"
PROCESSOR_WEBHOOK_CLIENT_NAME = "processor-webhook"
# The read-only MCP server (mcp_server/) calls the API with this client's key,
# so anything it does is attributed to it and never to internal-admin.
MCP_AGENT_CLIENT_NAME = "mcp-agent"
