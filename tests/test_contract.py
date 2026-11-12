import asyncio
import importlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request

import pytest


def core(module_name):
    return importlib.import_module(module_name + "._core")


def operation(module_name):
    return "review" if module_name.startswith("refactoring") else "overview"


def test_complete_result_and_environment(package, module_name, monkeypatch):
    raw = {"status": "partial", "evidence": {"unicode": "完整证据", "events": list(range(100))},
           "warnings": ["history incomplete"], "limitations": ["test"], "target": {"revision": "abc"}}
    observed = {}

    def run(command, **kwargs):
        observed.update(kwargs)
        return subprocess.CompletedProcess(command, 0, json.dumps(raw).encode(), b"diagnostic")

    monkeypatch.setattr(core(module_name).subprocess, "run", run)
    monkeypatch.setenv("OPENAI_API_KEY", "test-value-not-a-credential")
    monkeypatch.setenv("JAVA_AGENT_TOKEN", "test-value-not-a-credential")
    monkeypatch.setenv("JAVA_TOOL_OPTIONS", "test-value-not-forwarded")
    monkeypatch.setenv("GIT_DIR", "test-value-not-forwarded")
    result = package.Client().call(operation(module_name), repo="/example")
    assert result["result"] == raw
    assert result["status"] == "partial" and result["error"] is None
    assert result["process"]["stderr"] == "diagnostic"
    assert not {"OPENAI_API_KEY", "JAVA_AGENT_TOKEN", "JAVA_TOOL_OPTIONS", "GIT_DIR"} & observed["env"].keys()


@pytest.mark.parametrize("options", [{"max_files": 0}, {"max_files": True}, {"unexpected": 1}, {"format": "compact"}])
def test_invalid_arguments(package, module_name, options):
    result = package.Client().call(operation(module_name), repo="/example", **options)
    assert result["status"] == "error" and result["error"]["code"] == "INVALID_ARGUMENT"


def test_unknown_operation(package):
    assert package.Client().call("does-not-exist")["error"]["code"] == "INVALID_ARGUMENT"


def test_scope_and_output(package, module_name, tmp_path):
    allowed = tmp_path / "project"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    client = package.Client(allowed_roots=[allowed])
    assert client.call(operation(module_name), repo=outside)["error"]["code"] == "ACCESS_DENIED"
    assert client.call(operation(module_name), repo=allowed, output=tmp_path / "report.json")["error"]["code"] == "ACCESS_DENIED"
    with pytest.raises(ValueError):
        package.Client(allowed_roots=[])


def test_parent_git_scope(package, module_name, tmp_path):
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "small-subdir"
    nested.mkdir()
    result = package.Client(allowed_roots=[nested]).call(operation(module_name), repo=nested)
    assert result["error"]["code"] == "ACCESS_DENIED"


def test_linked_git_scope(package, module_name, tmp_path):
    (tmp_path / ".git").write_text("gitdir: ../other/.git", encoding="utf-8")
    result = package.Client(allowed_roots=[tmp_path]).call(operation(module_name), repo=tmp_path)
    assert result["error"]["code"] == "ACCESS_DENIED"


def test_symlink_scope(package, module_name, tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    link = allowed / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("OS does not permit test symlinks")
    assert package.Client(allowed_roots=[allowed]).call(operation(module_name), repo=link)["error"]["code"] == "ACCESS_DENIED"


def test_busy(package, module_name):
    client = package.Client()
    with client._lock:
        assert client.call(operation(module_name), repo="/example")["error"]["code"] == "BUSY"


def test_process_error_and_bad_json(package, module_name, monkeypatch):
    monkeypatch.setattr(core(module_name).subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, b"not json", b"err"))
    result = package.Client().call(operation(module_name), repo="/example")
    assert result["error"]["code"] == "INVALID_COMPONENT_RESPONSE"
    assert result["process"]["stdout_tail"] == "not json"


