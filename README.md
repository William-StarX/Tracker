# CodeTracker Agent

[中文](#chinese) · [English](#english)

SDK / service **1.5.0** · Result interface **1.0** · CodeTracker **3.0**

<a id="chinese"></a>

## 中文

### 作用是什么

**帮助 Agent 接手已有 Java 项目，并用代码演变证据支持缺陷调查和历史审查。**

接手旧项目时，Agent 需要先找到模块、入口、依赖和测试；调查问题时，还需要知道某个方法、局部变量或控制结构何时、如何发生变化。本组件把这两项工作做成可独立调用的工具：

- **`overview`：项目概览。** 扫描当前工作区，返回结构和阅读线索，帮助 Agent 制定后续计划。这是本项目编写的扫描器。
- **`trace`：元素历史追踪。** 调用 CodeTracker 作者库，追踪指定提交中的方法、局部变量或代码块，返回相关提交、变化事件和前后代码位置。

例如：Agent 调查一处日期边界问题时，可先从概览找到相关模块和测试，再选择关键条件所在的已提交代码块，追踪它的演变，阅读相关提交并设计回归测试。**历史变化为原因假设提供证据；最近修改过某段代码，并不证明该修改导致了缺陷。**

### 能帮助 Agent 干什么

| 工作场景 | 组件提供什么 | Agent 如何使用 |
|---|---|---|
| Root Agent 接管陌生旧项目 | 模块与依赖声明、包结构、入口和测试线索，以及可用的 Git 活动信息 | 选择先读哪些文件、在哪里实现、应检查哪些测试 |
| 缺陷调查 | 相关方法、局部变量或控制结构的提交历史与变化事件 | 缩小历史阅读范围，提出并验证原因假设 |
| 理解复杂旧代码 | 元素前后位置、重命名或移动等演变线索 | 跟随代码沿革，结合提交说明解释当前实现 |
| 项目继续与 Agent 交接 | 目标提交、选中元素、完整报告与覆盖限制 | 复用可追溯的证据，避免把旧概览当作当前状态 |

适用于能调用本地进程、Python SDK、HTTP 或 MCP 工具的 Agent。统一接口让不同 Agent 直接获取结构化证据；Skill 和 MCP 指引告诉它们在相关项目阶段主动调用。

完成实现和测试后，可搭配独立的 [RefactoringMiner Agent](https://github.com/William-StarX/RefactoringMiner) 审查候选补丁。两个组件可以分别使用，不要求安装另一方的 SDK。

### 快速开始

基础 SDK 需要 **Python 3.11+**，没有第三方 Python 依赖。**仅运行项目概览不需要 Java，也不要求有 Git 历史**；有 Git 时可额外收集活动信息。下方从 GitHub 安装的命令需要 Git。

```sh
python -m pip install "git+https://github.com/William-StarX/Tracker.git"
```

```python
from codetracker_agent import Client

client = Client()
report = client.overview("/path/to/repo")
print(report["status"])
print(report["result"])  # 组件报告，包含证据、警告、限制和来源
```

历史追踪另需 **Java 17+ 和本地 Git 仓库历史**；首次准备引擎需要 **JDK 和网络**：

```sh
codetracker-agent doctor
codetracker-agent prepare
```

`prepare` 下载固定版本依赖并准备本组件引擎，不构建被分析项目；后续可复用缓存。可用 `JAVA_HOME` 指定 Java、`JAVA_ANALYSIS_CACHE` 指定缓存。

```python
from codetracker_agent import Client

report = Client().trace(
    "/path/to/repo",
    "src/main/java/example/Service.java",
    42,
    commit="HEAD",
)
print(report["status"])
print(report["result"])
```

请将示例路径、提交和行号替换为实际目标。**文件和行号必须来自所选提交，而非未提交的编辑器内容。** 检查返回证据中的 `selected_element` 是否为预期元素；必要时用 `name` 精确指定名称。需要可复查的调查时，记录实际解析出的提交 ID。

不使用 Python SDK 的 Agent 可以传入一个 JSON 请求：

```sh
codetracker-agent describe
codetracker-agent call --request request.json
```

`request.json`：

```json
{"operation":"overview","repo":"/path/to/repo"}
```

`call` 也接受标准输入。`describe` 返回 `overview`、`trace` 的参数、响应 Schema 和调用阶段指引。

### 接入 Agent，并在关键阶段主动调用

提供四种调用入口：Python `Client` / `HTTPClient`、JSON CLI、MCP stdio / Streamable HTTP，以及认证 HTTP API。HTTP/MCP 服务需安装可选依赖：

```sh
python -m pip install "codetracker-agent[server] @ git+https://github.com/William-StarX/Tracker.git"
codetracker-agent config codex --root /path/to/repo
```

`config` 只生成配置片段，需合并到宿主配置；另支持 `claude-code`、`claude-desktop`、`cursor`、`vscode`、`copilot`。MCP stdio 启动命令为 `codetracker-agent mcp --root /path/to/repo`。配置与协议启动已验证，各宿主的完整任务流程仍需按实际环境验证，详见 [Agent 接入](docs/AGENTS.md)。

支持 Skill 的宿主还可导出调用流程，例如在项目根目录执行：

```sh
codetracker-agent install-skill --destination .agents/skills
```

该目录是 Codex 项目示例，其他宿主应使用其发现目录。安装器不覆盖已有 Skill，可加 `--java-home`、`--cache-dir`；生成的 `runtime.local.json` 仅保留在本机。

已加载 Skill 或 MCP 指引的 Agent，应在以下阶段主动调用，无需用户每轮再次点名：

1. 接管陌生 Java 旧项目、制定计划前，用 `overview` 建立结构线索。
2. 缺陷或历史调查中，确定相关已提交元素后，用 `trace` 获取演变证据。
3. 模块、依赖、入口或测试结构变化后，若后续工作需要旧概览，则更新概览。

已知目标可直接追踪，无需每轮重复全项目扫描。跨聊天继续项目时，宿主应继续加载指引，保存报告引用、目标提交和覆盖限制；当前工作区变化可能使旧概览过期。**这些指引由 Agent 执行；强制保证某个流程节点已经运行，需要宿主调度器接入。** SDK 自身不监听项目流程，也不恢复聊天记录。详见 [阶段规则](docs/WORKFLOW.md)。

需要 HTTP 时，先将 `JAVA_AGENT_TOKEN` 设置为至少 32 字符的随机令牌，再运行：

```sh
codetracker-agent http --root /path/to/repo --port 8766
```

服务监听 `127.0.0.1`；`/health`、`/tools`、`/invoke` 和 `/mcp` 均需 Bearer 认证。只允许配置目录中的目标，建议使用普通独立 clone；远程访问需自行配置可信 TLS 通道，路径指服务端路径。完整协议见 [API](docs/API.md)。

### 如何理解结果与开销

- 检查 `status`：`ok`、`partial` 或 `error`。`partial` 必须结合警告、限制和截断信息解释；HTTP 200 或退出码 0 不等于完整分析。
- 概览中的声明、注解和测试文件是阅读线索，不是已经验证的调用图、有效依赖图或业务架构；Agent 需要继续阅读相关代码。
- 历史追踪面向本封装支持的方法、局部变量和代码块，不覆盖所有 Java 元素或未提交修改。浅克隆、缺失提交和引擎限制可能影响历史完整性；`max_events` 限制返回事件数，不限制所有历史遍历工作。
- 默认返回完整组件报告；`format="compact"` 必须同时用 `output` 在被分析项目之外保存完整报告，服务另需授权 `--output-root`，已有文件不会被覆盖。完整返回并不保证引擎覆盖所有输入。
- 每个 Client / 服务实例一次执行一个分析，忙时返回 `BUSY`。概览不启动 Java；追踪按请求启动 Java，无常驻 JVM、数据库或 GPU。Java 堆默认上限 2048 MiB，可用 `memory_mb` 调整，但这不是整个进程树的内存上限。封装便利性不代表所有输入都更快或更省内存。
- 分析在本地执行，组件不调用模型、不上传源码、不发送遥测，也不运行目标项目的构建或测试。报告可能含源码、提交信息和路径，宿主 Agent 仍可能把结果发送给其模型提供商。见 [隐私说明](PRIVACY.md)。

### 论文与上游项目

历史追踪基于作者的 [jodavimehran/code-tracker](https://github.com/jodavimehran/code-tracker)，固定使用 Maven `io.github.jodavimehran:code-tracker:3.0`。相关研究包括：

1. **代码块历史追踪** — Mohammed Tayeeb Hasan, Nikolaos Tsantalis, Pouria Alikhanifard. *Refactoring-aware Block Tracking in Commit History*. **IEEE Transactions on Software Engineering (TSE)**, 50(12), 3330–3350, **2024 年 12 月**. [DOI: 10.1109/TSE.2024.3484586](https://doi.org/10.1109/TSE.2024.3484586)。对应代码块在重构和其他变化中的历史追踪能力。
2. **方法与变量历史追踪** — Mehran Jodavi, Nikolaos Tsantalis. *Accurate Method and Variable Tracking in Commit History*. **ESEC/FSE 2022**, 183–195. [DOI: 10.1145/3540250.3549079](https://doi.org/10.1145/3540250.3549079)。对应方法和变量历史追踪的基础工作。

书目信息依据 [上游引用说明](https://github.com/jodavimehran/code-tracker#how-to-cite-codetracker) 和 [作者论文目录](https://users.encs.concordia.ca/~nikolaos/publications.html)。底层依赖 RefactoringMiner 3.0.11，其研究来源见 [RefactoringMiner 的引用说明](https://github.com/tsantalis/RefactoringMiner/blob/master/documentation/research.md)。

**项目概览扫描器并非上述论文中的 CodeTracker 算法。** 论文实验结果属于上游研究设置，不等同于本封装在任意项目上的质量或性能保证。

### 本项目新增了什么

本仓库是**基于作者库的独立 Agent 适配项目**，不是作者官方仓库或完整镜像。本项目提供项目概览扫描、目标定位与 Java 调用桥接、统一 JSON、资源限制、SDK、CLI、HTTP/MCP、宿主配置与 Skill 阶段指引；业务解释和缺陷原因判断由调用它的 Agent 完成。

分析引擎保留了 RefactoringMiner 两处经差分测试的局部优化：`StringDistance.java` 和 `ReplacementUtil.keepReservedTokens`。上游 CodeTracker 固定版本的源码 LICENSE 与 Maven POM 存在许可元数据差异，已在 [NOTICE](NOTICE.md) 中记录。本仓库不分发组合引擎二进制，也不将第三方 MIT 文件视作全仓库的统一许可证；来源与许可状态请以该说明为准。

[API 与结果](docs/API.md) · [Agent 接入](docs/AGENTS.md) · [阶段规则](docs/WORKFLOW.md) · [接口验证](docs/VERIFICATION.md) · [1.5 阶段调用验证](docs/WORKFLOW_VERIFICATION.md) · [变更记录](CHANGELOG.md)

从源码开发时，在仓库根目录执行：

```sh
python -m pip install ".[server,test]"
python -m pytest
python -m build
```

---

<a id="english"></a>

## English

### What it does

**Helps agents take over existing Java projects and use code evolution evidence during bug investigation and historical review.**

An agent entering a legacy project first needs to find modules, entry points, dependencies, and tests. During an investigation, it also needs to understand when and how a particular method, local variable, or control structure changed. This component exposes two independently callable tools:

- **`overview`: project survey.** Scans the current worktree and returns structural evidence and reading leads for planning. This scanner is implemented by this project.
- **`trace`: element history.** Invokes the authors' CodeTracker library to follow a method, local variable, or block from a selected commit, returning related commits, change events, and before/after locations.

For example, an agent investigating a date boundary issue can use the overview to find relevant modules and tests, select the committed block containing the key condition, trace its evolution, inspect the relevant commits, and design regression tests. **Historical changes support causal hypotheses; a recent edit alone does not prove the origin of a defect.**

### How it helps an agent

| Task | Evidence provided | How the agent uses it |
|---|---|---|
| A root agent takes over an unfamiliar project | Module and dependency declarations, packages, entry-point and test hints, and available Git activity | Decide what to read first, where to implement, and which tests to inspect |
| Investigate a bug | Commit history and change events for relevant methods, local variables, or control structures | Narrow historical reading and formulate testable hypotheses |
| Understand complex legacy code | Before/after locations and evolution through changes such as renames or moves | Follow code history and interpret the implementation alongside commit context |
| Resume a project or hand work to another agent | Target commits, selected elements, complete reports, and coverage limits | Reuse traceable evidence without treating an old overview as current state |

Agents can use a local process, Python SDK, HTTP, or MCP. A consistent interface supplies structured evidence; Skill and MCP guidance tell agents when to invoke the tools at relevant project checkpoints.

After implementation and tests, optionally use the independent [RefactoringMiner Agent](https://github.com/William-StarX/RefactoringMiner) to review the candidate patch. Either component works independently and does not require the other agent SDK.

### Quick start

The base SDK requires **Python 3.11+** and has no third-party Python dependencies. **Project overview requires neither Java nor Git history**; Git activity can be included when Git is available. The GitHub installation command below requires Git.

```sh
python -m pip install "git+https://github.com/William-StarX/Tracker.git"
```

```python
from codetracker_agent import Client

client = Client()
report = client.overview("/path/to/repo")
print(report["status"])
print(report["result"])  # Component report: evidence, warnings, limits, and provenance
```

History tracking additionally requires **Java 17+ and local Git repository history**. Initial engine preparation requires a **JDK and network access**:

```sh
codetracker-agent doctor
codetracker-agent prepare
```

`prepare` downloads pinned dependencies and prepares this component's engine; it does not build the target project. Later runs can reuse the cache. Set `JAVA_HOME` to select Java and `JAVA_ANALYSIS_CACHE` to select a cache directory.

```python
from codetracker_agent import Client

report = Client().trace(
    "/path/to/repo",
    "src/main/java/example/Service.java",
    42,
    commit="HEAD",
)
print(report["status"])
print(report["result"])
```

Replace the example path, revision, and line with your actual target. **The file and line must refer to the selected commit, not an uncommitted editor buffer.** Check the returned `selected_element` evidence and use `name` when a precise name is needed. Record the resolved commit ID for reproducible investigations.

An agent without a Python integration can submit one JSON request:

```sh
codetracker-agent describe
codetracker-agent call --request request.json
```

`request.json`:

```json
{"operation":"overview","repo":"/path/to/repo"}
```

`call` also accepts standard input. `describe` returns parameters for `overview` and `trace`, response schemas, and checkpoint guidance.

### Connect an agent and use it at project checkpoints

Four entry points are available: Python `Client` / `HTTPClient`, JSON CLI, MCP stdio / Streamable HTTP, and an authenticated HTTP API. Install optional dependencies for HTTP/MCP services:

```sh
python -m pip install "codetracker-agent[server] @ git+https://github.com/William-StarX/Tracker.git"
codetracker-agent config codex --root /path/to/repo
```

`config` prints a fragment to merge into the host's configuration. It also supports `claude-code`, `claude-desktop`, `cursor`, `vscode`, and `copilot`. The MCP stdio launch command is `codetracker-agent mcp --root /path/to/repo`. Configuration parsing and protocol startup have been verified; complete workflows in each host still require validation in your environment. See [agent integration](docs/AGENTS.md).

For a host that supports Skills, export the workflow, for example from a project root:

```sh
codetracker-agent install-skill --destination .agents/skills
```

This destination is a Codex project example; use your host's discovery directory. The installer refuses to overwrite an existing Skill and accepts `--java-home` and `--cache-dir`. Keep the generated `runtime.local.json` on the local machine.

An agent with the Skill or MCP guidance loaded should proactively invoke the component at these checkpoints without requiring the user to name it again:

1. Before planning work in an unfamiliar existing Java project, use `overview` to establish structural leads.
2. During bug or historical investigation, use `trace` once a relevant committed element is identified.
3. After module, dependency, entry-point, or test-layout changes, refresh an overview if subsequent work depends on it.

Known targets can be traced directly; a full project scan is not needed every turn. Across chats, the host should keep loading the guidance and retain report references, target commits, and coverage limits. Worktree changes may make an old overview stale. **The agent follows these instructions; guaranteed execution at a workflow node requires host scheduler integration.** The SDK neither monitors project progress nor restores chat history. See [checkpoint behavior](docs/WORKFLOW.md).

For HTTP, first set `JAVA_AGENT_TOKEN` to a random token of at least 32 characters, then run:

```sh
codetracker-agent http --root /path/to/repo --port 8766
```

The service binds to `127.0.0.1`. `/health`, `/tools`, `/invoke`, and `/mcp` all require Bearer authentication. Targets must stay within configured roots; use a regular independent clone. Remote access requires an operator-configured trusted TLS channel, and paths refer to the server's filesystem. See the [API](docs/API.md).

### Interpreting results and resource use

- Check `status`: `ok`, `partial`, or `error`. Interpret `partial` with warnings, limitations, and truncation information. HTTP 200 or exit code 0 does not establish complete analysis.
- Declarations, annotations, and test files in an overview are reading leads, not a verified call graph, effective dependency graph, or business architecture. The agent needs to inspect the relevant source.
- Tracking covers the methods, local variables, and blocks supported by this wrapper, not every Java element or uncommitted edits. Shallow clones, missing commits, and engine limitations can affect completeness. `max_events` bounds returned events, not all history traversal work.
- The complete component report is returned by default. `format="compact"` requires `output` to preserve the complete report outside the analyzed project; services additionally require an authorized `--output-root`. Existing files are not overwritten. A complete response does not guarantee that the engine covered every input.
- Each Client / service instance runs one analysis at a time and returns `BUSY` to concurrent callers. Overview does not start Java; tracking starts Java per request, with no persistent JVM, database, or GPU requirement. The default Java heap ceiling is 2048 MiB, configurable with `memory_mb`; this is not a process-tree memory limit. Easier integration does not imply lower time or memory use on every input.
- Analysis runs locally. The component does not call models, upload source, send telemetry, or run the target project's build or tests. Reports may contain source, commit information, and paths, and the host agent may forward results to its model provider. See [privacy](PRIVACY.md).

### Papers and upstream project

History tracking uses the authors' [jodavimehran/code-tracker](https://github.com/jodavimehran/code-tracker), pinned to Maven `io.github.jodavimehran:code-tracker:3.0`. Relevant research includes:

1. **Block history tracking** — Mohammed Tayeeb Hasan, Nikolaos Tsantalis, Pouria Alikhanifard. *Refactoring-aware Block Tracking in Commit History*. **IEEE Transactions on Software Engineering (TSE)**, 50(12), 3330–3350, **December 2024**. [DOI: 10.1109/TSE.2024.3484586](https://doi.org/10.1109/TSE.2024.3484586). Covers tracking blocks through refactorings and other changes.
2. **Method and variable history tracking** — Mehran Jodavi, Nikolaos Tsantalis. *Accurate Method and Variable Tracking in Commit History*. **ESEC/FSE 2022**, 183–195. [DOI: 10.1145/3540250.3549079](https://doi.org/10.1145/3540250.3549079). The foundational work for tracking methods and variables.

Bibliographic details follow the [upstream citation guide](https://github.com/jodavimehran/code-tracker#how-to-cite-codetracker) and the [author's publication list](https://users.encs.concordia.ca/~nikolaos/publications.html). The engine also depends on RefactoringMiner 3.0.11; see its [research references](https://github.com/tsantalis/RefactoringMiner/blob/master/documentation/research.md).

**The project overview scanner is not the CodeTracker algorithm described in these papers.** Published results apply to the upstream research settings; they do not guarantee this wrapper's quality or performance on arbitrary projects.

### What this project adds

This repository is an **independent agent integration built on the authors' library**, not the official upstream repository or a complete mirror. It provides project scanning, target selection and a Java bridge, consistent JSON, resource controls, SDK, CLI, HTTP/MCP, host configuration, and Skill checkpoint guidance. The calling agent interprets business behavior and evaluates defect causes.

The engine retains two local RefactoringMiner optimizations checked by differential tests: `StringDistance.java` and `ReplacementUtil.keepReservedTokens`. The pinned upstream CodeTracker source LICENSE and Maven POM have different licensing metadata, documented in [NOTICE](NOTICE.md). This repository does not distribute combined engine binaries, and third-party MIT files do not establish a repository-wide MIT license. Consult that notice for provenance and licensing status.

[API and results](docs/API.md) · [Agent integration](docs/AGENTS.md) · [Checkpoints](docs/WORKFLOW.md) · [Interface verification](docs/VERIFICATION.md) · [1.5 checkpoint verification](docs/WORKFLOW_VERIFICATION.md) · [Changelog](CHANGELOG.md)

For development, run from the repository root:

```sh
python -m pip install ".[server,test]"
python -m pytest
python -m build
```
