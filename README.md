# TraceTrail

SDK / 服务 **1.5.0** · 结果接口 **1.0** · 历史引擎 CodeTracker **3.0**

SDK / service **1.5.0** · Result interface **1.0** · History engine CodeTracker **3.0**

TraceTrail 帮 Agent 接手旧 Java 项目和调查缺陷。先用 `overview` 找出模块、入口和测试，再用 `trace` 追踪关键方法、变量或代码块的历史。项目概览由本项目的 Python 扫描器完成，历史追踪使用开源项目 CodeTracker 的库。

TraceTrail helps agents take on existing Java projects and investigate bugs. Start with `overview` to find modules, entry points, and tests, then use `trace` to follow a relevant method, variable, or block through history. This project's Python scanner produces the overview; the open-source CodeTracker library handles history tracking.

## 快速开始：查看项目结构<br>Quick start: explore the project

概览使用 **Python 3.11+** 运行，基础 SDK 基于 Python 标准库，可以扫描普通源码目录或 Git 仓库。在 Git 仓库中还可收集近期活动信息。下方从 GitHub 安装的命令需要 Git。

Overview runs on **Python 3.11+**. The base SDK uses the Python standard library and scans both ordinary source directories and Git repositories, with recent activity available for Git projects. The GitHub installation command below requires Git.

TraceTrail 的命令行入口为 `codetracker-agent`，Python 包为 `codetracker_agent`。

Use `codetracker-agent` for TraceTrail's command line and `codetracker_agent` for its Python package.

```sh
python -m pip install "git+https://github.com/William-StarX/Tracker.git"
```

```python
from codetracker_agent import Client

client = Client()
report = client.overview("/path/to/repo")
print(report["status"])
# 组件报告，包含证据、警告、限制和来源
# Component report: evidence, warnings, limits, and provenance
print(report["result"])
```

## 调查一段代码的历史<br>Investigate a piece of code

历史追踪另需 **Java 17+ 和本地 Git 仓库历史**；首次准备引擎需要 **JDK 和网络**：

History tracking additionally requires **Java 17+ and local Git repository history**. Initial engine preparation requires a **JDK and network access**:

```sh
codetracker-agent doctor
codetracker-agent prepare
```

`prepare` 下载固定版本依赖并准备历史追踪引擎，后续调用可复用缓存。用 `JAVA_HOME` 指定 Java、`JAVA_ANALYSIS_CACHE` 指定缓存位置。

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

使用所选提交中的文件和行号替换示例目标，通过返回的 `selected_element` 确认追踪对象，也可用 `name` 精确指定名称。保存解析后的提交 ID，方便后续复查。

Use the file and line from your chosen commit, then check `selected_element` to confirm the target. You can also supply `name` to select a specific name. Keep the resolved commit ID for later reference.

通过命令行调用时，将参数写成 JSON 请求：

For command-line use, put the parameters in a JSON request:

```sh
codetracker-agent describe
codetracker-agent call --request request.json
```

`request.json`

```json
{"operation":"overview","repo":"/path/to/repo"}
```

`call` 也接受标准输入。`describe` 返回 `overview`、`trace` 的参数、响应 Schema 和调用阶段指引。

`call` also accepts standard input. `describe` returns parameters for `overview` and `trace`, response schemas, and checkpoint guidance.

## 交给 Agent 使用<br>Use it with an agent

已有 Python Agent 可以直接用上面的 `Client`，能运行命令的 Agent 可以调用 JSON CLI。要让支持 MCP 的宿主发现这两个工具，先安装服务依赖并生成配置：

A Python agent can use `Client` directly; an agent that can run commands can use the JSON CLI. To expose both tools to an MCP host, install the service dependencies and generate a configuration:

```sh
python -m pip install "codetracker-agent[server] @ git+https://github.com/William-StarX/Tracker.git"
codetracker-agent config codex --root /path/to/repo
```

