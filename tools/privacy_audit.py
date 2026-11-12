"""Scan the Git index and release archives without printing secret values.

Heuristic checks complement manual review; they do not prove absence of all secrets.
Pass private local identifiers with --forbid; their values are not written to the report.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import zipfile

PATTERNS = {
    "private_key": re.compile(r"(?m)^-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "model_key": re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{35,}\b"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "credential_url": re.compile(r"(?:https?|ssh)://[^\s/:]+:[^\s/@]+@"),
    "private_home_path": re.compile(r"(?i)(?:[a-z]:[/\\](?:users|documents and settings)[/\\][^/\\\s\"']+|/(?:home|Users)/[^/\s\"']+)"),
    "private_chat_reference": re.compile(r"(?:chatgpt\.com/library\?|libfile_[a-f0-9]{16,}|skill_id=[a-f0-9]{16,}|chatgpt-conversation://[a-f0-9-]{30,})"),
}
FORBIDDEN_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", "target", "reports"}
FORBIDDEN_SUFFIXES = {".jar", ".class", ".jfr", ".pyc", ".pem", ".key", ".p12", ".pfx", ".keystore", ".log"}


def scan(name, data, forbidden):
    path = PurePosixPath(name)
    findings = []
    if FORBIDDEN_PARTS.intersection(path.parts) or path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name == "runtime.local.json" or path.name.startswith((".env", "hs_err_pid", "replay_pid")):
        findings.append({"file": name, "rule": "excluded_artifact"})
    try:
        content = data.decode("utf-8")
    except UnicodeError:
        return findings + [{"file": name, "rule": "unexpected_binary"}]
    for rule, pattern in PATTERNS.items():
        for match in pattern.finditer(content):
            # Example credentials are intentionally invalid and public, never real secrets.
            if rule == "credential_url" and "example.invalid" in content[match.start():match.end() + 32]:
                continue
            findings.append({"file": name, "rule": rule, "line": content.count("\n", 0, match.start()) + 1})
    for value in forbidden:
        if value and value.casefold() in content.casefold():
            findings.append({"file": name, "rule": "private_identifier"})
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--archive", action="append", default=[])
    parser.add_argument("--forbid", action="append", default=[])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.repo).resolve(strict=True)
    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(root), *arguments])
    names = git("ls-files", "-z").decode("utf-8").split("\0")
    records, findings = [], []
    for name in filter(None, names):
        data = git("show", ":" + name)
        records.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        findings.extend(scan(name, data, args.forbid))
    archives = []
    for value in args.archive:
        archive = Path(value)
        files = []
        if archive.suffix == ".whl" or archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as opened:
                files = [(item.filename, opened.read(item)) for item in opened.infolist() if not item.is_dir()]
        else:
            with tarfile.open(archive, "r:gz") as opened:
                for item in opened.getmembers():
                    if item.isfile():
                        files.append((item.name, opened.extractfile(item).read()))
                    elif not item.isdir():
                        findings.append({"file": archive.name + ":" + item.name, "rule": "archive_link"})
        for name, data in files:
            findings.extend(scan(archive.name + ":" + name, data, args.forbid))
        archives.append({"name": archive.name, "files": len(files), "bytes": archive.stat().st_size,
                         "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()})
    emails = git("log", "--format=%ae%n%ce").decode("utf-8").splitlines()
    ordinary = {value for value in emails if value and not value.endswith("@users.noreply.github.com") and value != "noreply@github.com"}
    report = {"index_files": records, "archives": archives, "findings": findings,
              "existing_history_ordinary_email_count": len(ordinary),
              "limits": "Heuristic content/index/archive scan; existing history is preserved. Values of private identifiers and author emails are deliberately omitted."}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"index_files": len(records), "archives": len(archives), "findings": len(findings), "existing_history_ordinary_email_count": len(ordinary)}))
    if findings:
        print(json.dumps(findings, ensure_ascii=False, indent=2))
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
