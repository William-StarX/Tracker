# 来源与许可

本仓库是独立的定制组件，不是论文作者官方项目。Python SDK、命令行、项目概览、Java bridge、服务和接入配置由本项目提供；核心分析来源如下。

- RefactoringMiner：作者 [tsantalis/RefactoringMiner](https://github.com/tsantalis/RefactoringMiner)，固定 Maven `com.github.tsantalis:refactoring-miner:3.0.11`。
- CodeTracker（仅 Tracker 仓库）：作者 [jodavimehran/code-tracker](https://github.com/jodavimehran/code-tracker)，固定 Maven `io.github.jodavimehran:code-tracker:3.0`。
- 两个组件均保留 1.2 版本的两处局部优化：`StringDistance.java` 的等价 UTF-16 编辑距离计算，以及 `ReplacementUtil.keepReservedTokens` 的等价字符比较。它们是作者类的修改副本，**不能宣称所有底层实现完全未经修改**。原 MIT 版权许可位于 [LICENSES/RefactoringMiner-MIT.txt](LICENSES/RefactoringMiner-MIT.txt)，并随 Java bridge 资源打包。

本源码包与 wheel 不携带完整作者仓库或第三方 JAR；显式 prepare 时才下载实际依赖。Java POM 固定分析库与构建插件版本，Maven 3.9.11 下载校验摘要；传递依赖并非仅遵循一个统一许可证。服务额外使用官方 MCP Python SDK 2.3.0 和 Uvicorn，依赖由安装器下载，不复制其实现到源码中。

CodeTracker 的固定版本存在上游许可元数据差异：[源码 e85f5b9 的 LICENSE](https://github.com/jodavimehran/code-tracker/blob/e85f5b9352622f87a38e74c85018cddda3e1a900/LICENSE) 为 GPLv3，而 [Maven 3.0 POM](https://repo.maven.apache.org/maven2/io/github/jodavimehran/code-tracker/3.0/code-tracker-3.0.pom) 标注 MIT。本项目记录该差异，不替上游作许可结论，也不分发组合引擎二进制。子进程方式本身不解决许可问题。

仓库原先没有自有代码的开源许可证，本次没有擅自为仓库全部代码授予新许可。`LICENSES` 中的第三方许可证仅适用于对应来源文件，不代表全仓库统一许可证。