把 `config` 生成的片段合并到宿主配置中，即可连接工具。命令另支持 `claude-code`、`claude-desktop`、`cursor`、`vscode`、`copilot`；也可用 `codetracker-agent mcp --root /path/to/repo` 启动 MCP stdio 服务。详细步骤见 [Agent 接入](docs/AGENTS.md)。

Merge the fragment printed by `config` into the host's configuration to connect the tools. It also supports `claude-code`, `claude-desktop`, `cursor`, `vscode`, and `copilot`. To launch MCP stdio directly, use `codetracker-agent mcp --root /path/to/repo`. See [agent integration](docs/AGENTS.md) for setup details.

支持 Skill 的宿主还可导出调用流程，例如在项目根目录执行：

For a host that supports Skills, export the workflow, for example from a project root:

```sh
codetracker-agent install-skill --destination .agents/skills
```

这里使用 Codex 的项目技能目录。其他宿主选择各自的发现目录；通过 `--java-home` 和 `--cache-dir` 可以绑定已有的 Java 与缓存环境。

This example uses Codex's project skill directory. Choose the discovery directory for your host, and use `--java-home` and `--cache-dir` to bind an existing Java installation and cache.

加载 Skill 或 MCP 指引后，Agent 会被要求在这些时候使用工具：

Once loaded, the Skill or MCP instructions ask the agent to use the tools at these points:

1. 接管陌生 Java 旧项目、制定计划前，用 `overview` 建立结构线索。

   Before planning work in an unfamiliar existing Java project, use `overview` to establish structural leads.

2. 缺陷或历史调查中，确定相关已提交元素后，用 `trace` 获取演变证据。

   During bug or historical investigation, use `trace` once a relevant committed element is identified.

3. 模块、依赖、入口或测试结构变化后，若后续工作需要旧概览，则更新概览。

   After module, dependency, entry-point, or test-layout changes, refresh an overview if subsequent work depends on it.

按问题选择要追踪的元素，把提交、选中对象和报告位置留在任务记录中，下次就能接着查。概览随相关工作区内容的变化更新；跨聊天继续项目时，让宿主加载已有记录和 Skill/MCP 指引。详见 [调查流程](docs/WORKFLOW.md)。

Choose elements relevant to the question and keep their commits, selected targets, and report locations in the task notes so work can continue from them. Refresh the overview when relevant worktree content changes. Across chats, have the host load those notes and the Skill/MCP instructions. See the [investigation workflow](docs/WORKFLOW.md).

也可把调查工具作为本地 HTTP 服务使用，配合 `HTTPClient`、`/invoke` 或 MCP Streamable HTTP `/mcp` 调用。先将 `JAVA_AGENT_TOKEN` 设为至少 32 字符的随机令牌：

You can also run a local HTTP service and call it through `HTTPClient`, `/invoke`, or MCP Streamable HTTP at `/mcp`. First set `JAVA_AGENT_TOKEN` to a random token of at least 32 characters:

```sh
codetracker-agent http --root /path/to/repo --port 8766
```

服务在 `127.0.0.1` 提供 `/health`、`/tools`、`/invoke` 和 `/mcp`，通过 Bearer 令牌认证。用 `--root` 指定普通独立 clone 的分析目录；跨机器调用可连接可信 TLS 通道，并使用服务端路径。完整协议见 [API](docs/API.md)。

The service exposes `/health`, `/tools`, `/invoke`, and `/mcp` at `127.0.0.1`, authenticated with a Bearer token. Set `--root` to a regular independent clone. For access from another machine, connect through a trusted TLS channel and use server-side paths. See the [API](docs/API.md).

## 读取并保存调查结果<br>Read and save the findings

`status` 表示 `ok`、`partial` 或 `error`，`result` 保存组件报告。概览返回结构线索及文件位置，追踪返回选中元素、提交、变化事件和前后位置，方便 Agent 在源码与历史之间查阅。

`status` is `ok`, `partial`, or `error`, and `result` holds the component report. Overview returns structural leads and file locations; tracing returns the selected element, commits, change events, and before/after locations, so the agent can move between source and history.

