"""Export the bundled skill with a local runtime binding; never overwrite a skill."""
import json
from pathlib import Path
import shutil
import sys


def install(destination: str, *, java_home: str | None = None, cache_dir: str | None = None) -> Path:
    source = Path(__file__).resolve().parent / "skill_bundle"
    target = Path(destination).expanduser().resolve() / "codetracker-investigate"
    if target.exists() or target.is_symlink():
        raise ValueError("Skill directory already exists; preserve local customizations before updating it.")
    shutil.copytree(source, target)
    runtime = {"python": sys.executable}
    if java_home:
        runtime["java_home"] = str(Path(java_home).expanduser().resolve())
    if cache_dir:
        runtime["cache_dir"] = str(Path(cache_dir).expanduser().resolve())
    (target / "runtime.local.json").write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
    return target
