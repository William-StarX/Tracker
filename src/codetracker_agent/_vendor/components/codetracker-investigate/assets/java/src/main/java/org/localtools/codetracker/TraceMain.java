package org.localtools.codetracker;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.common.graph.EndpointPair;
import gr.uom.java.xmi.LocationInfo;
import org.codetracker.api.CodeElement;
import org.codetracker.api.CodeElementNotFoundException;
import org.codetracker.api.CodeTracker;
import org.codetracker.api.Edge;
import org.codetracker.api.History;
import org.codetracker.change.Change;
import org.codetracker.element.Block;
import org.codetracker.element.Method;
import org.codetracker.element.Variable;
import org.codetracker.util.CodeElementLocator;
import org.eclipse.jgit.lib.Repository;
import org.eclipse.jgit.storage.file.FileRepositoryBuilder;

import java.io.File;
import java.io.PrintStream;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Minimal local-only adapter; never calls CodeTracker's REST or remote helpers. */
public final class TraceMain {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String MERGE_LIMIT =
        "The upstream tracker uses first-parent-based traversal; complex merge histories may be incomplete.";

    private TraceMain() { }

    public static void main(String[] args) throws Exception {
        PrintStream resultStream = System.out;
        // The research library prints diagnostic progress to System.out.
        // Keep the process stdout a single machine-readable JSON object.
        System.setOut(System.err);
        Map<String, Object> result;
        long start = System.nanoTime();
        try {
            result = execute(parseArgs(args));
        } catch (InputException e) {
            result = map("status", "error", "error", map("code", e.code, "message", e.getMessage()));
        } catch (CodeElementNotFoundException e) {
            result = map("status", "error", "error", map("code", "ELEMENT_NOT_FOUND", "message", e.getMessage()));
        } catch (Exception e) {
            e.printStackTrace(System.err);
            result = map("status", "error", "error", map(
                "code", "TRACKING_FAILED",
                "message", e.getClass().getSimpleName() + ": " + clip(String.valueOf(e.getMessage()), 1500)));
        }
        result.put("engine", map("name", "CodeTracker", "version", "3.0", "refactoringminer_version", "3.0.11",
                "adapter_version", "1.2.0", "edit_distance", "exact-utf16-affix-trimmed",
                "core_overrides", List.of("StringDistance", "ReplacementUtil.keepReservedTokens")));
        result.put("engine_elapsed_ms", (System.nanoTime() - start) / 1_000_000L);
        resultStream.println(JSON.writeValueAsString(result));
    }

    private static Map<String, String> parseArgs(String[] args) throws InputException {
        Map<String, String> values = new LinkedHashMap<>();
        Set<String> allowed = Set.of("--repo", "--git-dir", "--commit", "--file", "--line", "--max-events", "--name");
        if (args.length % 2 != 0) {
            throw new InputException("INVALID_ARGUMENT", "Arguments must be flag/value pairs.");
        }
        for (int i = 0; i < args.length; i += 2) {
            if (!allowed.contains(args[i]) || values.put(args[i], args[i + 1]) != null) {
                throw new InputException("INVALID_ARGUMENT", "Unknown or duplicate argument: " + args[i]);
            }
        }
        for (String name : List.of("--repo", "--git-dir", "--commit", "--file", "--line")) {
            if (!values.containsKey(name) || values.get(name).isBlank()) {
                throw new InputException("INVALID_ARGUMENT", "Missing argument: " + name);
            }
        }
        return values;
    }