默认完整返回报告。使用 `format="compact"` 获取简短响应时，同时设置 `output`，将完整报告保存到分析项目之外的新文件；服务模式还需配置 `--output-root`。`max_events` 可调整返回的历史事件数。

Full reports are returned by default. For a shorter response, use `format="compact"` together with `output` to save the full report to a new file outside the analyzed project. Service mode also requires `--output-root`. Adjust `max_events` to choose how many history events to return.

概览由 Python 执行，历史追踪按请求启动 Java。每个 Client / 服务实例同时处理一项分析，忙时返回 `BUSY`。可用 `timeout` 设置追踪引擎超时、`memory_mb` 调整 Java 堆上限，默认堆上限为 2048 MiB。更多参数见 [API](docs/API.md)。

Python runs the overview, while tracking starts Java per request. Each Client / service instance handles one analysis at a time and returns `BUSY` while occupied. Use `timeout` to set the tracking engine timeout and `memory_mb` to adjust the Java heap ceiling, which defaults to 2048 MiB. More options are listed in the [API](docs/API.md).

## TraceTrail 增加了什么<br>What TraceTrail adds

- **先给 Agent 一份项目地图。** 自建概览扫描器收集 Maven/Gradle 声明、包结构、入口和测试线索，并附上文件位置。普通源码目录即可开始梳理，这一步只需 Python。

  **Give the agent a project map first.** The custom overview scanner collects Maven/Gradle declarations, packages, entry points, and test hints with file locations. It can start from an ordinary source directory using only Python.

- **从一个代码位置开始调查。** 传入提交、文件和行号，组件负责定位元素、调用 CodeTracker，并整理选中对象、变化事件和前后位置。Agent 可以先缩小范围，再追踪与问题有关的代码。

  **Start an investigation from a source location.** Supply a commit, file, and line. The component locates the element, calls CodeTracker, and organizes the selected target, change events, and before/after locations. The agent can narrow its search before tracing the code relevant to the problem.

- **让调查结果接得上后续工作。** SDK、命令行和服务返回同一套报告；Skill/MCP 指引覆盖项目接管、缺陷调查和结构更新。把提交、目标和报告位置保留在任务记录中，后续 Agent 就有明确的复查入口。接入与结果一致性见 [验证记录](docs/VERIFICATION.md)。

  **Keep findings useful for the next task.** The SDK, command line, and services return the same report format. Skill/MCP instructions cover onboarding, bug investigation, and structural updates. Recording the commit, target, and report location gives the next agent a clear place to resume. See the [integration and result checks](docs/VERIFICATION.md).

