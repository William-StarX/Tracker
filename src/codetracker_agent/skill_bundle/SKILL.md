---
name: codetracker-investigate
description: Proactively survey unfamiliar existing Java projects before planning and trace relevant committed methods, variables or blocks during bug investigation and historical review. Use for 旧项目接管, 项目梳理 and 缺陷调查 throughout a chat or project, without requiring the user to name TraceTrail.
---

# TraceTrail investigation checkpoints

Apply this workflow throughout the active project. Before planning work in an unfamiliar existing Java project, use `overview` to identify modules, entry/test hints and relevant files. Skip a new overview when current relevant structure is already established, or when the user has supplied a specific history target. During a bug or history investigation, trace the relevant committed element when its evolution can inform the diagnosis. Refresh a needed overview after relevant module, dependency, entry-point or test-layout changes.

Use connected TraceTrail `overview`/`trace` tools when available. Otherwise use this skill's launcher with the installed SDK:

```sh
python "<skill-dir>/scripts/run.py" describe
python "<skill-dir>/scripts/run.py" call --request request.json
```

The launcher reads optional `runtime.local.json` created by `install-skill`; keep its machine-specific Python/Java/cache paths local. Without it, the current Python must have `codetracker-agent` installed. Overview needs no Java or Git. Use `doctor` for setup problems and `prepare` once when environment setup is within the requested task; otherwise report unavailability explicitly.

Example requests, with the user's real project and target substituted:

```json
{"operation":"overview","repo":"PROJECT"}
```

```json
{"operation":"trace","repo":"PROJECT","commit":"COMMIT_SHA","file":"src/main/java/example/Service.java","line":42,"name":"variableName"}
```

For methods or blocks, omit `name` unless needed. Read the file at the requested commit to choose its line; the editor buffer may include uncommitted edits. Verify `evidence.selected_element` and the resolved commit before interpreting history. Never silently replace a missing or unsupported target with another element. Trace relevant elements only; do not scan all histories or rerun after every message.

Keep complete reports outside the target project. The task handoff should retain report references, exact commits or inspected-content fingerprint, selected elements, status/coverage and observed facts separately from hypotheses. On resume, confirm the target and version before reusing the report. A worktree edit can make an overview stale even if HEAD is unchanged. Fixed-commit history still describes that commit, not the current uncommitted code; engine version, query limits and available history also matter.

Overview is a custom scanner; historical tracking uses CodeTracker. Structural hints are not a verified call graph, and a recent change is not proof of defect causation. Preserve `partial`, truncated output and missing history; use relevant source and tests to verify hypotheses. A separately available change-review tool can check the resulting patch, but this skill remains independently usable.

These are proactive agent instructions. A host requiring deterministic checkpoint execution must bind its workflow events to these tools and check the results; keeping a service online alone does not schedule analysis.
