"""
Read-only MCP server for GenPay.

A thin HTTP client of the running API: every tool is one GET against a public
route, sent with the mcp-agent ApiClient's key. It never imports `app`
(tests/test_architecture.py enforces this), so it can't bypass auth, the
api -> services -> repositories layering, or get_db()'s one-commit-per-request
rule. See docs/mcp.md.
"""
