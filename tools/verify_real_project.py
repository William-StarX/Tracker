"""Reproduce full-result transport checks on the public Apache Commons Lang fixture.

Uses an existing clone and prepared engine. Does not fetch, checkout or build the target.
Writes full reports only to the operator-supplied output directory; do not publish them blindly.
"""
import argparse
import asyncio
import importlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


def stable(result):
    # Only omit clocks. Evidence, warnings, target identity and engine metadata stay intact.
    return {key: value for key, value in result.items() if key not in {"timings", "generated_at"}}


async def verify(args):
    import httpx2
    from mcp import Client as MCPClient, StdioServerParameters
    from mcp.client.streamable_http import streamable_http_client

    package = importlib.import_module(args.module)
    repo = str(Path(args.repo).resolve(strict=True))
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix="java-agent-fixture-") as temporary:
        fixture = Path(temporary)
        before, after = fixture / "before", fixture / "after"
        before.mkdir()
        after.mkdir()
        (before / "Sample.java").write_text("public class Sample { int oldName(int x) { return x + 1; } }\n", encoding="utf-8")
        (after / "Sample.java").write_text("public class Sample { int newName(int x) { return x + 1; } }\n", encoding="utf-8")
        if args.module == "refactoringminer_agent":
            cases = {
                "review": {"repo": repo, "base": "567bcda3de4d8768a2dc1e3ffc567b5879a9a74f", "head": "b9b30efb01e861a16503232bb96b684107e73199"},
                "directories": {"before": str(before), "after": str(after)},
            }
        else:
            cases = {
                "overview": {"repo": repo},
                "trace": {"repo": repo, "commit": "a36c903d4f1065bc59f5e6d2bb0f9d92a5e71d83",
                          "file": "src/main/java/org/apache/commons/lang3/time/DateUtils.java", "line": 1009, "name": "aField", "max_events": 1000},
            }
        expected = {}

        def record(channel, operation, response):
            (output / f"{operation}-{channel}.json").write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
            assert response["status"] in {"ok", "partial"}, (channel, operation, response.get("error"))
            raw = stable(response["result"])
            if operation not in expected:
                expected[operation] = raw
            assert raw == expected[operation], (channel, operation, "result differs")
            rows.append({"operation": operation, "channel": channel, "status": response["status"], "complete_result_equal": True})
            print(operation, channel, "ok", flush=True)

        local = package.Client()
        for operation, arguments in cases.items():
            record("sdk", operation, local.call(operation, **arguments))
            completed = subprocess.run([sys.executable, "-m", args.module, "call"],
                input=json.dumps({"operation": operation, **arguments}).encode(), capture_output=True, check=True)
            record("cli", operation, json.loads(completed.stdout))

        server_args = ["-m", args.module, "mcp", "--root", repo, "--root", temporary]
        runtime_env = {key: value for key, value in os.environ.items() if key.upper() in {
            "PATH", "SYSTEMROOT", "USERPROFILE", "JAVA_HOME", "JAVA_ANALYSIS_CACHE", "TEMP", "TMP"}}
        async with MCPClient(StdioServerParameters(command=sys.executable, args=server_args, env=runtime_env),
                             mode="legacy", read_timeout_seconds=240) as client:
            for operation, arguments in cases.items():
                response = await client.call_tool(operation, arguments)
                record("mcp-stdio", operation, response.structured_content)

        token = secrets.token_urlsafe(32)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen([sys.executable, "-m", args.module, "http", "--root", repo, "--root", temporary, "--port", str(port)],
            env={**runtime_env, "JAVA_AGENT_TOKEN": token}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        url = f"http://127.0.0.1:{port}"
        try:
            ready = False
            for _ in range(100):
                try:
                    request = urllib.request.Request(url + "/health", headers={"Authorization": "Bearer " + token})
                    with urllib.request.urlopen(request, timeout=1) as response:
                        ready = response.status == 200
                        break
                except OSError:
                    if process.poll() is not None:
                        break
                    await asyncio.sleep(0.1)
            assert ready, "HTTP server did not start"
            http_sdk = package.HTTPClient(url, token, timeout=240)
            for operation, arguments in cases.items():
                record("http", operation, http_sdk.call(operation, **arguments))
            async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + token}, timeout=240) as http:
                async with MCPClient(streamable_http_client(url + "/mcp", http_client=http), mode="legacy", read_timeout_seconds=240) as client:
                    for operation, arguments in cases.items():
                        response = await client.call_tool(operation, arguments)
                        record("mcp-http", operation, response.structured_content)
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        if args.baseline:
            for operation in cases:
                old = Path(args.baseline) / f"real_{operation}.response.json"
                if old.exists():
                    assert stable(json.loads(old.read_text(encoding="utf-8-sig"))["result"]) == expected[operation], (operation, "prior result differs")
                    rows.append({"operation": operation, "channel": "prior-interface-1.3.0", "complete_result_equal": True})
        summary = {"version": package.__version__, "project": "apache/commons-lang", "checks": rows,
                   "normalization": "Excluded only top-level timings and generated_at; all other report fields compared.",
                   "scope": "Transport/result regression, not a new upstream speed or accuracy benchmark."}
        (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, choices=["refactoringminer_agent", "codetracker_agent"])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--baseline", help="Optional local 1.3.0 evidence directory; never uploads it")
    asyncio.run(verify(parser.parse_args()))