    private static Map<String, Object> execute(Map<String, String> args) throws Exception {
        String commit = args.get("--commit");
        String path = args.get("--file");
        if (!commit.matches("[0-9a-fA-F]{40}")) {
            throw new InputException("UNSUPPORTED_OBJECT_FORMAT", "Provide a resolved SHA-1 commit identifier.");
        }
        if (path.startsWith("/") || path.contains("\\") || path.contains(":") ||
            List.of(path.split("/")).contains("..") || !path.endsWith(".java")) {
            throw new InputException("INVALID_PATH", "Provide a repository-relative Java source path.");
        }
        int line = positiveInt(args.get("--line"), "line", Integer.MAX_VALUE);
        int maxEvents = positiveInt(args.getOrDefault("--max-events", "100"), "max-events", 1000);
        File gitDir = new File(args.get("--git-dir"));
        if (!gitDir.isDirectory()) {
            throw new InputException("INVALID_REPOSITORY", "The local Git directory does not exist.");
        }
        List<String> warnings = new ArrayList<>();
        List<String> limitations = new ArrayList<>(List.of(
            MERGE_LIMIT,
            "History is evidence of changes, not a determination of defect causality or developer intent.",
            "Code locations refer to the requested committed revision, not the current worktree.",
            "max_events limits returned events; the upstream tracking computation is bounded by the outer timeout and JVM heap."));

        try (Repository repository = new FileRepositoryBuilder()
                .setGitDir(gitDir)
                .setWorkTree(new File(args.get("--repo")))
                .setMustExist(true)
                .build()) {
            CodeElement selected = new CodeElementLocator(repository, commit, path, args.get("--name"), line).locate();
            if (selected == null) {
                throw new InputException("ELEMENT_NOT_FOUND", "No code element was located at this committed source line.");
            }
            String requestedName = args.get("--name");
            if (requestedName != null && !(
                    selected instanceof Method method && requestedName.equals(method.getUmlOperation().getName()) ||
                    selected instanceof Variable variable && requestedName.equals(variable.getVariableDeclaration().getVariableName()))) {
                throw new InputException("ELEMENT_NOT_FOUND", "No method or local variable named " +
                    clip(requestedName, 200) + " was selected at this committed line. The upstream locator resolved a " +
                    selected.getClass().getSimpleName() + "; its history was not substituted.");
            }
            History<? extends CodeElement> history = track(repository, commit, path, selected);
            List<? extends History.HistoryInfo<? extends CodeElement>> entries = history.getHistoryInfoList();
            // Preserve upstream event relationships and expose a deterministic display order.
            List<History.HistoryInfo<? extends CodeElement>> ordered = new ArrayList<>(entries);
            ordered.sort(Comparator
                .comparingLong((History.HistoryInfo<? extends CodeElement> h) -> h.getCommitTime()).reversed()
                .thenComparing(History.HistoryInfo::getCommitId)
                .thenComparing(h -> h.getElementAfter() == null ? "" : h.getElementAfter().getIdentifier()));
            List<Map<String, Object>> events = new ArrayList<>();
            int count = Math.min(maxEvents, ordered.size());
            for (int i = 0; i < count; i++) {
                History.HistoryInfo<? extends CodeElement> info = ordered.get(i);
                List<Map<String, Object>> changes = new ArrayList<>();
                for (Change change : info.getChangeList()) {
                    changes.add(map("type", change.getType().getTitle(), "description", clip(change.toString(), 4000)));
                }
                changes.sort(Comparator.comparing(change -> String.valueOf(change.get("type")) + change.get("description")));
                events.add(map(
                    "commit", info.getCommitId(),
                    "parent_commit", realCommit(info.getParentCommitId()),
                    "commit_time", Instant.ofEpochSecond(info.getCommitTime()).toString(),
                    "commit_time_epoch", info.getCommitTime(),
                    "before", element(info.getElementBefore()),
                    "after", element(info.getElementAfter()),
                    "changes", changes));
            }
            boolean truncated = ordered.size() > maxEvents;
            Map<String, Object> lineage = lineage(history, maxEvents);
            boolean lineageTruncated = Boolean.TRUE.equals(lineage.get("truncated"));
            if (truncated) {
                warnings.add("Event output truncated: returned " + count + " of " + ordered.size() + " events.");
            }
            if (ordered.isEmpty()) {
                warnings.add("No history events were returned. This is not proof that the element has never changed.");
            }
            if (lineageTruncated) {
                warnings.add("Lineage edge output was truncated; increase max-events to inspect the remaining mappings.");
            }
            if (!(selected instanceof Block)) {
                warnings.add("The selected line resolved to a " + selected.getClass().getSimpleName() +
                    "; that element's history was tracked. Inspect selected_element to confirm the intended scope.");
            }
            return map(
                "status", truncated || lineageTruncated ? "partial" : "ok",
                "evidence", map(
                    "selected_element", element(selected),
                    "history", events,
                    "event_count", ordered.size(),
                    "returned_event_count", count,
                    "events_truncated", truncated,
                    "lineage_edges", lineage.get("edges"),
                    "lineage_edge_count", lineage.get("count"),
                    "lineage_edges_truncated", lineageTruncated,
                    "display_order", "commit_time_descending; relationships are specified by parent_commit",
                    "analysed_commits", history.getHistoryReport() == null ? null : history.getHistoryReport().getAnalysedCommits()),
                "warnings", warnings,
                "limitations", limitations);
        }
    }