def test_existing_output(package, module_name, tmp_path):
    report = tmp_path / "report.json"
    report.write_text("keep this", encoding="utf-8")
    result = package.Client().call(operation(module_name), repo="/example", output=report)
    assert result["status"] == "error" and report.read_text() == "keep this"


@pytest.mark.parametrize("url", ["file:///example", "https://name:password@example.invalid", "http://localhost?q=secret", "http://localhost#fragment", "http://example.invalid"])
def test_httpclient_invalid_url(package, url):
    with pytest.raises(ValueError):
        package.HTTPClient(url, "test-token")


def test_httpclient_redirect(package, monkeypatch):
    client = package.HTTPClient("http://localhost", "test-token")

    def redirect(*args, **kwargs):
        raise urllib.error.HTTPError("http://localhost", 302, "redirect", {}, None)

    monkeypatch.setattr(client._opener, "open", redirect)
    with pytest.raises(package.TransportError, match="redirects"):
        client.call("anything")


def test_http_guard(package, module_name, tmp_path):
    from starlette.testclient import TestClient
    service = importlib.import_module(module_name + ".service")
    token = secrets.token_urlsafe(32)
    app = service.create_http_app(package.Client(allowed_roots=[tmp_path]), token)
    with TestClient(app, base_url="http://127.0.0.1") as http:
        assert http.get("/health").status_code == 401
        headers = {"Authorization": "Bearer " + token}
        assert http.get("/health", headers=headers).status_code == 200
        assert http.get("/tools", headers=headers).headers["cache-control"] == "no-store"
        assert http.get("/health", headers={**headers, "Origin": "https://example.invalid"}).status_code == 403
        assert http.get("/health", headers={**headers, "Host": "attacker.invalid"}).status_code == 403
        assert http.post("/invoke", headers=headers, json={"operation": "prepare"}).status_code == 403
        assert http.post("/invoke", headers=headers, json={"operation": operation(module_name), "repo": str(tmp_path.parent)}).status_code == 403
        assert http.post("/invoke", headers=headers, content=b"a" * 65537).status_code == 413
        assert http.post("/invoke", headers=headers, content="{}").status_code == 415
        assert http.post("/invoke", headers={**headers, "Content-Type": "application/json"}, content="{").status_code == 400
    with pytest.raises(ValueError):
        service.create_http_app(package.Client(), token)
    with pytest.raises(ValueError):
        service.create_http_app(package.Client(allowed_roots=[tmp_path]), "short")


@pytest.mark.parametrize("host", ["codex", "claude-code", "claude-desktop", "cursor", "vscode", "copilot"])
def test_agent_configuration_starts_mcp(module_name, tmp_path, host):
    from mcp import Client, StdioServerParameters
    adapters = importlib.import_module(module_name + ".adapters")
    text = adapters.configuration(host, [str(tmp_path)])
    config = tomllib.loads(text) if host == "codex" else json.loads(text)
    entries = config["mcp_servers" if host == "codex" else "servers" if host == "vscode" else "mcpServers"]
    entry = next(iter(entries.values()))
    assert entry["command"] == sys.executable
    if host == "codex":
        assert entry["tool_timeout_sec"] == 600
    parameters = StdioServerParameters(command=entry["command"], args=entry["args"], env=entry.get("env"))

    async def run():
        async with Client(parameters, mode="legacy", read_timeout_seconds=30) as client:
            assert client.instructions == importlib.import_module(module_name).Client().describe()["instructions"]
            listing = await client.list_tools()
            assert len(listing.tools) == 2
            assert "prepare" not in [item.name for item in listing.tools]
            response = await client.call_tool(operation(module_name), {"repo": str(tmp_path), "max_files": 0})
            assert response.is_error
            assert response.structured_content["error"]["code"] == "INVALID_ARGUMENT"
    asyncio.run(run())


