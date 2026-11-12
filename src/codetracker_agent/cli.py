"""Small CLI for JSON calls, setup, services and agent configuration."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from . import _core
from ._meta import DEFAULT_PORT, DISTRIBUTION, VERSION
from .adapters import HOSTS, configuration
from .client import Client


def main(argv=None) -> int:
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog=DISTRIBUTION)
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("describe", help="Print tool schemas without running Java")
    commands.add_parser("doctor", help="Inspect engine readiness")
    prepare = commands.add_parser("prepare", help="Explicitly download and prepare engine dependencies")
    prepare.add_argument("--timeout", type=int, default=600)
    call = commands.add_parser("call", help="Read one JSON request from stdin or a file")
    call.add_argument("--request", help="UTF-8 JSON file (default: stdin)")
    for mode in ("mcp", "http", "config"):
        command = commands.add_parser(mode)
        command.add_argument("--root", action="append", required=True, help="Authorized project directory; repeatable")
        command.add_argument("--output-root", help="Optional directory for complete report files")
        if mode == "http":
            command.add_argument("--port", type=int, default=DEFAULT_PORT)
            command.add_argument("--token-env", default="JAVA_AGENT_TOKEN", help="Name of environment variable containing a random bearer token")
        if mode == "config":
            command.add_argument("agent", choices=HOSTS)
            command.add_argument("--python", help="Absolute Python executable with this package installed")
            command.add_argument("--java-home", help="Optional JDK/JRE directory for the child server")
            command.add_argument("--cache-dir", help="Optional pre-prepared engine cache")
    args = parser.parse_args(argv)
    try:
        if args.command == "describe":
            result = Client().describe()
        elif args.command == "doctor":
            result = Client().doctor()
        elif args.command == "prepare":
            result = Client().prepare(timeout=args.timeout)
        elif args.command == "call":
            raw = Path(args.request).read_text(encoding="utf-8-sig") if args.request else sys.stdin.read()
            request = json.loads(raw.lstrip("\ufeff"))
            if not isinstance(request, dict) or "operation" not in request:
                raise ValueError("Expected an object containing operation and its arguments.")
            result = Client().call(request.pop("operation"), **request)
        elif args.command == "config":
            env = {key: value for key, value in (("JAVA_HOME", args.java_home), ("JAVA_ANALYSIS_CACHE", args.cache_dir)) if value}
            print(configuration(args.agent, args.root, python=args.python, output_root=args.output_root, env=env), end="")
            return 0
        else:
            client = Client(allowed_roots=args.root, output_root=args.output_root)
            try:
                from .service import create_http_app, run_stdio
                if args.command == "mcp":
                    asyncio.run(run_stdio(client))
                else:
                    import uvicorn
                    if not 1 <= args.port <= 65535:
                        raise ValueError("Port must be between 1 and 65535.")
                    token = os.environ.get(args.token_env, "")
                    app = create_http_app(client, token)
                    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="error")
            except ModuleNotFoundError:
                print(f"Install {DISTRIBUTION}[server] to enable HTTP/MCP services.", file=sys.stderr)
                return 2
            return 0
    except (ValueError, OSError, UnicodeError) as exc:
        if args.command in {"mcp", "http", "config"}:
            print("Cannot start service or generate configuration: " + str(exc), file=sys.stderr)
            return 2
        result = _core.failure(None, "INVALID_ARGUMENT", str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result.get("status") == "error" else 0
