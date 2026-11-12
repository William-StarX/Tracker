"""Local and HTTP SDK clients; no third-party dependency for either client."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any, Iterable, cast
import urllib.error
import urllib.parse
import urllib.request

from . import _core
from ._meta import OPERATIONS
from .models import AnalysisResult, TransportError
from ._operations import Operations
from .workflow import INSTRUCTIONS, CHECKPOINTS


class Client(Operations):
    """Synchronous local client. Services must set allowed_roots explicitly."""

    def __init__(self, *, allowed_roots: Iterable[str | os.PathLike] | None = None,
                 output_root: str | os.PathLike | None = None):
        self.roots = None if allowed_roots is None else tuple(Path(p).expanduser().resolve(strict=True) for p in allowed_roots)
        if self.roots is not None and (not self.roots or any(not p.is_dir() for p in self.roots)):
            raise ValueError("At least one existing project directory is required.")
        self.output_root = Path(output_root).expanduser().resolve() if output_root is not None else None
        self._lock = Lock()

    def call(self, operation: str, **arguments: Any) -> AnalysisResult:
        arguments = {key: os.fspath(value) if isinstance(value, os.PathLike) else value for key, value in arguments.items()}
        if self.roots is not None:
            try:
                for key in ("repo", "before", "after"):
                    if key in arguments:
                        path = Path(arguments[key]).expanduser().resolve(strict=True)
                        if not any(path.is_relative_to(root) for root in self.roots):
                            raise ValueError("Requested project is outside the configured roots.")
                        arguments[key] = str(path)
                        if key == "repo":
                            self._check_git_scope(path)
                if "output" in arguments:
                    path = Path(arguments["output"]).expanduser().resolve()
                    if self.output_root is None or not path.is_relative_to(self.output_root):
                        raise ValueError("Output is outside the configured report directory.")
                    arguments["output"] = str(path)
            except (OSError, ValueError, TypeError):
                return cast(AnalysisResult, _core.failure(operation, "ACCESS_DENIED", "Requested path is unavailable or outside the configured scope."))
        if not self._lock.acquire(blocking=False):
            return cast(AnalysisResult, _core.failure(operation, "BUSY", "An analysis is already running; retry after it finishes."))
        try:
            return cast(AnalysisResult, _core.invoke(operation, **arguments))
        finally:
            self._lock.release()

    def describe(self, *, analysis_only: bool = False) -> dict:
        result = _core.describe()
        result["instructions"] = INSTRUCTIONS
        result["checkpoints"] = copy.deepcopy(CHECKPOINTS)
        if analysis_only:
            result["tools"] = [tool for tool in result["tools"] if tool["name"] in OPERATIONS]
        return result

    def _check_git_scope(self, path: Path) -> None:
        # Git discovers parent repositories and can redirect through linked worktrees.
        for parent in (path, *path.parents):
            metadata = parent / ".git"
            if metadata.exists() or metadata.is_symlink():
                if not any(parent.is_relative_to(root) for root in self.roots):
                    raise ValueError("Parent repository is outside scope.")
                if not metadata.is_dir() or metadata.is_symlink():
                    raise ValueError("Services require a regular clone, not linked Git metadata.")
                if (metadata / "commondir").exists() or (metadata / "objects/info/alternates").exists():
                    raise ValueError("Services do not allow shared Git object stores.")
                break

    def prepare(self, *, timeout: int = 600) -> AnalysisResult:
        """Explicit setup; may download pinned dependencies. Not exposed by services."""
        return self.call("prepare", timeout=timeout)

    def doctor(self) -> AnalysisResult:
        return self.call("doctor")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None  # Never forward bearer credentials to a redirected endpoint.


class HTTPClient(Operations):
    """Call an operator-managed HTTP service; project paths are server-side paths."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 180):
        url = urllib.parse.urlsplit(base_url)
        if url.scheme not in {"http", "https"} or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError("Use an HTTP(S) base URL without embedded credentials, query or fragment.")
        if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Use HTTPS for connections outside loopback.")
        if not token:
            raise ValueError("A bearer token is required.")
        self.base_url, self._token, self.timeout = base_url.rstrip("/"), token, timeout
        self._opener = urllib.request.build_opener(_NoRedirect())

    def call(self, operation: str, **arguments: Any) -> AnalysisResult:
        arguments = {key: os.fspath(value) if isinstance(value, os.PathLike) else value for key, value in arguments.items()}
        body = json.dumps({"operation": operation, **arguments}).encode("utf-8")
        request = urllib.request.Request(self.base_url + "/invoke", data=body,
            headers={"Authorization": "Bearer " + self._token, "Content-Type": "application/json"}, method="POST")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            if 300 <= exc.code < 400:
                raise TransportError("HTTP redirects are refused to protect credentials.") from None
            raw = exc.read()
        except (OSError, urllib.error.URLError):
            raise TransportError("Could not reach the configured HTTP service.") from None
        try:
            result = json.loads(raw)
            if not isinstance(result, dict) or result.get("status") not in {"ok", "partial", "error"}:
                raise ValueError("Unexpected response")
            return cast(AnalysisResult, result)
        except (ValueError, UnicodeError):
            raise TransportError("Service did not return a valid analysis envelope.") from None
