"""Isolated, pinned Java bridge runtime. No project builds or remote Git access."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit, unquote
import xml.etree.ElementTree as ET

MAVEN_VERSION = "3.9.11"
MAVEN_URL = (
    "https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/"
    f"{MAVEN_VERSION}/apache-maven-{MAVEN_VERSION}-bin.tar.gz"
)
MAVEN_SHA512 = (
    "bcfe4fe305c962ace56ac7b5fc7a08b87d5abd8b7e89027ab251069faebee516b0"
    "ded8961445d6d91ec1985dfe30f8153268843c89aa392733d1a3ec956c9978"
)
MAX_JSON_BYTES = 32 * 1024 * 1024


def cache_root() -> Path:
    value = os.environ.get("JAVA_ANALYSIS_CACHE")
    return Path(value).expanduser().resolve() if value else Path.home() / ".cache" / "java-analysis-components"


def temporary_root() -> Path:
    directory = cache_root() / "tmp"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def java_tool(name: str) -> str | None:
    suffix = ".exe" if os.name == "nt" else ""
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / (name + suffix)
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


def _version(command: str | None) -> tuple[str, int | None]:
    if not command:
        return "not found", None
    try:
        prefix = "-J" if Path(command).stem.lower() == "javac" else ""
        proc = subprocess.run([command, prefix + "-Xms16m", prefix + "-Xmx64m", "-version"],
                              capture_output=True, text=True, timeout=15)
        value = (proc.stdout + proc.stderr).strip()
        match = re.search(r'(?:version\s+"|javac\s+)(\d+)(?:\.(\d+))?', value)
        major = int(match.group(1)) if match and proc.returncode == 0 else None
        if major == 1 and match.group(2):
            major = int(match.group(2))
        return value.splitlines()[0] if value else "no version output", major
    except (OSError, subprocess.SubprocessError) as exc:
        return str(exc), None


def _compiler_version() -> tuple[str, int | None, bool]:
    javac = java_tool("javac")
    if javac:
        text, major = _version(javac)
        return text, major, False
    java = java_tool("java")
    if java:
        try:
            result = subprocess.run([java, "-Xms16m", "-Xmx64m", "-m", "jdk.compiler/com.sun.tools.javac.Main", "-version"], capture_output=True, text=True, timeout=15)
            text = (result.stdout + result.stderr).strip()
            match = re.search(r"javac\s+(\d+)", text)
            if result.returncode == 0 and match:
                return text, int(match.group(1)), True
        except (OSError, subprocess.SubprocessError):
            pass
    return "not found", None, False


def _java_major(command: str | None) -> int | None:
    """A JDK/JRE release file avoids a second JVM just to launch the real JVM."""
    if command:
        try:
            release = Path(command).resolve().parent.parent / "release"
            match = re.search(r'^JAVA_VERSION="(\d+)(?:\.(\d+))?', release.read_text(encoding="utf-8"), re.MULTILINE)
            if match:
                return int(match.group(2)) if match.group(1) == "1" else int(match.group(1))
        except (OSError, UnicodeError):
            pass
    return _version(command)[1]


def _source_id(skill_dir: Path) -> str:
    source = skill_dir / "assets" / "java"
    if not (source / "pom.xml").is_file():
        raise RuntimeError("Bundled Java bridge source is missing (assets/java/pom.xml).")
    digest = hashlib.sha256()
    files = sorted(p for p in source.rglob("*") if p.is_file() and "target" not in p.relative_to(source).parts)
    for path in files:
        digest.update(path.relative_to(source).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _engine_dir(skill_dir: Path, component: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]+", component):
        raise RuntimeError("Invalid component name.")
    return cache_root() / "engines" / component / _source_id(skill_dir)[:20]


def doctor(skill_dir: str | Path, component: str) -> dict:
    skill_dir = Path(skill_dir).resolve()
    java, javac = java_tool("java"), java_tool("javac")
    version, major = _version(java)
    compiler_version, compiler_major, via_module = _compiler_version()
    jar = _engine_dir(skill_dir, component) / "engine.jar"
    return {
        "schema_version": "1.0", "component": component, "operation": "doctor",
        "status": "ok" if major and major >= 17 and (jar.is_file() or (compiler_major and compiler_major >= 17)) else "error",
        "java": {"path": java, "version": version, "major": major},
        "javac": {"path": javac, "version": compiler_version, "major": compiler_major, "via_jdk_module": via_module},
        "engine": {"prepared": jar.is_file(), "path": str(jar), "source_sha256": _source_id(skill_dir)},
        "maven": {"bootstrap_version": MAVEN_VERSION, "system_path": shutil.which("mvn")},
        "cache": str(cache_root()),
        "requirements": ["JDK 17+ for prepare; Java 17+ to run a prepared engine", "Network only for explicit prepare", "Git for repository operations"],
    }


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.wait()


def _run(command: list[str], *, cwd: Path, timeout: float, max_bytes: int = MAX_JSON_BYTES) -> tuple[int, str, str]:
    if timeout <= 0:
        raise RuntimeError("timeout must be positive")
    with tempfile.TemporaryFile(dir=temporary_root()) as out, tempfile.TemporaryFile(dir=temporary_root()) as err:
        options = {"start_new_session": True} if os.name != "nt" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        try:
            proc = subprocess.Popen(command, cwd=str(cwd), stdout=out, stderr=err, stdin=subprocess.DEVNULL, **options)
        except OSError as exc:
            raise RuntimeError(f"Cannot start Java tool: {exc}") from exc
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _terminate(proc)
            raise RuntimeError(f"Java operation timed out after {timeout:g} seconds; no analysis result is available.") from exc
        out.seek(0, os.SEEK_END)
        if out.tell() > max_bytes:
            raise RuntimeError(f"Java output exceeded the {max_bytes} byte limit; narrow the target.")
        out.seek(0)
        stdout = out.read().decode("utf-8", "replace")
        err.seek(0, os.SEEK_END)
        size = err.tell()
        err.seek(max(0, size - 16000))
        stderr = err.read().decode("utf-8", "replace")
        return proc.returncode, stdout, stderr


def _maven_home() -> Path:
    root = cache_root() / "toolchains"
    home = root / f"apache-maven-{MAVEN_VERSION}"
    if (home / "bin" / "m2.conf").is_file():
        return home
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="maven-download-", dir=str(root)) as name:
        work = Path(name)
        archive = work / "maven.tar.gz"
        digest = hashlib.sha512()
        request = urllib.request.Request(MAVEN_URL, headers={"User-Agent": "JavaAnalysisComponents/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=45) as response, archive.open("wb") as dest:
                while block := response.read(1024 * 1024):
                    digest.update(block)
                    dest.write(block)
        except OSError as exc:
            raise RuntimeError(f"Maven download failed: {exc}") from exc
        if digest.hexdigest() != MAVEN_SHA512:
            raise RuntimeError("Maven archive checksum mismatch; refusing to use it.")
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar:
                relative = Path(member.name)
                if relative.is_absolute() or ".." in relative.parts or not (member.isfile() or member.isdir()):
                    raise RuntimeError("Unexpected path or link in Maven archive.")
                target = work / relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = tar.extractfile(member)
                    if source is None:
                        raise RuntimeError("Unreadable file in Maven archive.")
                    with source, target.open("wb") as dest:
                        shutil.copyfileobj(source, dest)
        try:
            (work / home.name).rename(home)
        except OSError:
            if not (home / "bin" / "m2.conf").is_file():
                raise
    return home


def _maven_settings(work: Path) -> Path:
    """Honor the process's configured proxy without exposing it in arguments/logs."""
    settings = ET.Element("settings", xmlns="http://maven.apache.org/SETTINGS/1.0.0")
    configured = urllib.request.getproxies()
    entries = ET.SubElement(settings, "proxies")
    bypass = configured.get("no", "")
    bypass_hosts = [value.strip().lstrip(".") for value in bypass.split(",") if value.strip() and "/" not in value]
    for protocol in ("http", "https"):
        value = configured.get(protocol)
        if not value:
            continue
        proxy_url = urlsplit(value)
        if proxy_url.scheme not in {"http", "https"} or not proxy_url.hostname:
            raise RuntimeError("The configured Maven proxy must use an HTTP(S) URL.")
        proxy = ET.SubElement(entries, "proxy")
        fields = {"id": "environment-" + protocol, "active": "true", "protocol": protocol,
                  "host": proxy_url.hostname, "port": str(proxy_url.port or (443 if proxy_url.scheme == "https" else 80))}
        if bypass_hosts:
            fields["nonProxyHosts"] = "|".join(bypass_hosts)
        if proxy_url.username:
            fields["username"] = unquote(proxy_url.username)
        if proxy_url.password:
            fields["password"] = unquote(proxy_url.password)
        for key, text in fields.items():
            ET.SubElement(proxy, key).text = text
    path = work / "maven-settings.xml"
    path.write_bytes(ET.tostring(settings, encoding="utf-8", xml_declaration=True))
    path.chmod(0o600)
    return path


