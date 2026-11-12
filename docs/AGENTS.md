# Agent 接入

优先使用 MCP stdio：无监听端口、无需服务令牌。各宿主启动 `codetracker-agent mcp --root <项目目录>`，即获得本组件的两个工具。也可直接使用 Python SDK、JSON CLI 或认证 HTTP API。

| 配置目标 | 生成命令中的 agent | 配置位置与结构 |
|---|---|---|
| Codex | `codex` | 用户 `~/.codex/config.toml` 的 `[mcp_servers.<名称>]` |
| Claude Code | `claude-code` | 项目 `.mcp.json`，顶层 `mcpServers` |
| Claude Desktop | `claude-desktop` | 桌面客户端 MCP 配置，顶层 `mcpServers` |
| Cursor | `cursor` | `.cursor/mcp.json`，顶层 `mcpServers` |
| VS Code 编辑器兼容格式 | `vscode` | `.vscode/mcp.json`，顶层 `servers`、type 为 stdio |
| GitHub Copilot 原生 Agent | `copilot` | `.mcp.json` 或 `~/.copilot/mcp-config.json`，顶层 `mcpServers` |

```sh
codetracker-agent config codex --root /path/to/repo --java-home /path/to/jdk --cache-dir /path/to/cache
```

`--root` 可重复；`--output-root` 单独授权报告目录。生成器只把明确传入的 Java/cache 路径放进 env，不收集模型密钥或其它环境变量。需要先在相同 Java/cache 环境运行 `prepare`。生成的配置可能包含本机路径，应作为本地配置保管，**不要直接提交到公开仓库**。

Codex 配置设置启动超时 30 秒、工具超时 600 秒。其它宿主按其设置调整工具超时。配置片段应合并到现有配置，不要覆盖已有服务。GUI 宿主的信任提示和启用步骤由宿主管理。

验证分层：本仓库测试会解析六种配置，并用其真实 command/args/env 启动子进程，通过官方 MCP 客户端执行工具发现和调用。这验证配置结构与启动协议；**不声称已在六款 GUI/Agent 产品中分别完成端到端任务**。同一协议能被更多 Agent 使用，但宿主必须支持相应 MCP 版本或本地命令调用。

HTTP MCP 地址为 `http://127.0.0.1:8766/mcp`，需配置 Authorization Bearer 请求头。优先让宿主从环境变量或其凭据存储读取令牌，避免把真实令牌写入共享配置。本服务没有 OAuth 自动登录流程。

官方配置依据（2026-11-12 核对）：[Codex](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)、[Claude Code](https://code.claude.com/docs/en/mcp)、[Cursor](https://cursor.com/docs/mcp)、[VS Code/Copilot](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)。MCP 使用 [官方 Python SDK](https://py.sdk.modelcontextprotocol.io/) 2.3.0；stdio 测试同时覆盖传统 initialize 握手，避免仅验证新客户端的自动发现流程。
