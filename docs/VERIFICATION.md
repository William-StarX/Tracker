# 1.4.0 发布核验

日期：2026-11-12。环境：Windows / Python 3.12.14 / Java 21，官方 MCP Python SDK 2.3.0。

## 已完成

- 从源码构建 sdist，再从 sdist 构建 wheel；实际安装 wheel 后运行测试，而非只检查源码导入。
- 本组件 **28 项测试通过、1 项跳过**。跳过项是操作系统不允许创建的符号链接测试；越界路径、父 Git 仓库、链接 Git 元数据和输出目录检查通过。
- 两个基础 wheel 另在全新环境安装，只包含两个组件分发包，没有 MCP、Uvicorn 或其它 Python 依赖。SDK 的 review、overview、trace 简洁方法在真实项目上可用。
- 六种 Agent 配置经过解析、真实进程启动、工具发现与调用；另验证 MCP 自动协商及传统 initialize 握手。此项属于协议/配置测试，不是六款宿主 UI 的逐款验收。
- 认证 HTTP 拒绝缺失/错误令牌、越界路径、Origin、错误 Host、过大/无效请求；HTTP 客户端拒绝重定向与非本机明文 HTTP。验证 BUSY、完整结果和 partial 状态传播。
- SDK、JSON CLI、HTTP SDK、MCP stdio、MCP Streamable HTTP 共五个入口，两项工具共 **10 次分析**。报告仅排除顶层 timings、generated_at，其他字段（包括全部证据、版本、目标、警告和限制）逐字段一致。可与旧 1.3.0 接口结果对应的用例也保持一致。
- 9 个随包组件源码/资源与既有 1.2 组件逐字节一致，见 [指纹清单](component-manifest.json)。Git 属性保留这些文件原始字节，避免换行转换影响引擎缓存指纹。

项目概览返回 partial：两个文件超过原有单文件扫描上限，测试框架线索按原有 100 条输出上限截断。所有入口均保留相同状态、限制、证据和数量；这不是全项目无遗漏扫描的证明。历史追踪返回 ok。

## 真实项目与复现

目标：[Apache Commons Lang](https://github.com/apache/commons-lang)。提交比较为 `567bcda3de4d8768a2dc1e3ffc567b5879a9a74f` → `b9b30efb01e861a16503232bb96b684107e73199`；历史追踪起点 `a36c903d4f1065bc59f5e6d2bb0f9d92a5e71d83`，`src/main/java/org/apache/commons/lang3/time/DateUtils.java:1009` 的局部变量 `aField`。

已有该完整 clone 并完成引擎 prepare 后：

```sh
python tools/verify_real_project.py --module codetracker_agent --repo /path/to/commons-lang --output /path/to/private-check-results
```

脚本不获取或切换目标提交、不构建目标项目。原始结果含本机路径与源码，留在操作者指定目录；公开仓库只保存 [脱敏核验汇总](verification.json)。

## 发布检查与限制

新增源码和构建产物扫描包括私钥/令牌模式、凭据 URL、私有主目录/聊天引用、已知本机标识以及不应随包发布的文件类型；结合人工检查，仅提交明确选定的源码、文档和测试。可复用 `tools/privacy_audit.py` 对 Git 暂存区与 wheel/sdist 检查。最终扫描记录保留在本地交付目录，避免扫描日志本身混入发布内容。

没有发布目标项目、原始报告、个人配置、环境文件、分析缓存或 JAR。旧初始提交的普通作者邮箱属于已存在的历史信息，本次保留历史；新增提交采用 GitHub noreply 邮箱。扫描不证明绝对无泄露风险，报告内容和宿主模型传输边界见 [PRIVACY.md](../PRIVACY.md)。

这轮是 SDK/服务封装与结果完整性验证，**不是重新测量相对作者原版的性能或准确率**；没有据此声称更快。跨系统 CI 已配置，本文只记录本机实际完成的检查。
