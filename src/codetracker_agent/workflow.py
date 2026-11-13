"""Portable guidance for agent checkpoints; the host owns task scheduling."""

INSTRUCTIONS = (
    "Use TraceTrail proactively at relevant project checkpoints. Run overview before planning work in an "
    "unfamiliar existing Java project. During bug investigation or historical review, trace the relevant "
    "committed method, variable or block before drawing conclusions about its evolution. Confirm selected_element "
    "and resolved commit; editor-buffer line numbers can differ. Preserve partial/error status. "
    "Tool availability does not prove a checkpoint ran.\n\n"
    "Follow these checkpoints throughout the project, without requiring the user to name this tool again. "
    "Skip overview for a task whose relevant structure is already established; go directly to a known trace target. "
    "Refresh a needed overview after relevant module, dependency, entry-point or test-layout changes. "
    "Trace only relevant elements, not every file or every conversation turn. Trace reads committed history, "
    "not uncommitted edits; resolve locations in the selected revision and never silently change the target. "
    "Record resolved commits, selected elements, report references, coverage and hypotheses in the task handoff. "
    "On resume, verify that the recorded target and worktree evidence still apply. A changed worktree invalidates "
    "claims that a previous overview describes current content; fixed-commit history remains evidence about that "
    "commit, not newer code. Engine versions, limits and available history affect reuse. Keep complete reports "
    "outside the target project. Distinguish observed changes from inferred causes; recent changes alone do not "
    "prove a defect's origin. The host must implement an explicit checkpoint gate if it requires deterministic "
    "enforcement; these instructions do not schedule work themselves."
)

CHECKPOINTS = [
    {"phase": "existing_project_onboarding", "tools": ["overview"],
     "when": "Planning work in an unfamiliar existing Java project without current structural evidence."},
    {"phase": "bug_or_history_investigation", "tools": ["trace"],
     "when": "A relevant committed method, variable or block is identified and its history informs the investigation."},
    {"phase": "project_structure_changed", "tools": ["overview"],
     "when": "Relevant structure changed and a subsequent task depends on the previous overview."},
]
