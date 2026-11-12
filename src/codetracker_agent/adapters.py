"""Generate host-native MCP configuration without changing personal settings."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from ._meta import MODULE, SERVER_NAME

HOSTS = ("codex", "claude-code", "claude-desktop", "cursor", "vscode", "copilot")


def configuration(host: str, roots: list[str], *, python: str | None = None,
                  output_root: str | None = None, env: dict[str, str] | None = None) -> str:
    """Return a snippet to merge into the named host's configuration."""
    if host not in HOSTS or not roots:
        raise ValueError("Choose a supported agent and at least one project root.")
    args = ["-m", MODULE, "mcp"]
    for root in roots:
        args.extend(["--root", str(Path(root).expanduser().resolve(strict=True))])
    if output_root:
        args.extend(["--output-root", str(Path(output_root).expanduser().resolve())])
    entry = {"command": python or sys.executable, "args": args}
    if env:
        if set(env) - {"JAVA_HOME", "JAVA_ANALYSIS_CACHE"}:
            raise ValueError("Only JAVA_HOME and JAVA_ANALYSIS_CACHE may be included in generated configuration.")
        entry["env"] = env
    if host == "codex":
        lines = [f"[mcp_servers.{SERVER_NAME}]", "command = " + json.dumps(entry["command"], ensure_ascii=False),
                 "args = " + json.dumps(args, ensure_ascii=False), "startup_timeout_sec = 30", "tool_timeout_sec = 600"]
        if env:
            lines += [f"[mcp_servers.{SERVER_NAME}.env]"]
            lines += [key + " = " + json.dumps(value, ensure_ascii=False) for key, value in env.items()]
        return "\n".join(lines) + "\n"
    if host == "vscode":
        entry["type"] = "stdio"
    return json.dumps({"servers" if host == "vscode" else "mcpServers": {SERVER_NAME: entry}}, ensure_ascii=False, indent=2) + "\n"
