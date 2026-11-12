# API 1.0

```python
from codetracker_agent import Client, HTTPClient, AnalysisResult, TransportError
client = Client()  # 可信本地调用；访问权限与当前进程相同
result = client.call("overview", repo="/path/to/repo")
catalog = client.describe()  # 工具名、参数 JSON Schema、响应 JSON Schema
```

`Client(allowed_roots=[...], output_root=...)` 启用与服务相同的路径检查。服务必须有项目根目录；SDK 的直接调用可不限制。路径支持字符串与 `pathlib.Path`。`prepare()`、`doctor()` 仅为本地 SDK/CLI 功能。

所有通道使用同一封装：

```json
{"interface_version":"1.0","operation":"overview","status":"ok","error":null,"result":{"status":"ok"},"process":{"exit_code":0,"stderr":""}}
```

上例仅展示封装，不代表完整组件报告。`result` 保留原始报告的所有字段。`status` 为 `ok`、`partial` 或 `error`；`error` 为 null 或 `{"code":"...","message":"..."}`。输入错误没有子进程结果时 `result`、`process` 为 null。`partial` 必须结合原报告的 warnings/limitations/截断标志解释。

常见错误：`INVALID_ARGUMENT`（参数不匹配）、`ACCESS_DENIED`（路径超范围）、`BUSY`（本实例正在分析）、`OPERATION_NOT_EXPOSED`（服务不提供准备等操作）。引擎错误代码原样保留；不能只依赖 HTTP 200 判断分析成功。`HTTPClient` 遇到连接、重定向或非协议响应抛出 `TransportError`。

HTTP 使用 `POST /invoke`，JSON 为 `{"operation":"overview","repo":"/path/on/server"}`。参数错误 HTTP 400，权限错误 403，忙时 429；引擎运行结果通常 HTTP 200 并带上述状态。认证失败 401，超大请求 413，非 JSON 请求 415。请求体上限 64 KiB；结果不因该请求限制被截短。

MCP 的 `tools/list` 返回相同参数/响应 Schema；`tools/call` 同时提供 JSON 文本与 `structuredContent` 以兼容不同客户端。分析错误设置 `isError=true`；`partial` 通过内容状态表示。MCP 工具参数中不包含 `operation`，工具名即操作名。

通用分析选项及各工具完整参数以 `codetracker-agent describe` 为准。`timeout` 是组件引擎超时，不是整个 HTTP 调用的截止时间。HTTPClient 默认 180 秒，可通过构造参数调高。Agent 宿主超时应大于引擎超时并留出准备输入和序列化时间。客户端取消连接不保证立即终止引擎；它会受自身超时约束，期间服务可返回 BUSY。

`memory_mb` 限制 Java 堆，`max_events` 限制返回历史事件，不限制全部历史遍历。并发控制仅覆盖同一 Client/服务实例；启动多个实例仍可能并行耗用资源。
