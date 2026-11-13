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

沿着这些线索，Agent 可以阅读历史实现、对照需求，并选择回归测试。修复完成后，可以使用 [RefactoringMiner Agent](https://github.com/William-StarX/RefactoringMiner) 审查补丁。

### 先跑一次项目概览

概览使用 **Python 3.11+** 运行，基础 SDK 基于 Python 标准库，可以扫描普通源码目录或 Git 仓库。在 Git 仓库中还可收集近期活动信息。下方从 GitHub 安装的命令需要 Git。

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

`prepare` 下载固定版本依赖并准备历史追踪引擎，后续调用可复用缓存。用 `JAVA_HOME` 指定 Java、`JAVA_ANALYSIS_CACHE` 指定缓存位置。

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

使用所选提交中的文件和行号替换示例目标，通过返回的 `selected_element` 确认追踪对象，也可用 `name` 精确指定名称。保存解析后的提交 ID，方便后续复查。

通过命令行调用时，将参数写成 JSON 请求：

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

把 `config` 生成的片段合并到宿主配置中，即可连接工具。命令另支持 `claude-code`、`claude-desktop`、`cursor`、`vscode`、`copilot`；也可用 `codetracker-agent mcp --root /path/to/repo` 启动 MCP stdio 服务。详细步骤见 [Agent 接入](docs/AGENTS.md)。

支持 Skill 的宿主还可导出调用流程，例如在项目根目录执行：

```sh
codetracker-agent install-skill --destination .agents/skills
```

这里使用 Codex 的项目技能目录。其他宿主选择各自的发现目录；通过 `--java-home` 和 `--cache-dir` 可以绑定已有的 Java 与缓存环境。

加载 Skill 或 MCP 指引后，Agent 会被要求在这些时候使用工具：

1. 接管陌生 Java 旧项目、制定计划前，用 `overview` 建立结构线索。
2. 缺陷或历史调查中，确定相关已提交元素后，用 `trace` 获取演变证据。
3. 模块、依赖、入口或测试结构变化后，若后续工作需要旧概览，则更新概览。

按问题选择要追踪的元素，把提交、选中对象和报告位置留在任务记录中，下次就能接着查。概览随相关工作区内容的变化更新；跨聊天继续项目时，让宿主加载已有记录和 Skill/MCP 指引。详见 [调查流程](docs/WORKFLOW.md)。

也可把调查工具作为本地 HTTP 服务使用，配合 `HTTPClient`、`/invoke` 或 MCP Streamable HTTP `/mcp` 调用。先将 `JAVA_AGENT_TOKEN` 设为至少 32 字符的随机令牌：

```sh
codetracker-agent http --root /path/to/repo --port 8766
```

服务在 `127.0.0.1` 提供 `/health`、`/tools`、`/invoke` 和 `/mcp`，通过 Bearer 令牌认证。用 `--root` 指定普通独立 clone 的分析目录；跨机器调用可连接可信 TLS 通道，并使用服务端路径。完整协议见 [API](docs/API.md)。

### 保存调查结果

`status` 表示 `ok`、`partial` 或 `error`，`result` 保存组件报告。概览返回结构线索及文件位置，追踪返回选中元素、提交、变化事件和前后位置，方便 Agent 在源码与历史之间查阅。

默认完整返回报告。使用 `format="compact"` 获取简短响应时，同时设置 `output`，将完整报告保存到分析项目之外的新文件；服务模式还需配置 `--output-root`。`max_events` 可调整返回的历史事件数。

概览由 Python 执行，历史追踪按请求启动 Java。每个 Client / 服务实例同时处理一项分析，忙时返回 `BUSY`。可用 `timeout` 设置追踪引擎超时、`memory_mb` 调整 Java 堆上限，默认堆上限为 2048 MiB。更多参数见 [API](docs/API.md)。

### CodeTracker 的研究来源

历史追踪基于作者的 [jodavimehran/code-tracker](https://github.com/jodavimehran/code-tracker)，固定使用 Maven `io.github.jodavimehran:code-tracker:3.0`。相关研究包括：

1. **代码块历史追踪** — Mohammed Tayeeb Hasan, Nikolaos Tsantalis, Pouria Alikhanifard. *Refactoring-aware Block Tracking in Commit History*. **IEEE Transactions on Software Engineering (TSE)**, 50(12), 3330–3350, **2024 年 12 月**. [DOI: 10.1109/TSE.2024.3484586](https://doi.org/10.1109/TSE.2024.3484586)。对应代码块在重构和其他变化中的历史追踪能力。
2. **方法与变量历史追踪** — Mehran Jodavi, Nikolaos Tsantalis. *Accurate Method and Variable Tracking in Commit History*. **ESEC/FSE 2022**, 183–195. [DOI: 10.1145/3540250.3549079](https://doi.org/10.1145/3540250.3549079)。对应方法和变量历史追踪的基础工作。

书目信息依据 [上游引用说明](https://github.com/jodavimehran/code-tracker#how-to-cite-codetracker) 和 [作者论文目录](https://users.encs.concordia.ca/~nikolaos/publications.html)。底层依赖 RefactoringMiner 3.0.11，其研究来源见 [RefactoringMiner 的引用说明](https://github.com/tsantalis/RefactoringMiner/blob/master/documentation/research.md)。

### 关于项目概览和封装

项目概览由本项目的 Python 扫描器完成，历史追踪使用 CodeTracker。SDK、命令行和服务将 Agent 指定的提交与代码位置传给引擎，再把结果整理为 JSON 报告，便于继续调查和交接。

分析引擎包含 RefactoringMiner 的两处局部优化：`StringDistance.java` 和 `ReplacementUtil.keepReservedTokens`，通过减少字符串计算和临时分配支持历史分析，结果经过差分测试。

### Attention

- 概览和历史提供调查线索，结论结合源码与测试确认。浅克隆、缺失提交和复杂合并可能影响覆盖，`partial` 结果需查看警告与截断信息。
- 若需要在指定阶段强制执行调查，将工具调用接入宿主流程；日常使用可由 Agent 遵循 Skill/MCP 指引。
- 报告可能包含源码、提交信息和路径，分享前按需检查；本机配置的保管方式见 [隐私说明](PRIVACY.md)。
- 上游来源、局部修改及许可信息（含 CodeTracker 的许可元数据差异）见 [NOTICE](NOTICE.md)。

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

The agent can follow these leads to read earlier implementations, check requirements, and choose regression tests. Once a fix is ready, [RefactoringMiner Agent](https://github.com/William-StarX/RefactoringMiner) can help review the patch.

### Start with the project layout

Overview runs on **Python 3.11+**. The base SDK uses the Python standard library and scans both ordinary source directories and Git repositories, with recent activity available for Git projects. The GitHub installation command below requires Git.

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

`prepare` downloads pinned dependencies and prepares the history engine for reuse. Set `JAVA_HOME` to select Java and `JAVA_ANALYSIS_CACHE` to choose a cache directory.

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

Use the file and line from your chosen commit, then check `selected_element` to confirm the target. You can also supply `name` to select a specific name. Keep the resolved commit ID for later reference.

For command-line use, put the parameters in a JSON request:

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

Merge the fragment printed by `config` into the host's configuration to connect the tools. It also supports `claude-code`, `claude-desktop`, `cursor`, `vscode`, and `copilot`. To launch MCP stdio directly, use `codetracker-agent mcp --root /path/to/repo`. See [agent integration](docs/AGENTS.md) for setup details.

For a host that supports Skills, export the workflow, for example from a project root:

```sh
codetracker-agent install-skill --destination .agents/skills
```

This example uses Codex's project skill directory. Choose the discovery directory for your host, and use `--java-home` and `--cache-dir` to bind an existing Java installation and cache.

Once loaded, the Skill or MCP instructions ask the agent to use the tools at these points:

1. Before planning work in an unfamiliar existing Java project, use `overview` to establish structural leads.
2. During bug or historical investigation, use `trace` once a relevant committed element is identified.
3. After module, dependency, entry-point, or test-layout changes, refresh an overview if subsequent work depends on it.

Choose elements relevant to the question and keep their commits, selected targets, and report locations in the task notes so work can continue from them. Refresh the overview when relevant worktree content changes. Across chats, have the host load those notes and the Skill/MCP instructions. See the [investigation workflow](docs/WORKFLOW.md).

You can also run a local HTTP service and call it through `HTTPClient`, `/invoke`, or MCP Streamable HTTP at `/mcp`. First set `JAVA_AGENT_TOKEN` to a random token of at least 32 characters:

```sh
codetracker-agent http --root /path/to/repo --port 8766
```

The service exposes `/health`, `/tools`, `/invoke`, and `/mcp` at `127.0.0.1`, authenticated with a Bearer token. Set `--root` to a regular independent clone. For access from another machine, connect through a trusted TLS channel and use server-side paths. See the [API](docs/API.md).

### Keep the investigation results

`status` is `ok`, `partial`, or `error`, and `result` holds the component report. Overview returns structural leads and file locations; tracing returns the selected element, commits, change events, and before/after locations, so the agent can move between source and history.

Full reports are returned by default. For a shorter response, use `format="compact"` together with `output` to save the full report to a new file outside the analyzed project. Service mode also requires `--output-root`. Adjust `max_events` to choose how many history events to return.

Python runs the overview, while tracking starts Java per request. Each Client / service instance handles one analysis at a time and returns `BUSY` while occupied. Use `timeout` to set the tracking engine timeout and `memory_mb` to adjust the Java heap ceiling, which defaults to 2048 MiB. More options are listed in the [API](docs/API.md).

### The research behind CodeTracker

History tracking uses the authors' [jodavimehran/code-tracker](https://github.com/jodavimehran/code-tracker), pinned to Maven `io.github.jodavimehran:code-tracker:3.0`. Relevant research includes:

1. **Block history tracking** — Mohammed Tayeeb Hasan, Nikolaos Tsantalis, Pouria Alikhanifard. *Refactoring-aware Block Tracking in Commit History*. **IEEE Transactions on Software Engineering (TSE)**, 50(12), 3330–3350, **December 2024**. [DOI: 10.1109/TSE.2024.3484586](https://doi.org/10.1109/TSE.2024.3484586). Covers tracking blocks through refactorings and other changes.
2. **Method and variable history tracking** — Mehran Jodavi, Nikolaos Tsantalis. *Accurate Method and Variable Tracking in Commit History*. **ESEC/FSE 2022**, 183–195. [DOI: 10.1145/3540250.3549079](https://doi.org/10.1145/3540250.3549079). The foundational work for tracking methods and variables.

Bibliographic details follow the [upstream citation guide](https://github.com/jodavimehran/code-tracker#how-to-cite-codetracker) and the [author's publication list](https://users.encs.concordia.ca/~nikolaos/publications.html). The engine also depends on RefactoringMiner 3.0.11; see its [research references](https://github.com/tsantalis/RefactoringMiner/blob/master/documentation/research.md).

### About the scanner and integration

This project's Python scanner produces the overview, while CodeTracker handles history. The SDK, command line, and services pass the agent's chosen commit and source location to the engine, then return a JSON report for further investigation or handoff.

The engine includes two local RefactoringMiner optimizations, `StringDistance.java` and `ReplacementUtil.keepReservedTokens`, to reduce string computation and temporary allocation during history analysis. Results have been checked with differential tests.

### Attention

- Use source and tests to assess the leads from overview and history. Shallow clones, missing commits, and complex merges can affect coverage; check warnings and truncation details for `partial` results.
- Wire calls into the host workflow when investigation must run at a required step. For everyday use, agents can follow the Skill/MCP instructions.
- Reports may contain source, commit information, and paths. Check them before sharing; see [privacy](PRIVACY.md) for handling local configuration.
- See [NOTICE](NOTICE.md) for upstream sources, local changes, and licensing details, including CodeTracker's licensing metadata discrepancy.

[API and results](docs/API.md) · [Agent integration](docs/AGENTS.md) · [Checkpoints](docs/WORKFLOW.md) · [Interface verification](docs/VERIFICATION.md) · [1.5 checkpoint verification](docs/WORKFLOW_VERIFICATION.md) · [Changelog](CHANGELOG.md)

For development, run from the repository root:

```sh
python -m pip install ".[server,test]"
python -m pytest
python -m build
```