    private static <T extends CodeElement> Map<String, Object> lineage(History<T> history, int limit) {
        List<Map<String, Object>> edges = new ArrayList<>();
        if (history.getGraph() == null) return map("edges", edges, "count", 0, "truncated", false);
        List<EndpointPair<T>> pairs = new ArrayList<>(history.getGraph().getEdges());
        pairs.sort(Comparator.comparing((EndpointPair<T> pair) -> pair.target().getVersion().getTime()).reversed()
            .thenComparing(pair -> pair.target().getIdentifier()));
        for (EndpointPair<T> pair : pairs.subList(0, Math.min(limit, pairs.size()))) {
            Edge value = history.getGraph().getEdgeValue(pair).orElse(null);
            edges.add(map(
                "before", element(pair.source()), "after", element(pair.target()),
                "upstream_change_type", value == null ? null : value.getType().getTitle(),
                "note", "Tracked element correspondence; a no-change edge can connect renamed or moved containers."));
        }
        return map("edges", edges, "count", pairs.size(), "truncated", pairs.size() > limit);
    }

    private static History<? extends CodeElement> track(Repository repo, String commit, String path,
                                                        CodeElement selected) throws Exception {
        if (selected instanceof Block block) {
            return CodeTracker.blockTracker().repository(repo).startCommitId(commit).filePath(path)
                .methodName(block.getOperation().getName())
                .methodDeclarationLineNumber(block.getOperation().getLocationInfo().getStartLine())
                .codeElementType(block.getLocation().getCodeElementType())
                .blockStartLineNumber(block.getLocation().getStartLine())
                .blockEndLineNumber(block.getLocation().getEndLine())
                .build().track();
        }
        if (selected instanceof Method method) {
            return CodeTracker.methodTracker().repository(repo).startCommitId(commit).filePath(path)
                .methodName(method.getUmlOperation().getName())
                .methodDeclarationLineNumber(method.getLocation().getStartLine())
                .build().track();
        }
        if (selected instanceof Variable variable) {
            return CodeTracker.variableTracker().repository(repo).startCommitId(commit).filePath(path)
                .methodName(variable.getOperation().getName())
                .methodDeclarationLineNumber(variable.getOperation().getLocationInfo().getStartLine())
                .variableName(variable.getVariableDeclaration().getVariableName())
                .variableDeclarationLineNumber(variable.getLocation().getStartLine())
                .build().track();
        }
        throw new InputException("UNSUPPORTED_ELEMENT", "The selected line resolved to " +
            selected.getClass().getSimpleName() + ". This adapter supports Block, Method and Variable. " +
            "Select a method declaration or a control-flow statement in the requested committed file.");
    }

    private static Map<String, Object> element(CodeElement element) {
        if (element == null) return null;
        LocationInfo location = element.getLocation();
        return map(
            "kind", element.getClass().getSimpleName(),
            "name", clip(element.getName(), 4000),
            "file", element.getFilePath(),
            "start_line", location == null ? null : location.getStartLine(),
            "end_line", location == null ? null : location.getEndLine(),
            "ast_type", location == null ? null : location.getCodeElementType().name(),
            "commit", element.getVersion() == null ? null : realCommit(element.getVersion().getId()),
            "virtual_origin", element.getVersion() != null && "0".equals(element.getVersion().getId()),
            "added", element.isAdded(),
            "removed", element.isRemoved());
    }

    private static String realCommit(String value) {
        return "0".equals(value) ? null : value;
    }

    private static int positiveInt(String value, String name, int max) throws InputException {
        try {
            int parsed = Integer.parseInt(value);
            if (parsed > 0 && parsed <= max) return parsed;
        } catch (NumberFormatException ignored) { }
        throw new InputException("INVALID_ARGUMENT", name + " must be between 1 and " + max + ".");
    }

    private static String clip(String value, int max) {
        if (value == null || value.length() <= max) return value;
        return value.substring(0, max) + " [truncated]";
    }

    private static Map<String, Object> map(Object... values) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (int i = 0; i < values.length; i += 2) result.put((String) values[i], values[i + 1]);
        return result;
    }

    private static final class InputException extends Exception {
        final String code;
        InputException(String code, String message) { super(message); this.code = code; }
    }
}