def prepare_engine(skill_dir: str | Path, component: str, timeout: float = 300) -> str:
    skill_dir = Path(skill_dir).resolve()
    engine_dir = _engine_dir(skill_dir, component)
    jar = engine_dir / "engine.jar"
    if jar.is_file():
        return str(jar)
    java, javac = java_tool("java"), java_tool("javac")
    if (_version(java)[1] or 0) < 17 or (_compiler_version()[1] or 0) < 17:
        raise RuntimeError("prepare requires JDK 17+ (both java and javac). Set JAVA_HOME to your JDK.")
    engine_dir.mkdir(parents=True, exist_ok=True)
    lock = engine_dir / ".prepare-lock"
    deadline = time.monotonic() + timeout
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if jar.is_file():
                return str(jar)
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Another prepare is running or left a lock at {lock}. Check that process before retrying.")
            time.sleep(0.2)
    try:
        if jar.is_file():
            return str(jar)
        maven = _maven_home()
        launcher = sorted((maven / "boot").glob("plexus-classworlds-*.jar"))
        if len(launcher) != 1:
            raise RuntimeError("Maven bootstrap launcher is missing.")
        with tempfile.TemporaryDirectory(prefix="build-", dir=str(engine_dir)) as name:
            work = Path(name)
            shutil.copytree(skill_dir / "assets" / "java", work, dirs_exist_ok=True, ignore=shutil.ignore_patterns("target", "*.class"))
            settings = _maven_settings(work)
            command = [
                java, "-XX:-UsePerfData", "-Xms32m", "-Xmx512m", f"-Dmaven.home={maven}", f"-Dclassworlds.conf={maven / 'bin' / 'm2.conf'}",
                f"-Dmaven.multiModuleProjectDirectory={work}", "-classpath", str(launcher[0]),
                "org.codehaus.plexus.classworlds.launcher.Launcher", "-B", "-ntp", "-U", "-s", str(settings),
                f"-Dmaven.repo.local={cache_root() / 'm2'}", "-DskipTests", "package",
            ]
            remaining = max(1, deadline - time.monotonic())
            code, stdout, stderr = _run(command, cwd=work, timeout=remaining)
            if code or not (work / "target" / "engine.jar").is_file():
                raise RuntimeError("Java bridge build failed:\n" + (stdout + "\n" + stderr)[-18000:])
            shutil.copy2(work / "target" / "engine.jar", engine_dir / "engine.jar.tmp")
            (engine_dir / "engine.jar.tmp").replace(jar)
            (engine_dir / "build.json").write_text(json.dumps({
                "component": component, "source_sha256": _source_id(skill_dir), "maven": MAVEN_VERSION,
                "java": _version(java)[0], "jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
            }, indent=2), encoding="utf-8")
        return str(jar)
    finally:
        lock.rmdir()


