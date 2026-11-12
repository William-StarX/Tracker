"""Optional MCP transports and an authenticated, loopback-only HTTP API."""
from __future__ import annotations

import hmac
import json

from . import _core
from ._meta import OPERATIONS, SERVER_NAME, VERSION
from .client import Client

MAX_REQUEST_BYTES = 65536


def dispatch(client: Client, request: object) -> dict:
    if not isinstance(request, dict) or not isinstance(request.get("operation"), str):
        return _core.failure(None, "INVALID_ARGUMENT", "Expected an object containing operation and its arguments.")
    arguments = dict(request)
    operation = arguments.pop("operation")
    if operation not in OPERATIONS:
        return _core.failure(operation, "OPERATION_NOT_EXPOSED", "Only analysis tools are exposed by the service.")
    return client.call(operation, **arguments)


def create_mcp_server(client: Client):
    import anyio
    from mcp.server import Server
    from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

    if client.roots is None:
        raise ValueError("Services require explicit project roots.")
    catalog = client.describe(analysis_only=True)

    async def list_tools(ctx, params):
        return ListToolsResult(tools=[Tool(name=item["name"], description=item["description"],
            inputSchema=item["inputSchema"], outputSchema=catalog["response_schema"])
            for item in catalog["tools"]])

    async def call_tool(ctx, params):
        arguments = params.arguments or {}
        # The tool name is authoritative; arguments cannot select another operation.
        if "operation" in arguments:
            result = _core.failure(params.name, "INVALID_ARGUMENT", "operation is not a tool argument.")
        else:
            result = await anyio.to_thread.run_sync(dispatch, client, {"operation": params.name, **arguments})
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
                              structuredContent=result, isError=result["status"] == "error")

    return Server(SERVER_NAME, version=VERSION, instructions=catalog["instructions"],
                  on_list_tools=list_tools, on_call_tool=call_tool)


async def run_stdio(client: Client) -> None:
    from mcp.server.stdio import stdio_server

    server = create_mcp_server(client)
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


class _HTTPGuard:
    """Authenticate before reading requests; bound bodies and reject browser origins."""

    def __init__(self, app, token: str):
        if len(token) < 32 or not token.isascii() or any(ord(char) < 33 for char in token):
            raise ValueError("The HTTP token must contain at least 32 printable ASCII characters.")
        self.app = app
        self.authorization = ("Bearer " + token).encode("ascii")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse

        async def reject(status, code, message):
            response = JSONResponse(_core.failure(None, code, message), status_code=status,
                                    headers={"Cache-Control": "no-store"})
            await response(scope, receive, send)

        headers = scope.get("headers", [])
        auth = [value for key, value in headers if key.lower() == b"authorization"]
        if len(auth) != 1 or not hmac.compare_digest(auth[0], self.authorization):
            return await reject(401, "UNAUTHORIZED", "A valid bearer token is required.")
        hosts = [value.decode("latin-1").lower() for key, value in headers if key.lower() == b"host"]
        if len(hosts) != 1 or hosts[0].split(":")[0] not in {"127.0.0.1", "localhost"}:
            return await reject(403, "INVALID_HOST", "Only loopback hosts are allowed.")
        if any(key.lower() == b"origin" for key, _ in headers):
            return await reject(403, "ORIGIN_DENIED", "Browser-origin requests are not supported.")
        lengths = [value for key, value in headers if key.lower() == b"content-length"]
        try:
            if len(lengths) > 1 or (lengths and (int(lengths[0]) < 0 or int(lengths[0]) > MAX_REQUEST_BYTES)):
                return await reject(413, "REQUEST_TOO_LARGE", "Request exceeds the 64 KiB limit.")
        except ValueError:
            return await reject(400, "INVALID_ARGUMENT", "Invalid content length.")
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_REQUEST_BYTES:
                return await reject(413, "REQUEST_TOO_LARGE", "Request exceeds the 64 KiB limit.")
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        async def private_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [(b"cache-control", b"no-store")]
            await send(message)

        await self.app(scope, bounded_receive, private_send)


def create_http_app(client: Client, token: str):
    import anyio
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def health(request):
        return JSONResponse({"name": SERVER_NAME, "version": VERSION, "status": "ok"})

    async def tools(request):
        return JSONResponse(client.describe(analysis_only=True))

    async def invoke(request):
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return JSONResponse(_core.failure(None, "INVALID_ARGUMENT", "Use application/json."), status_code=415)
        try:
            value = await request.json()
        except (ValueError, UnicodeError):
            return JSONResponse(_core.failure(None, "INVALID_ARGUMENT", "Request is not valid JSON."), status_code=400)
        result = await anyio.to_thread.run_sync(dispatch, client, value)
        code = result.get("error", {}).get("code") if result.get("error") else None
        status = {"INVALID_ARGUMENT": 400, "ACCESS_DENIED": 403, "OPERATION_NOT_EXPOSED": 403, "BUSY": 429}.get(code, 200)
        return JSONResponse(result, status_code=status)

    server = create_mcp_server(client)
    app = server.streamable_http_app(stateless_http=True, json_response=True,
        max_request_body_size=MAX_REQUEST_BYTES, custom_starlette_routes=[
            Route("/health", health), Route("/tools", tools), Route("/invoke", invoke, methods=["POST"])])
    return _HTTPGuard(app, token)
