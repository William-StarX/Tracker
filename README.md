# CodeTracker Agent

[中文](#chinese) · [English](#english)

SDK / service **1.5.0** · Result interface **1.0** · CodeTracker **3.0**

<a id="chinese"></a>

## 中文

拿到一个旧 Java 仓库，Agent 往往先要弄清两件事：从哪里开始读，以及眼前这段代码是怎么来的。

CodeTracker Agent 为这两件事提供了两个入口。`overview` 扫描项目结构，找出模块、入口和测试线索；`trace` 从指定提交出发，沿历史追踪一个方法、局部变量或代码块。前者是本项目编写的扫描器，后者调用 CodeTracker 作者库。

### 从项目里找到调查入口

刚接手项目，可以先跑概览。模块和依赖声明帮助 Agent 判断要读哪一部分，包结构、入口注解和测试文件则给出具体的阅读位置。Root Agent 可以据此安排后续调查，再阅读代码确认模块职责。

如果已经知道问题出在某个方法，就直接追踪那个元素。例如，一个日期判断为何多了一层条件，可以沿历史找到相关修改，再阅读提交说明、前后实现和测试。即使代码曾改名或移动，CodeTracker 也会尝试恢复它的沿革。

这些结果能缩小调查范围，但“在哪次提交改过”和“为什么出现缺陷”仍是两件事。原因需要结合代码和测试验证。修复完成后的补丁审查，可以交给另一个独立工具 [RefactoringMiner Agent](https://github.com/William-StarX/RefactoringMiner)。

### 先跑一次项目概览

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

### 追踪一段代码

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

### 在项目中持续使用

已有 Python Agent 可以直接用上面的 `Client`，能运行命令的 Agent 可以调用 JSON CLI。要让支持 MCP 的宿主发现这两个工具，先安装服务依赖并生成配置：

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

加载 Skill 或 MCP 指引后，Agent 会被要求在这些时候使用工具：

1. 接管陌生 Java 旧项目、制定计划前，用 `overview` 建立结构线索。
2. 缺陷或历史调查中，确定相关已提交元素后，用 `trace` 获取演变证据。
3. 模块、依赖、入口或测试结构变化后，若后续工作需要旧概览，则更新概览。

不必每轮聊天都扫描仓库，也不必追踪每个方法。把调查过的提交、选中元素和报告位置留在任务记录中，下次可以接着查；概览描述的是工作区，相关文件变了就要重新判断它是否仍适用。跨聊天使用还需要宿主继续加载指引，工具本身不保存对话。若要保证指定步骤一定执行，需要在宿主流程中接入调用。详见 [调查流程](docs/WORKFLOW.md)。

也可把调查工具作为本地 HTTP 服务使用，配合 `HTTPClient`、`/invoke` 或 MCP Streamable HTTP `/mcp` 调用。先将 `JAVA_AGENT_TOKEN` 设为至少 32 字符的随机令牌：

```sh
codetracker-agent http --root /path/to/repo --port 8766
```

服务监听 `127.0.0.1`；`/health`、`/tools`、`/invoke` 和 `/mcp` 均需 Bearer 认证。只允许配置目录中的目标，建议使用普通独立 clone；远程访问需自行配置可信 TLS 通道，路径指服务端路径。完整协议见 [API](docs/API.md)。

### 调查范围与运行开销

- 检查 `status`：`ok`、`partial` 或 `error`。`partial` 必须结合警告、限制和截断信息解释；HTTP 200 或退出码 0 不等于完整分析。
- 概览中的声明、注解和测试文件是阅读线索，不是已经验证的调用图、有效依赖图或业务架构；Agent 需要继续阅读相关代码。
- 历史追踪面向本封装支持的方法、局部变量和代码块，不覆盖所有 Java 元素或未提交修改。浅克隆、缺失提交和引擎限制可能影响历史完整性；`max_events` 限制返回事件数，不限制所有历史遍历工作。
- 默认返回完整组件报告；`format="compact"` 必须同时用 `output` 在被分析项目之外保存完整报告，服务另需授权 `--output-root`，已有文件不会被覆盖。完整返回并不保证引擎覆盖所有输入。
- 每个 Client / 服务实例一次执行一个分析，忙时返回 `BUSY`。概览不启动 Java；追踪按请求启动 Java，无常驻 JVM、数据库或 GPU。Java 堆默认上限 2048 MiB，可用 `memory_mb` 调整，但这不是整个进程树的内存上限。封装便利性不代表所有输入都更快或更省内存。
- 分析在本地执行，组件不调用模型、不上传源码、不发送遥测，也不运行目标项目的构建或测试。报告可能含源码、提交信息和路径，宿主 Agent 仍可能把结果发送给其模型提供商。见 [隐私说明](PRIVACY.md)。

### CodeTracker 的研究来源

历史追踪基于作者的 [jodavimehran/code-tracker](https://github.com/jodavimehran/code-tracker)，固定使用 Maven `io.github.jodavimehran:code-tracker:3.0`。相关研究包括：

1. **代码块历史追踪** — Mohammed Tayeeb Hasan, Nikolaos Tsantalis, Pouria Alikhanifard. *Refactoring-aware Block Tracking in Commit History*. **IEEE Transactions on Software Engineering (TSE)**, 50(12), 3330–3350, **2024 年 12 月**. [DOI: 10.1109/TSE.2024.3484586](https://doi.org/10.1109/TSE.2024.3484586)。对应代码块在重构和其他变化中的历史追踪能力。
2. **方法与变量历史追踪** — Mehran Jodavi, Nikolaos Tsantalis. *Accurate Method and Variable Tracking in Commit History*. **ESEC/FSE 2022**, 183–195. [DOI: 10.1145/3540250.3549079](https://doi.org/10.1145/3540250.3549079)。对应方法和变量历史追踪的基础工作。

书目信息依据 [上游引用说明](https://github.com/jodavimehran/code-tracker#how-to-cite-codetracker) 和 [作者论文目录](https://users.encs.concordia.ca/~nikolaos/publications.html)。底层依赖 RefactoringMiner 3.0.11，其研究来源见 [RefactoringMiner 的引用说明](https://github.com/tsantalis/RefactoringMiner/blob/master/documentation/research.md)。

**项目概览扫描器并非上述论文中的 CodeTracker 算法。** 论文实验结果属于上游研究设置，不等同于本封装在任意项目上的质量或性能保证。

### 关于项目概览和封装

这里的项目概览、SDK、命令行和服务接入由本项目实现。历史追踪交给 CodeTracker，封装负责把 Agent 指定的提交和代码位置传给它，再返回 JSON 报告。这是对作者库的独立适配，未复制整个上游项目。

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

An agent opening an unfamiliar Java repository usually has two questions: where to start reading, and how the code in front of it got there.

CodeTracker Agent provides an entry point for each. `overview` scans the project for modules, entry points, and tests. `trace` follows a method, local variable, or block through history, starting at a chosen commit. The overview scanner belongs to this project; history tracking uses the authors' CodeTracker library.

### Finding a place to start

Run an overview when first taking on a project. Module and dependency declarations help the agent choose a part of the repository to inspect. Packages, entry-point annotations, and test files point to specific places to read. A root agent can use these leads to plan the investigation, then check the source to establish what each module does.

If the problem is already narrowed down to a method, trace that element directly. To investigate an extra condition in a date check, for example, follow its history to the relevant changes, then read the commit messages, earlier implementations, and tests. CodeTracker attempts to follow the element even when it has been renamed or moved.

This narrows the investigation, but identifying a change does not establish the cause of a bug. That still takes source inspection and tests. Once a fix is ready, the separate [RefactoringMiner Agent](https://github.com/William-StarX/RefactoringMiner) can help review the patch.

### Start with the project layout

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

### Follow a method, variable, or block

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

### Keep it available during a project

A Python agent can use `Client` directly; an agent that can run commands can use the JSON CLI. To expose both tools to an MCP host, install the service dependencies and generate a configuration:

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

Once loaded, the Skill or MCP instructions ask the agent to use the tools at these points:

1. Before planning work in an unfamiliar existing Java project, use `overview` to establish structural leads.
2. During bug or historical investigation, use `trace` once a relevant committed element is identified.
3. After module, dependency, entry-point, or test-layout changes, refresh an overview if subsequent work depends on it.

There is no need to scan the repository every turn or trace every method. Keep the investigated commits, selected elements, and report locations in the task notes so work can continue from them. An overview describes the worktree, so reconsider it when relevant files change. Across chats, the host must keep loading the instructions; the tool does not store conversations. Required execution at a particular step needs a call wired into the host's workflow. See the [investigation workflow](docs/WORKFLOW.md).

You can also run a local HTTP service and call it through `HTTPClient`, `/invoke`, or MCP Streamable HTTP at `/mcp`. First set `JAVA_AGENT_TOKEN` to a random token of at least 32 characters:

```sh
codetracker-agent http --root /path/to/repo --port 8766
```

The service binds to `127.0.0.1`. `/health`, `/tools`, `/invoke`, and `/mcp` all require Bearer authentication. Targets must stay within configured roots; use a regular independent clone. Remote access requires an operator-configured trusted TLS channel, and paths refer to the server's filesystem. See the [API](docs/API.md).

### Tracking scope and resource use

- Check `status`: `ok`, `partial`, or `error`. Interpret `partial` with warnings, limitations, and truncation information. HTTP 200 or exit code 0 does not establish complete analysis.
- Declarations, annotations, and test files in an overview are reading leads, not a verified call graph, effective dependency graph, or business architecture. The agent needs to inspect the relevant source.
- Tracking covers the methods, local variables, and blocks supported by this wrapper, not every Java element or uncommitted edits. Shallow clones, missing commits, and engine limitations can affect completeness. `max_events` bounds returned events, not all history traversal work.
- The complete component report is returned by default. `format="compact"` requires `output` to preserve the complete report outside the analyzed project; services additionally require an authorized `--output-root`. Existing files are not overwritten. A complete response does not guarantee that the engine covered every input.
- Each Client / service instance runs one analysis at a time and returns `BUSY` to concurrent callers. Overview does not start Java; tracking starts Java per request, with no persistent JVM, database, or GPU requirement. The default Java heap ceiling is 2048 MiB, configurable with `memory_mb`; this is not a process-tree memory limit. Easier integration does not imply lower time or memory use on every input.
- Analysis runs locally. The component does not call models, upload source, send telemetry, or run the target project's build or tests. Reports may contain source, commit information, and paths, and the host agent may forward results to its model provider. See [privacy](PRIVACY.md).

### The research behind CodeTracker

History tracking uses the authors' [jodavimehran/code-tracker](https://github.com/jodavimehran/code-tracker), pinned to Maven `io.github.jodavimehran:code-tracker:3.0`. Relevant research includes:

1. **Block history tracking** — Mohammed Tayeeb Hasan, Nikolaos Tsantalis, Pouria Alikhanifard. *Refactoring-aware Block Tracking in Commit History*. **IEEE Transactions on Software Engineering (TSE)**, 50(12), 3330–3350, **December 2024**. [DOI: 10.1109/TSE.2024.3484586](https://doi.org/10.1109/TSE.2024.3484586). Covers tracking blocks through refactorings and other changes.
2. **Method and variable history tracking** — Mehran Jodavi, Nikolaos Tsantalis. *Accurate Method and Variable Tracking in Commit History*. **ESEC/FSE 2022**, 183–195. [DOI: 10.1145/3540250.3549079](https://doi.org/10.1145/3540250.3549079). The foundational work for tracking methods and variables.

Bibliographic details follow the [upstream citation guide](https://github.com/jodavimehran/code-tracker#how-to-cite-codetracker) and the [author's publication list](https://users.encs.concordia.ca/~nikolaos/publications.html). The engine also depends on RefactoringMiner 3.0.11; see its [research references](https://github.com/tsantalis/RefactoringMiner/blob/master/documentation/research.md).

**The project overview scanner is not the CodeTracker algorithm described in these papers.** Published results apply to the upstream research settings; they do not guarantee this wrapper's quality or performance on arbitrary projects.

### About the scanner and integration

The project overview, SDK, command line, and service integration are implemented here. CodeTracker handles historical tracking: the wrapper passes it the agent's chosen commit and source location, then returns a JSON report. This is a separate integration of the authors' library, without a copy of the full upstream project.

The engine retains two local RefactoringMiner optimizations checked by differential tests: `StringDistance.java` and `ReplacementUtil.keepReservedTokens`. The pinned upstream CodeTracker source LICENSE and Maven POM have different licensing metadata, documented in [NOTICE](NOTICE.md). This repository does not distribute combined engine binaries, and third-party MIT files do not establish a repository-wide MIT license. Consult that notice for provenance and licensing status.

[API and results](docs/API.md) · [Agent integration](docs/AGENTS.md) · [Checkpoints](docs/WORKFLOW.md) · [Interface verification](docs/VERIFICATION.md) · [1.5 checkpoint verification](docs/WORKFLOW_VERIFICATION.md) · [Changelog](CHANGELOG.md)

For development, run from the repository root:

```sh
python -m pip install ".[server,test]"
python -m pytest
python -m build
```
