"""Run the installed SDK using an optional machine-local runtime binding."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    binding = Path(__file__).resolve().parents[1] / "runtime.local.json"
    config = json.loads(binding.read_text(encoding="utf-8")) if binding.exists() else {}
    environment = os.environ.copy()
    for key, variable in (("java_home", "JAVA_HOME"), ("cache_dir", "JAVA_ANALYSIS_CACHE")):
        if config.get(key):
            environment[variable] = config[key]
    return subprocess.run([config.get("python", sys.executable), "-m", "codetracker_agent", *sys.argv[1:]],
                          env=environment).returncode


if __name__ == "__main__":
    raise SystemExit(main())
