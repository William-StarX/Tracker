# 1.5.0 — 2026-11-12

- 为旧项目接管、缺陷/历史调查和结构概览更新提供主动调用规则。
- 通过 MCP 初始化 instructions 与 SDK/HTTP 工具目录交付相同规则和阶段元数据。
- 包含允许隐式调用的 Skill，新增 install-skill 命令和本机运行环境绑定；不覆盖已有技能。
- 不增加轮询、常驻 JVM 或项目数据库，不改变分析算法与报告接口。

# 1.4.0 — 2026-11-12

- 形成可独立安装、构建 wheel/sdist 的 SDK；保留接口版本 1.0 和完整组件结果。
- 增加本地/HTTP Client、JSON CLI、标准 MCP stdio/Streamable HTTP、认证 HTTP API。
- 提供 Codex、Claude Code/Desktop、Cursor、VS Code、Copilot 配置生成。
- 增加授权目录、报告目录、令牌、请求大小和单实例并发控制。
- 分析引擎保留已有 1.2 实现；没有在服务封装中裁剪证据或宣称新的算法性能提升。
