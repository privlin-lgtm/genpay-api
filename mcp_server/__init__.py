"""
Read-only MCP server for GenPay.

A thin HTTP client of the running API: every tool is one GET against an
existing route, sent with the mcp-agent ApiClient's key. Most of those routes
need a key and return financial data, and the API refuses that key on any
write, so treat GENPAY_MCP_API_KEY as a secret that reads the whole ledger. It never imports `app`
(tests/test_architecture.py enforces this), so it can't bypass auth, the
api -> services -> repositories layering, or get_db()'s one-commit-per-request
rule. See docs/mcp.md.
"""