def run_java_bridge(skill_dir: str | Path, component: str, args: list[str], timeout: float = 120, memory_mb: int = 2048) -> dict:
    skill_dir = Path(skill_dir).resolve()
    jar = _engine_dir(skill_dir, component) / "engine.jar"
    if not jar.is_file():
        raise RuntimeError("Java engine is not prepared. Run this component's prepare command first.")
    java = java_tool("java")
    if (_java_major(java) or 0) < 17:
        raise RuntimeError("Java 17+ is required to run the engine.")
    if not isinstance(memory_mb, int) or memory_mb < 256 or memory_mb > 32768:
        raise RuntimeError("memory_mb must be an integer between 256 and 32768.")
    command = [java, "-XX:-UsePerfData", "-Xms32m", f"-Xmx{memory_mb}m", "-Dfile.encoding=UTF-8", "-Djava.awt.headless=true", "-jar", str(jar)] + list(args)
    code, stdout, stderr = _run(command, cwd=jar.parent, timeout=timeout)
    if code:
        raise RuntimeError(f"Java engine exited with code {code}: " + (stderr or stdout)[-12000:])
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Java engine did not return one valid JSON object. " + stderr[-2000:]) from exc
    if not isinstance(result, dict):
        raise RuntimeError("Java engine returned an unexpected JSON value.")
    if stderr.strip():
        result.setdefault("runtime_diagnostics", stderr.strip()[-4000:])
    return result