def test_mcp_full_partial_result(package, module_name, tmp_path, monkeypatch):
    from mcp import Client
    service = importlib.import_module(module_name + ".service")
    value = {"interface_version": "1.0", "operation": operation(module_name), "status": "partial", "error": None,
             "result": {"evidence": list(range(300)), "warnings": ["incomplete"]}, "process": {"exit_code": 0, "stderr": ""}}
    local = package.Client(allowed_roots=[tmp_path])
    monkeypatch.setattr(local, "call", lambda *a, **kw: value)

    async def run():
        async with Client(service.create_mcp_server(local), mode="legacy") as client:
            result = await client.call_tool(operation(module_name), {"repo": str(tmp_path)})
            assert not result.is_error
            assert result.structured_content == value
            assert json.loads(result.content[0].text) == value
    asyncio.run(run())


def test_stdio_auto_negotiation(module_name, tmp_path):
    from mcp import Client, StdioServerParameters

    async def run():
        parameters = StdioServerParameters(command=sys.executable, args=["-m", module_name, "mcp", "--root", str(tmp_path)])
        async with Client(parameters, read_timeout_seconds=30) as client:
            assert client.instructions == importlib.import_module(module_name).Client().describe()["instructions"]
            assert len((await client.list_tools()).tools) == 2
    asyncio.run(run())


@pytest.fixture
def http_process(module_name, tmp_path):
    token = secrets.token_urlsafe(32)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([sys.executable, "-m", module_name, "http", "--root", str(tmp_path), "--port", str(port)],
        env={**os.environ, "JAVA_AGENT_TOKEN": token}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{port}"
    ready = False
    try:
        for _ in range(150):
            try:
                request = urllib.request.Request(url + "/health", headers={"Authorization": "Bearer " + token})
                with urllib.request.urlopen(request, timeout=1) as response:
                    ready = response.status == 200
                    break
            except OSError:
                if process.poll() is not None:
                    break
                time.sleep(0.1)
        assert ready, "HTTP process did not start"
        yield url, token
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        process.communicate()


def test_http_sdk_and_mcp(package, module_name, tmp_path, http_process):
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    url, token = http_process
    result = package.HTTPClient(url, token).call(operation(module_name), repo=tmp_path, max_files=0)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    denied = package.HTTPClient(url, "wrong").call(operation(module_name), repo=tmp_path)
    assert denied["error"]["code"] == "UNAUTHORIZED"

    async def run():
        async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + token}) as http:
            async with Client(streamable_http_client(url + "/mcp", http_client=http), mode="legacy") as client:
                assert client.instructions == package.Client().describe()["instructions"]
                listing = await client.list_tools()
                assert len(listing.tools) == 2
                response = await client.call_tool(operation(module_name), {"repo": str(tmp_path), "max_files": 0})
                assert response.is_error and response.structured_content["status"] == "error"
    asyncio.run(run())


def test_checkpoint_catalog_isolated_and_valid(package):
    client = package.Client()
    catalog = client.describe(analysis_only=True)
    tools = {item["name"] for item in catalog["tools"]}
    assert catalog["instructions"]
    assert catalog["checkpoints"]
    assert all(set(item["tools"]) <= tools for item in catalog["checkpoints"])
    catalog["checkpoints"][0]["tools"].clear()
    assert client.describe()["checkpoints"][0]["tools"]


def test_skill_install_and_bound_launcher(package, module_name, tmp_path):
    installer = importlib.import_module(module_name + ".skill")
    destination = installer.install(str(tmp_path / "skills"))
    binding = json.loads((destination / "runtime.local.json").read_text(encoding="utf-8"))
    assert binding == {"python": sys.executable}
    result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(destination / "scripts/run.py"), "describe"],
                            capture_output=True, check=True)
    assert json.loads(result.stdout) == package.Client().describe()


def test_skill_install_preserves_existing_content(module_name, tmp_path):
    installer = importlib.import_module(module_name + ".skill")
    destination = installer.install(str(tmp_path / "skills"))
    (destination / "SKILL.md").write_text("Local customization", encoding="utf-8")
    with pytest.raises(ValueError, match="already exists"):
        installer.install(str(tmp_path / "skills"))
    assert (destination / "SKILL.md").read_text() == "Local customization"