历史引擎包含两处经过差分测试的 RefactoringMiner 字符串辅助计算优化；基础 SDK 使用 Python 标准库，Java 在历史查询时按需启动。修复完成后，可用 [RefactoringMiner Agent](https://github.com/William-StarX/RefactoringMiner) 审查补丁。

The history engine includes two local optimizations to RefactoringMiner's string helpers, checked by differential tests. The base SDK uses the Python standard library, and Java starts on demand for history queries. Once a fix is ready, use [RefactoringMiner Agent](https://github.com/William-StarX/RefactoringMiner) to review the patch.

## 开源基础与论文<br>Open-source foundation and papers

历史追踪采用 CodeTracker 的重构感知追踪思路，调用作者的 [jodavimehran/code-tracker](https://github.com/jodavimehran/code-tracker)，固定使用 Maven `io.github.jodavimehran:code-tracker:3.0`。相关研究包括：

History analysis follows CodeTracker's refactoring-aware tracking approach and uses the authors' [jodavimehran/code-tracker](https://github.com/jodavimehran/code-tracker), pinned to Maven `io.github.jodavimehran:code-tracker:3.0`. Relevant research includes:

1. **代码块历史追踪** — Mohammed Tayeeb Hasan, Nikolaos Tsantalis, Pouria Alikhanifard. *Refactoring-aware Block Tracking in Commit History*. **IEEE Transactions on Software Engineering (TSE)**, 50(12), 3330–3350, **2024 年 12 月**. [DOI: 10.1109/TSE.2024.3484586](https://doi.org/10.1109/TSE.2024.3484586)。对应代码块在重构和其他变化中的历史追踪能力。

   **Block history tracking** — Mohammed Tayeeb Hasan, Nikolaos Tsantalis, Pouria Alikhanifard. *Refactoring-aware Block Tracking in Commit History*. **IEEE Transactions on Software Engineering (TSE)**, 50(12), 3330–3350, **December 2024**. [DOI: 10.1109/TSE.2024.3484586](https://doi.org/10.1109/TSE.2024.3484586). Covers tracking blocks through refactorings and other changes.

2. **方法与变量历史追踪** — Mehran Jodavi, Nikolaos Tsantalis. *Accurate Method and Variable Tracking in Commit History*. **ESEC/FSE 2022**, 183–195. [DOI: 10.1145/3540250.3549079](https://doi.org/10.1145/3540250.3549079)。对应方法和变量历史追踪的基础工作。

   **Method and variable history tracking** — Mehran Jodavi, Nikolaos Tsantalis. *Accurate Method and Variable Tracking in Commit History*. **ESEC/FSE 2022**, 183–195. [DOI: 10.1145/3540250.3549079](https://doi.org/10.1145/3540250.3549079). The foundational work for tracking methods and variables.

书目信息依据 [上游引用说明](https://github.com/jodavimehran/code-tracker#how-to-cite-codetracker) 和 [作者论文目录](https://users.encs.concordia.ca/~nikolaos/publications.html)。底层依赖 RefactoringMiner 3.0.11，其研究来源见 [RefactoringMiner 的引用说明](https://github.com/tsantalis/RefactoringMiner/blob/master/documentation/research.md)。

Bibliographic details follow the [upstream citation guide](https://github.com/jodavimehran/code-tracker#how-to-cite-codetracker) and the [author's publication list](https://users.encs.concordia.ca/~nikolaos/publications.html). The engine also depends on RefactoringMiner 3.0.11; see its [research references](https://github.com/tsantalis/RefactoringMiner/blob/master/documentation/research.md).

## 注意事项<br>Attention

- 概览和历史提供调查线索，结论结合源码与测试确认。浅克隆、缺失提交和复杂合并可能影响覆盖，`partial` 结果需查看警告与截断信息。

  Use source and tests to assess the leads from overview and history. Shallow clones, missing commits, and complex merges can affect coverage; check warnings and truncation details for `partial` results.

- 若需要在指定阶段强制执行调查，将工具调用接入宿主流程；日常使用可由 Agent 遵循 Skill/MCP 指引。

  Wire calls into the host workflow when investigation must run at a required step. For everyday use, agents can follow the Skill/MCP instructions.

- 报告可能包含源码、提交信息和路径，分享前按需检查；本机配置的保管方式见 [隐私说明](PRIVACY.md)。

  Reports may contain source, commit information, and paths. Check them before sharing; see [privacy](PRIVACY.md) for handling local configuration.

- 上游来源、局部修改及许可信息（含 CodeTracker 的许可元数据差异）见 [NOTICE](NOTICE.md)。

  See [NOTICE](NOTICE.md) for upstream sources, local changes, and licensing details, including CodeTracker's licensing metadata discrepancy.

[API 与结果](docs/API.md) · [Agent 接入](docs/AGENTS.md) · [阶段规则](docs/WORKFLOW.md) · [接口验证](docs/VERIFICATION.md) · [1.5 阶段调用验证](docs/WORKFLOW_VERIFICATION.md) · [变更记录](CHANGELOG.md)

[API and results](docs/API.md) · [Agent integration](docs/AGENTS.md) · [Checkpoints](docs/WORKFLOW.md) · [Interface verification](docs/VERIFICATION.md) · [1.5 checkpoint verification](docs/WORKFLOW_VERIFICATION.md) · [Changelog](CHANGELOG.md)

从源码开发时，在仓库根目录执行：

For development, run from the repository root:

```sh
python -m pip install ".[server,test]"
python -m pytest
python -m build
```
