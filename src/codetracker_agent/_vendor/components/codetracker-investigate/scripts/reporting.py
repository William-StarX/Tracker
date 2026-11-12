"""Optional bounded evidence view. Full reports remain the default and the saved artifact."""
from __future__ import annotations

import json
from pathlib import Path


def render_result(result: dict, format: str = "full", saved_output: str | None = None) -> str:
    if format != "compact" or result.get("status") == "error":
        return json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    omitted = []

    def shrink(value, path):
        if path in {"/evidence/unified_diff", "/evidence/lineage_edges"} and value:
            omitted.append({"path": path,
                            "original_characters" if isinstance(value, str) else "original_count": len(value)})
            return None
        if isinstance(value, dict):
            return {key: shrink(item, path + "/" + key.replace("~", "~0").replace("/", "~1"))
                    for key, item in value.items()}
        if isinstance(value, list):
            if len(value) > 8:
                omitted.append({"path": path, "original_count": len(value), "returned_count": 8})
            return [shrink(item, path + "/" + str(index)) for index, item in enumerate(value[:8])]
        if isinstance(value, str) and len(value) > 1000:
            omitted.append({"path": path, "original_characters": len(value), "returned_characters": 1000})
            return value[:1000]
        return value

    view = dict(result)
    view["evidence"] = shrink(result.get("evidence", {}), "/evidence")
    view["view"] = {
        "format": "compact",
        "full_report": str(Path(saved_output).expanduser().resolve()) if saved_output else None,
        "omitted": omitted,
        "note": "Display omissions only; read full_report before whole-scope conclusions."
                if saved_output else "Use --output to retain full evidence, or rerun with --format full.",
    }
    return json.dumps(view, ensure_ascii=False, indent=2) + "\n"
