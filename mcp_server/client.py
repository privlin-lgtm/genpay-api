from typing import Any

import httpx2
from mcp.server.mcpserver.exceptions import ToolError

API_KEY_HEADER = "X-API-Key"


class GenPayClient:
    """
    Sends GETs to the GenPay API and turns failures into ToolErrors whose text
    the model can act on. ToolError is the only exception type whose message
    the MCP SDK passes to the model; anything else shows up as a bare
    "Error executing tool". The API key never appears in an error.

    Takes an injected httpx2.Client: a real one pointed at GENPAY_API_URL in
    production, FastAPI's TestClient (an httpx2.Client) in tests.
    """

    def __init__(self, http: httpx2.Client, api_key: str) -> None:
        self._http = http
        self._api_key = api_key

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            response = self._http.get(path, params=clean, headers={API_KEY_HEADER: self._api_key})
        except httpx2.TimeoutException as exc:
            raise ToolError("GenPay API timed out; try again shortly.") from exc
        except httpx2.TransportError as exc:
            raise ToolError(
                "Could not reach the GenPay API; check GENPAY_API_URL and that the API is running."
            ) from exc

        if response.status_code == 401:
            raise ToolError("GenPay rejected the MCP server's API key; check GENPAY_MCP_API_KEY.")
        if response.status_code == 404:
            raise ToolError(_detail(response) or "Not found")
        if response.status_code == 422:
            raise ToolError(f"GenPay rejected the request: {_detail(response) or 'invalid input'}")
        if response.status_code >= 400:
            raise ToolError(f"GenPay API returned HTTP {response.status_code}.")
        try:
            return response.json()
        except ValueError as exc:
            raise ToolError(
                "GenPay API returned a response that isn't JSON; check GENPAY_API_URL points at the API."
            ) from exc


def _detail(response: httpx2.Response) -> str | None:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return None
    return detail if isinstance(detail, str) else (str(detail) if detail else None)
