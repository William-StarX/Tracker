#!/usr/bin/env python3
"""Trace committed Java code with CodeTracker without changing the source repository."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import time
from typing import Any

from reporting import render_result

SKILL_DIR = Path(__file__).resolve().parents[1]
COMPONENT = "codetracker-investigate"


class TraceError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise TraceError("INVALID_ARGUMENT", message)


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def parser() -> Parser:
    result = Parser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True, parser_class=Parser)
    commands.add_parser("doctor", help="inspect local Java, Maven and prepared engine")
    setup = commands.add_parser("prepare", help="build the pinned adapter in the external cache")
    setup.add_argument("--timeout", type=positive_int, default=600)
    trace = commands.add_parser("trace", help="trace a Java element in an existing local Git repository")
    trace.add_argument("--repo", required=True)
    trace.add_argument("--commit", default="HEAD", help="revision containing the requested file and line")
    trace.add_argument("--file", required=True, help="repository-relative .java path at --commit")
    trace.add_argument("--line", required=True, type=positive_int, help="1-based line at --commit")
    trace.add_argument("--name", help="optional method or local-variable name to disambiguate the selected element")
    trace.add_argument("--max-events", type=positive_int, default=100, help="returned event limit, at most 1000")
    trace.add_argument("--max-source-bytes", type=positive_int, default=1_000_000)
    trace.add_argument("--timeout", type=positive_int, default=120, help="Java process timeout in seconds")
    trace.add_argument("--memory-mb", type=positive_int, default=2048, help="Java heap ceiling")
    trace.add_argument("--output", help="optional JSON output file outside the source repository")
    trace.add_argument("--format", choices=["full", "compact"], default="full",
                       help="stdout view; --output always saves full evidence")
    return result


def git(repo: Path, *args: str, timeout: int = 20) -> bytes:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    # Do not inherit unrelated Git repository overrides from a caller's shell.
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        env.pop(key, None)
    try:
        completed = subprocess.run(
            ["git", "--no-optional-locks", "--literal-pathspecs", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, env=env, check=False,
        )
    except FileNotFoundError as exc:
        raise TraceError("GIT_NOT_FOUND", "Git is required for local history tracing.") from exc
    except subprocess.TimeoutExpired as exc:
        raise TraceError("GIT_TIMEOUT", "A local Git metadata read exceeded its time limit.") from exc
    if completed.returncode:
        message = completed.stderr.decode("utf-8", errors="replace").strip()[-1500:]
        raise TraceError("GIT_READ_FAILED", message or "Unable to read local Git metadata.")
    return completed.stdout


def validate_target(args: argparse.Namespace, warnings: list[str]) -> dict[str, Any]:
    supplied_repo = Path(args.repo).expanduser().resolve()
    if not supplied_repo.is_dir():
        raise TraceError("INVALID_REPOSITORY", "--repo must be an existing local Git worktree directory.")
    if not args.commit or args.commit.startswith("-") or len(args.commit) > 512 or any(ord(c) < 32 for c in args.commit):
        raise TraceError("INVALID_REVISION", "Provide a local revision name or full commit SHA.")
    metadata = git(supplied_repo, "rev-parse", "--show-toplevel", "--absolute-git-dir",
                   "--is-shallow-repository", "--verify", "--end-of-options", args.commit + "^{commit}").decode("utf-8").splitlines()
    if len(metadata) != 4:
        raise TraceError("INVALID_REPOSITORY", "Unable to resolve repository metadata unambiguously.")
    root, git_dir = (Path(value).resolve() for value in metadata[:2])
    shallow, commit = metadata[2] == "true", metadata[3]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise TraceError("UNSUPPORTED_OBJECT_FORMAT", "This CodeTracker adapter requires SHA-1 Git repositories.")
    requested_path = args.file.replace("\\", "/")
    path = PurePosixPath(requested_path)
    if (not requested_path or path.is_absolute() or ":" in requested_path or
            any(part in {"..", ".git"} for part in path.parts) or
            any(ord(c) < 32 for c in requested_path) or not requested_path.endswith(".java")):
        raise TraceError("INVALID_PATH", "--file must be a repository-relative .java source path without '..'.")
    relative = path.as_posix()
    listing = git(root, "ls-tree", "-l", "-z", commit, "--", relative)
    records = [part for part in listing.split(b"\0") if part]
    if len(records) != 1:
        raise TraceError("FILE_NOT_FOUND", "The requested Java file is not present at the specified commit.")
    metadata, actual_path = records[0].split(b"\t", 1)
    mode, object_type, blob, raw_size = metadata.decode("ascii").split()
    if actual_path.decode("utf-8") != relative or mode not in {"100644", "100755"} or object_type != "blob":
        raise TraceError("UNSUPPORTED_FILE", "The requested path must be a regular committed Java file, not a symlink or submodule.")
    size = int(raw_size)
    if size > args.max_source_bytes:
        raise TraceError("SOURCE_TOO_LARGE", f"Source is {size} bytes; increase --max-source-bytes deliberately if appropriate.")
    try:
        source = git(root, "cat-file", "blob", blob).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TraceError("UNSUPPORTED_ENCODING", "Source must be UTF-8; convert a copy before tracing.") from exc
    lines = source.splitlines()
    if args.line > len(lines):
        raise TraceError("LINE_OUT_OF_RANGE", f"Requested line {args.line}; committed file has {len(lines)} lines.")
    if shallow:
        warnings.append("The repository is shallow. Available history can be incomplete and upstream tracking may stop at a missing parent.")
    if git(root, "status", "--porcelain=v1", "--untracked-files=no", "--", relative).strip():
        warnings.append("This file has worktree/index changes. The requested line is interpreted in the committed revision; those changes are not traced.")
    if args.max_events > 1000:
        raise TraceError("INVALID_ARGUMENT", "--max-events must not exceed 1000.")
    if args.name is not None and (not args.name.strip() or any(ord(c) < 32 for c in args.name)):
        raise TraceError("INVALID_ARGUMENT", "--name must be a nonempty source element name without control characters.")
    if args.output:
        output = Path(args.output).expanduser().resolve()
        if output == root or root in output.parents:
            raise TraceError("OUTPUT_INSIDE_REPOSITORY", "Choose --output outside the source repository to preserve read-only analysis.")
    return {
        "repository": str(root), "git_dir": str(git_dir), "requested_revision": args.commit,
        "commit": commit, "file": relative, "line": args.line,
        "source_line": lines[args.line - 1][:600], "blob": blob, "source_bytes": size,
        "shallow": shallow,
    }


def trace(args: argparse.Namespace, result: dict[str, Any]) -> None:
    target = validate_target(args, result["warnings"])
    result["target"] = {key: value for key, value in target.items() if key != "git_dir"}
    if args.name is not None:
        result["target"]["requested_name"] = args.name
    from runtime import run_java_bridge
    payload = run_java_bridge(
        SKILL_DIR, COMPONENT,
        ["--repo", target["repository"], "--git-dir", target["git_dir"],
         "--commit", target["commit"], "--file", target["file"], "--line", str(args.line),
         "--max-events", str(args.max_events)] + (["--name", args.name] if args.name is not None else []),
        timeout=args.timeout, memory_mb=args.memory_mb,
    )
    if not isinstance(payload, dict) or payload.get("status") not in {"ok", "partial", "error"}:
        raise TraceError("INVALID_ENGINE_OUTPUT", "The engine did not return a recognized result envelope.")
    result["status"] = payload["status"]
    result["engine"] = payload.get("engine", {})
    result["evidence"] = payload.get("evidence", {})
    result["warnings"].extend(payload.get("warnings", []))
    result["limitations"].extend(payload.get("limitations", []))
    result["timings"]["engine_ms"] = payload.get("engine_elapsed_ms")
    if payload.get("runtime_diagnostics"):
        result["engine_diagnostics"] = payload["runtime_diagnostics"]
    if payload.get("error"):
        result["error"] = payload["error"]
    if target["shallow"] and result["status"] == "ok":
        result["status"] = "partial"


def write_result(result: dict[str, Any], output: str | None, format: str = "full") -> None:
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output:
        path = Path(output).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".trace-", suffix=".json", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(text)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    sys.stdout.write(render_result(result, format, output))


def main(argv: list[str] | None = None) -> int:
    started = time.monotonic()
    result: dict[str, Any] = {
        "schema_version": "1.0", "component": COMPONENT, "operation": "trace", "status": "error",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target": {}, "evidence": {}, "warnings": [], "limitations": [], "timings": {},
    }
    args = None
    validated_output = None
    try:
        args = parser().parse_args(argv)
        result["operation"] = args.command
        if args.command == "trace":
            trace(args, result)
            validated_output = args.output
        elif args.command == "doctor":
            from runtime import doctor
            diagnosis = doctor(SKILL_DIR, COMPONENT)
            result["evidence"] = {key: value for key, value in diagnosis.items()
                                  if key not in {"schema_version", "component", "operation", "status"}}
            result["status"] = diagnosis.get("status", "error")
        else:
            from runtime import prepare_engine
            jar = prepare_engine(SKILL_DIR, COMPONENT, timeout=args.timeout)
            result["evidence"] = {"engine_jar": str(jar), "prepared": True}
            result["status"] = "ok"
    except TraceError as exc:
        result["error"] = {"code": exc.code, "message": str(exc)}
    except (RuntimeError, ImportError, OSError, ValueError) as exc:
        message = str(exc)[-2000:]
        code = "ENGINE_TIMEOUT" if "timed out" in message.lower() else "EXECUTION_FAILED"
        result["error"] = {"code": code, "message": message}
    result["timings"]["total_ms"] = round((time.monotonic() - started) * 1000)
    try:
        write_result(result, validated_output, getattr(args, "format", "full"))
    except OSError as exc:
        result["status"] = "error"
        result["error"] = {"code": "OUTPUT_WRITE_FAILED", "message": str(exc)}
        write_result(result, None)
    return 2 if result["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
