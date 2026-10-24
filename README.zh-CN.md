# Aether CLI

[English](README.md) · **简体中文**

基于 [Aether](https://github.com/ruifengc/aether) 的终端应用，提供连续对话、处理中补充输入、工具进度、查询与取消。运行机制由独立 Aether 库负责，本应用管理终端交互、配置发现、工具选择与展示。终端状态提示目前使用中文。

[详细用法](docs/usage.md) · [自定义工具示例](examples/extra_tools.py)

## 安装并使用真实 LLM

需要 Python 3.11+、Git 和 uv。安装到独立工具环境：

```bash
uv tool install git+https://github.com/ruifengc/aether-cli.git
```

使用 TokenHub 时，在环境中配置 `TOKENHUB_API_KEY` 或 `TENCENT_API_KEY`，然后运行：

```bash
aether --live --provider tencent --cwd .
```

这条路径实际调用模型。TokenHub 默认使用 `deepseek/deepseek-flash`，可用 `--model` 和 `--reasoning` 覆盖模型配置。直连 DeepSeek 使用 `--provider deepseek`，并设置 `DEEPSEEK_API_KEY`。`--cwd` 后必须提供目录参数，`.` 表示当前目录。

配置发现位于 `aether_cli.settings.load_settings`，进程环境优先于兼容的 `~/.hermes/.env` 文件；文件作为数据解析，不执行其中的 shell 内容。配置发现属于应用，Aether 库只接收显式配置。

安装包元数据和锁文件均固定依赖 Aether 公开 GitHub 仓库的一个提交。安装需要访问 GitHub 和包索引，不依赖内网 Gitea、本机兄弟源码目录或 PyPI 上的同名 `aether` 包。这两个项目目前尚未发布到 PyPI。

## 固定脚本演示

安装后运行：

```bash
aether --demo
aether --demo --debug
```

演示使用**固定 Python 规则与虚构资料，不执行 LLM 推理**：先查询设备资料，在工具运行期间追加150克重量条件，最后输出 `GAMMA`。它验证提交、工具执行、处理中补充和事件展示，不验证模型效果，也不具备通用自然语言理解能力。演示本身不发起网络请求，不需要模型凭据。

不带 `--live` 的交互模式同样使用这个固定模型；真实助手须指定 `--live`。`--debug` 展示完整事件与查询快照。

## 工具与终端命令

真实模式显式注册 Aether 的 `terminal`、`read_file`、`write_file`、`edit_file`、`search_files`，可用 `--no-builtin-tools` 关闭。进程工具目前面向 POSIX，命令依赖 Bash，检索依赖 `rg`。

通过可重复的 `--tools MODULE:FACTORY` 追加工具。工厂为无参数同步函数，返回 Aether `Tool` 的可迭代对象；handler 可以是同步函数或协程。在源码目录中可尝试：

```bash
uv run python -m aether_cli --live --tools examples.extra_tools:make_tools
```

| 命令 | 行为 |
| --- | --- |
| `/query` | 查看状态、操作次数与 token 用量 |
| `/cancel` | 请求取消当前工作 |
| `/new` | 开始新会话，已有工作继续运行 |
| `/help` | 查看终端命令 |
| `/quit` | 退出终端视图 |

输入与输出均为 TTY 时，支持中文编辑、输入历史、粘贴，以及后台输出期间保留草稿。Ctrl+C 清空草稿，Ctrl+D 退出；管道输入使用逐行读取。也可通过 `await aether_cli.run(agent)` 嵌入终端视图，传入实例仍由调用方管理。

## 源码开发

```bash
git clone https://github.com/ruifengc/aether-cli.git
cd aether-cli
uv sync --locked
uv run aether --demo
bash scripts/check.sh
uv build
```

在源码目录执行 `uv run aether --live --provider tencent --cwd .` 开始真实交互。`python -m aether_cli` 与安装后的 `aether` 命令等价。应用代码位于 `src/aether_cli`，运行机制保留在独立 Aether 库中。

检查包含工作区和实际 index 的凭据扫描、Ruff、19 项应用与终端测试，以及两种固定脚本演示。测试使用受控模型与真实伪终端，不请求真实模型。源码发行包包含两份 README、使用文档、示例、测试与检查脚本。

联合开发时，可以用 `uv add --editable ../aether` 临时覆盖固定依赖；提交前恢复已提交的依赖声明与锁文件。
