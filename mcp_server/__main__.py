"""
Run the GenPay MCP server.

    python -m mcp_server                # stateless streamable HTTP on 127.0.0.1:8001/mcp
    python -m mcp_server --stdio        # stdio, for a local client that spawns the process
"""

import argparse

import httpx2
import uvicorn

from mcp_server.client import GenPayClient
from mcp_server.config import load_config
from mcp_server.server import build_server


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m mcp_server", description=__doc__)
    parser.add_argument("--stdio", action="store_true", help="serve over stdio instead of HTTP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    config = load_config()
    http = httpx2.Client(base_url=config.api_url, timeout=config.timeout_seconds)
    server = build_server(GenPayClient(http, config.api_key))

    if args.stdio:
        server.run("stdio")
        return
    # Stateless: no session kept between requests, so any instance can serve any call.
    app = server.streamable_http_app(stateless_http=True, json_response=True, host=args.host)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
