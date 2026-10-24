# Aether CLI 使用说明

## CLI 应用与工具扩展

入口由 aether-cli 提供：`uv run python -m aether_cli` 或 `uv run aether`。kernel 包没有 CLI 入口。`--live` 使用真实模型，默认 high；真实交互显式注册 Aether 提供的五种本地工具，--no-builtin-tools 关闭默认工具但仍加载用户追加工具，--cwd PATH 设置工具路径基准。省略 --live 使用固定脚本，--demo 运行一次有界演示；演示模型、资料和 catalog 工具仅在 CLI 包中。

默认保留回答与提问的真实换行，只显示工具名称、目标和简短完成或错误状态，不展开工具正文。`--debug` 显示完整运行事件，并让 `/query` 输出原始 JSON 快照；普通 `/query` 只显示工作状态、操作次数与 token 用量。两种模式都只观察，不触发模型调用。持续展示统一使用订阅，溢出后按游标查询补齐。

通过 `--tools MODULE:FACTORY` 启动时追加工具，可重复指定。模块需可导入，工厂是无参数同步函数，返回 `Tool` 的可迭代对象；工具 handler 本身可以同步或异步。多处配置的工具合并后交给 Agent，同名工具由库校验，await_input 名称冲突由默认模型适配器在请求前检查，不隐式覆盖。

例：从项目根目录执行 `uv run python -m aether_cli --live --tools examples.extra_tools:make_tools`，注册示例乘法工具。examples 是仓库示例，不随发行包安装；使用命令入口 aether 加载外部工具时，工具模块需要已经安装或位于 Python 模块路径中。只执行用户显式指定的工厂，没有自动发现或独立插件框架。

应用也可自行构造实例，再使用终端视图：

```python
from aether import Agent
from aether_cli import run

async with Agent(my_model, tools=my_tools) as agent:
    await run(agent)
```

`run(agent, debug=False)` 不构造模型、不追加工具、不关闭传入的实例。CLI 启动组装函数 `aether_cli.app.main(args, tools=...)` 也接受应用直接提供的工具。`/query`、`/cancel`、`/new`、`/quit` 和 `/help` 属于终端命令，不进入 kernel 的业务协议；/new 不取消旧工作，输出以短工作 ID 区分。退出终端视图只清理展示任务，调用方仍可继续使用实例。

标准输入、输出均为 TTY 时使用异步行编辑，支持中文退格、方向键、会话内输入历史和粘贴；后台输出显示在输入框上方，保留草稿。Ctrl+C 清空草稿，/cancel 取消工作，Ctrl+D 或 /quit 退出视图。终端模式退出后恢复，输入历史不写文件。其他输入输出组合使用标准库逐行读取，支持管道批量多行、跨块 UTF-8 和 EOF 无换行末行；非法编码只拒收当前行并提示重输。终端视图不会关闭调用方 stdin。

## 模型配置与应用默认值

配置由 aether_cli.settings.load_settings 从显式选项和当前进程允许的环境变量中读取，不查找或读取任何配置文件，也不写回环境变量。缺少所选供应商凭据时明确报错；环境由宿主 shell 或启动器提供。支持 tencent / deepseek 路由；默认使用 TokenHub Flash，CLI 的默认回答风格为 Answer concisely.。

--context-bytes 覆盖输入字节预算。CLI 对已确认的 Flash 1M 路由默认使用 input_bytes=800000，为输出与包装留余量；未知路由采用库的通用默认。模型窗口和字节预算是两个量，不宣称该预算利用满 1M tokens。

CLI 为本地工具设置 130 秒的外层超时，容纳最长 120 秒命令及清理；kernel 的 Limits 默认仍为 30 秒。

## 安装来源与演示范围

Aether 依赖通过公开 GitHub 仓库的固定提交安装，pyproject.toml 与 uv.lock 使用同一来源；不需要访问内网 Gitea，也不要求本机存在库的源码目录。当前从 GitHub 安装，尚未发布到 PyPI。

`aether --demo` 使用 DemoModel 的固定 Python 规则与虚构设备资料，不执行 LLM 推理。它先提交资料查询，再在工具执行期间追加150克重量条件，最后输出 GAMMA；用于验证工具执行、途中补充、事件展示与结果回流。未指定 --live 的交互模式同样使用固定规则，不是通用自然语言助手。初次安装依赖需要网络；环境准备好后，演示本身不发起网络请求。

使用真实模型须指定 --live，并配置所选供应商的凭据。演示、单元测试与伪终端测试不能替代真实模型效果验证。
