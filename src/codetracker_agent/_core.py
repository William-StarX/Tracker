"""Component dispatch and complete evidence envelope, interface version 1.0."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent / "_vendor"
INTERFACE_VERSION = "1.0"
PARAMETERS = {'repo': {'type': 'string',
          'description': 'Local project/repository directory.'},
 'commit': {'type': 'string',
            'description': 'History start revision; default HEAD.'},
 'file': {'type': 'string',
          'description': 'Repository-relative Java file at the selected '
                         'commit.'},
 'line': {'type': 'integer',
          'minimum': 1,
          'description': 'One-based line at that commit.'},
 'name': {'type': 'string',
          'description': 'Method or local-variable name; specify for variable '
                         'tracking.'},
 'format': {'type': 'string',
            'enum': ['full', 'compact'],
            'description': 'Default full. Compact requires output for complete '
                           'evidence.'},
 'output': {'type': 'string',
            'description': 'New full-report file outside the analyzed project; '
                           'existing paths are rejected.'},
 'timeout': {'type': 'integer',
             'minimum': 1,
             'description': 'Component engine/preparation timeout in seconds, '
                            'not a whole-call deadline.'},
 'memory_mb': {'type': 'integer',
               'minimum': 256,
               'maximum': 32768,
               'description': 'Java heap ceiling; default 2048. Not a '
                              'process-tree RAM limit.'},
 'max_files': {'type': 'integer', 'minimum': 1, 'maximum': 100000},
 'max_total_bytes': {'type': 'integer', 'minimum': 1},
 'max_events': {'type': 'integer',
                'minimum': 1,
                'maximum': 1000,
                'description': 'Returned history-event limit, not a '
                               'traversal-work limit; default 100.'},
 'max_source_bytes': {'type': 'integer', 'minimum': 1},
 'max_commits': {'type': 'integer', 'minimum': 0, 'maximum': 5000},
 'max_file_bytes': {'type': 'integer', 'minimum': 1024, 'maximum': 10000000}}
OPERATIONS = {'overview': {'description': "Inventory an existing project's modules, "
                             'dependencies, entry/test hints and Git activity. '
                             'Requires no Java engine; not a verified call '
                             'graph.',
              'required': ['repo'],
              'optional': ['max_files',
                           'max_commits',
                           'max_file_bytes',
                           'max_total_bytes',
                           'output',
                           'format'],
              'component': 'trace',
              'script': 'overview.py',
              'command': None},
 'trace': {'description': 'Trace a Java method, local variable or block in '
                          'committed history. Inspect selected_element; use '
                          'name for a specific variable.',
           'required': ['repo', 'file', 'line'],
           'optional': ['commit',
                        'name',
                        'max_events',
                        'max_source_bytes',
                        'timeout',
                        'memory_mb',
                        'output',
                        'format'],
           'component': 'trace',
           'script': 'trace.py',
           'command': 'trace'},
 'doctor': {'description': 'Inspect runtime and engine readiness. A successful '
                           'diagnosis may still report prepared=false.',
            'required': [],
            'optional': [],
            'command': 'doctor',
            'component': 'trace',
            'script': 'trace.py'},
 'prepare': {'description': 'Explicitly prepare one engine. May download '
                            'pinned build dependencies; does not build the '
                            'analyzed project.',
             'required': [],
             'optional': ['timeout'],
             'command': 'prepare',
             'component': 'trace',
             'script': 'trace.py'}}
COMPONENTS = {'trace': 'codetracker-investigate'}

def child_environment(operation: str) -> dict[str, str]:
    # Forward runtime necessities, not model credentials or HTTP bearer tokens.
    names = {"PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT", "WINDIR",
             "SYSTEMDRIVE", "PATHEXT", "COMSPEC", "TEMP", "TMP", "TMPDIR", "JAVA_HOME", "JAVA_ANALYSIS_CACHE"}
    if operation == "prepare":
        names.update({"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR"})
    return {key: value for key, value in os.environ.items() if key.upper() in names}


def input_schema(operation: str) -> dict:
    spec = OPERATIONS[operation]
    properties = {key: copy.deepcopy(PARAMETERS[key]) for key in spec["required"] + spec["optional"]}
    for item in properties.values():
        if item["type"] == "string":
            item["minLength"] = 1
    if operation == "overview":
        properties["max_total_bytes"].update(minimum=1024, maximum=200000000)
    return {"type": "object", "properties": properties, "required": list(spec["required"]), "additionalProperties": False}


def describe() -> dict:
    """JSON Schema tool descriptions, without starting engines or reading projects."""
    return {"interface_version": INTERFACE_VERSION, "tools": [
        {"name": name, "description": spec["description"], "inputSchema": input_schema(name)}
        for name, spec in OPERATIONS.items()],
        "calling_convention": {"python": "Client().call(tool_name, **arguments)",
                               "stdin": "One object: {\"operation\": tool_name, **arguments}"},
        "response_schema": {
            "type": "object", "required": ["interface_version", "operation", "status", "error", "result", "process"],
            "additionalProperties": False, "properties": {
                "interface_version": {"const": INTERFACE_VERSION}, "operation": {"type": ["string", "null"]},
                "status": {"enum": ["ok", "partial", "error"]},
                "error": {"anyOf": [{"type": "null"}, {"type": "object", "required": ["code", "message"],
                    "additionalProperties": False, "properties": {"code": {"type": "string"}, "message": {"type": "string"}}}]},
                "result": {"type": ["object", "null"], "description": "Unmodified component report, including all evidence and provenance fields."},
                "process": {"type": ["object", "null"], "properties": {
                    "exit_code": {"type": "integer"}, "stderr": {"type": "string"}, "stdout_tail": {"type": "string"}}}}}}


def failure(operation, code: str, message: str, *, result=None, process=None) -> dict:
    return {"interface_version": INTERFACE_VERSION, "operation": operation if isinstance(operation, str) else None,
            "status": "error", "error": {"code": code, "message": message}, "result": result, "process": process}


def invoke(operation: str, **arguments) -> dict:
    """Run one independent component; preserve its complete response inside result."""
    try:
        if not isinstance(operation, str) or operation not in OPERATIONS:
            raise ValueError("Unknown operation. Call describe() or --describe to list tools.")
        schema = input_schema(operation)
        missing = [key for key in schema["required"] if key not in arguments]
        unknown = sorted(set(arguments) - set(schema["properties"]))
        if missing or unknown:
            raise ValueError(f"Missing arguments: {missing}; unknown arguments: {unknown}.")
        for key, value in arguments.items():
            rule = schema["properties"][key]
            expected = {"string": str, "integer": int, "boolean": bool}[rule["type"]]
            if expected is int and isinstance(value, float) and value.is_integer():
                value = arguments[key] = int(value)
            if type(value) is not expected:
                raise ValueError(f"{key} must be {rule['type']}.")
            if isinstance(value, str) and (not value or "\0" in value):
                raise ValueError(f"{key} must be nonempty and contain no NUL characters.")
            if "enum" in rule and value not in rule["enum"]:
                raise ValueError(f"{key} must be one of {rule['enum']}.")
            if ("minimum" in rule and value < rule["minimum"]) or ("maximum" in rule and value > rule["maximum"]):
                raise ValueError(f"{key} is outside the documented bounds.")
        if arguments.get("format") == "compact" and not arguments.get("output"):
            raise ValueError("compact requires output so complete evidence is retained.")
        if arguments.get("output"):
            output = Path(arguments["output"]).expanduser()
            if output.exists() or output.is_symlink():
                raise ValueError("output already exists; choose a new report path.")
    except (ValueError, OSError) as exc:
        return failure(operation, "INVALID_ARGUMENT", str(exc))

    spec = OPERATIONS[operation]
    component = spec.get("component", arguments.get("component"))
    script = ROOT / "components" / COMPONENTS[component] / "scripts" / spec.get("script", "review.py" if component == "review" else "trace.py")
    command = [sys.executable, "-B", "-X", "utf8", str(script)]
    if spec["command"]:
        command.append(spec["command"])
    for name, value in arguments.items():
        if name == "component":
            continue
        option = "--" + name.replace("_", "-")
        if isinstance(value, bool):
            if value:
                command.append(option)
        else:
            command.append(option + "=" + str(value))
    try:
        completed = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, check=False, env=child_environment(operation))
    except OSError as exc:
        return failure(operation, "PROCESS_FAILED", str(exc))
    process = {"exit_code": completed.returncode, "stderr": completed.stderr.decode("utf-8", errors="replace")}
    try:
        raw = json.loads(completed.stdout)
        if not isinstance(raw, dict) or raw.get("status") not in {"ok", "partial", "error"}:
            raise ValueError("Expected a result object with status ok, partial or error.")
    except (ValueError, UnicodeError) as exc:
        process["stdout_tail"] = completed.stdout[-4000:].decode("utf-8", errors="replace")
        return failure(operation, "INVALID_COMPONENT_RESPONSE", str(exc), process=process)
    if raw["status"] == "error":
        error = raw.get("error", "Component reported an error; inspect result and process.stderr.")
        code = error.get("code", "COMPONENT_ERROR") if isinstance(error, dict) else "COMPONENT_ERROR"
        message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        return failure(operation, str(code), str(message), result=raw, process=process)
    if completed.returncode:
        return failure(operation, "PROCESS_FAILED", "Component exited unsuccessfully despite its JSON status.", result=raw, process=process)
    return {"interface_version": INTERFACE_VERSION, "operation": operation, "status": raw["status"],
            "error": None, "result": raw, "process": process}
