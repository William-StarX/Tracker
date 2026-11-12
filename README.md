# CodeTracker Agent

独立、可安装、可被不同 Agent 调用的 Java 分析组件。梳理项目结构，并追踪 Java 方法、局部变量或语句块的提交历史。项目概览是自编扫描器；历史追踪使用 CodeTracker 作者库。

这是基于作者库的定制适配项目，**不是作者官方仓库，也不是其完整镜像**。SDK/服务版本 **1.4.0**，结果接口 **1.0**。保留已有 1.2 分析引擎和两处等价优化，详见 [来源与许可](NOTICE.md)。

## 快速使用

需要 Python 3.11+。Java 分析需 Java 17+、Git（目录比较不需要 Git）；首次准备需 JDK 和网络。项目概览不需要 Java。基础 SDK 没有第三方 Python 依赖。

```sh
python -m pip install "git+https://github.com/William-StarX/Tracker.git"
codetracker-agent doctor
codetracker-agent prepare
```

`prepare` 只准备本组件引擎，不构建被分析项目；下载固定版本 Maven/Java 依赖，后续命中缓存不重复构建。`JAVA_HOME` 可指定 Java，`JAVA_ANALYSIS_CACHE` 可指定缓存。概览可跳过 `prepare`。

```python
from codetracker_agent import Client

result = Client().overview("/path/to/repo")
# 历史调查：Client().trace("/path/to/repo", "src/main/java/example/App.java", 42, name="run")
print(result["status"])
print(result["result"])  # 完整组件报告；保留证据、警告、限制和来源
```

任意能启动本地进程的 Agent 都可以通过 JSON 调用，无需 Python 集成：

```sh
codetracker-agent describe
codetracker-agent call --request request.json
```

`request.json`：

```json
{"operation":"overview","repo":"/path/to/repo"}
```

也支持把同一 JSON 写入 `call` 的标准输入。错误退出码为 2，成功和带明确限制的 `partial` 为 0；必须检查 `status`。

## 接入 Agent

安装可选服务依赖后启动标准 MCP：

```sh
python -m pip install "codetracker-agent[server] @ git+https://github.com/William-StarX/Tracker.git"
codetracker-agent mcp --root /path/to/repo
```

生成宿主原生配置，复制合并到对应配置文件即可。命令会使用当前 Python 的完整路径，不修改个人设置：

```sh
codetracker-agent config codex --root /path/to/repo
codetracker-agent config claude-code --root /path/to/repo
codetracker-agent config cursor --root /path/to/repo
codetracker-agent config copilot --root /path/to/repo
```

另支持 `claude-desktop`、`vscode`。每个服务只公开本组件的两项分析工具，不公开下载/准备操作。[接入配置、超时与验证边界](docs/AGENTS.md)。

## HTTP 与远程调用

服务固定监听 `127.0.0.1`。设置 `JAVA_AGENT_TOKEN` 为至少 32 字符的随机令牌，然后运行：

```sh
codetracker-agent http --root /path/to/repo --port 8766
```

`GET /health`、`GET /tools`、`POST /invoke`、MCP Streamable HTTP `/mcp` 均要求 `Authorization: Bearer <token>`。令牌从环境变量读取，不写入命令参数或仓库。

```python
import os
from codetracker_agent import HTTPClient

client = HTTPClient("http://127.0.0.1:8766", os.environ["JAVA_AGENT_TOKEN"])
result = client.overview("/path/on/server/to/repo")
```

路径指服务所在机器的路径。跨机器部署需操作者自行配置带 TLS 的可信通道；本项目不提供公网匿名服务、用户管理或 OAuth 授权平台。

## 完整结果与资源开销

默认完整返回。`format="compact"` 必须同时设置 `output` 保存完整报告；服务还需显式配置 `--output-root`。已有文件不会被覆盖。不要把 `partial` 当作完整分析。

每个服务一次只运行一个分析，忙时返回 `BUSY`，避免并行 JVM 放大内存。Java 按请求启动，无常驻 JVM、数据库、GPU 或额外模型；HTTP/MCP 的 Python 依赖只在安装 `[server]` 时引入。Java 堆默认上限 2048 MiB，可设置 `memory_mb`，它不是整个进程树的内存限制。SDK/服务的便利性不意味着所有输入都更快或更省内存。

[API 与结果说明](docs/API.md) · [隐私与服务边界](PRIVACY.md) · [发布核验记录](docs/VERIFICATION.md)

## 从源码构建和测试

```sh
python -m pip install ".[server,test]"
python -m pytest
python -m build
```

测试覆盖 SDK、HTTP 权限与路径边界、MCP stdio/HTTP 协议、Agent 配置启动。构建输出 wheel 和 sdist；不包含第三方 JAR、项目数据、个人配置或分析缓存。
