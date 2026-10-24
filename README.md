# Aether CLI

**English** · [简体中文](README.zh-CN.md)

A terminal application built on [Aether](https://github.com/ruifengc/aether), with continuous conversations, input while work is running, tool progress, queries and cancellation. Aether owns the runtime; this application owns terminal interaction, configuration discovery, tool selection and display. Terminal status messages currently use Chinese.

[Detailed usage (Chinese)](docs/usage.md) · [Custom tool example](examples/extra_tools.py)

## Install and use a real LLM

Requires Python 3.11+, Git and uv. Install into an isolated tool environment:

```bash
uv tool install git+https://github.com/ruifengc/aether-cli.git
```

For TokenHub, set `TOKENHUB_API_KEY` (or `TENCENT_API_KEY`) in your environment, then run:

```bash
aether --live --provider tencent --cwd .
```

This makes real model requests. TokenHub defaults to `deepseek/deepseek-flash`; `--model` and `--reasoning` override model settings. Direct DeepSeek access uses `--provider deepseek` and `DEEPSEEK_API_KEY`. `--cwd` requires a directory argument; `.` means the current directory.

Configuration is loaded by `aether_cli.settings.load_settings`. Process environment values take precedence over the compatible `~/.hermes/.env` file; the file is parsed as data rather than executed. This configuration discovery belongs to the application. The Aether library receives explicit settings.

The Aether dependency is pinned to a public GitHub commit in the package metadata and lockfile. Installation needs GitHub and package-index access, with no private Gitea server, sibling source directory or PyPI package named `aether` required. These projects are not yet published to PyPI.

## Scripted demo

After installation:

```bash
aether --demo
aether --demo --debug
```

The demo uses **fixed Python rules and fictional data, with no LLM inference**. It starts a device lookup, adds a 150-gram constraint while the tool is running, and finishes with `GAMMA`. This exercises submission, tool execution, incoming updates and event display; it does not measure model quality or provide general natural-language understanding. The demo itself makes no network requests and needs no model credentials.

Omitting `--live` also selects this scripted model in interactive mode. Use `--live` for a real assistant. `--debug` shows full events and query snapshots.

## Tools and terminal commands

Live mode explicitly registers Aether's `terminal`, `read_file`, `write_file`, `edit_file` and `search_files` tools. Disable them with `--no-builtin-tools`. Process tools currently target POSIX, with Bash for commands and `rg` for search.

Append your own tools with repeated `--tools MODULE:FACTORY` options. Each factory is a synchronous, no-argument function returning an iterable of Aether `Tool` objects; handlers may be synchronous or asynchronous. From a source checkout, try:

```bash
uv run python -m aether_cli --live --tools examples.extra_tools:make_tools
```

| Command | Behavior |
| --- | --- |
| `/query` | Show state and operation/token counts |
| `/cancel` | Request cancellation of current work |
| `/new` | Start a new conversation; existing work continues |
| `/help` | Show terminal commands |
| `/quit` | Exit the terminal view |

When both streams are TTYs, line editing supports Chinese input, history, paste and draft preservation during background output. Ctrl+C clears the draft; Ctrl+D exits. Piped input uses line-based reading. The terminal view can also be embedded with `await aether_cli.run(agent)`; the caller retains ownership of the supplied Agent.

## Develop from source

```bash
git clone https://github.com/ruifengc/aether-cli.git
cd aether-cli
uv sync --locked
uv run aether --demo
bash scripts/check.sh
uv build
```

`uv run aether --live --provider tencent --cwd .` starts real interaction from the checkout. `python -m aether_cli` is equivalent to the installed `aether` command. Importable application code lives in `src/aether_cli`; runtime code stays in the independent Aether library.

Checks cover worktree and index credential scans, Ruff, 19 application/terminal tests and both scripted demos. Tests use controlled models and real pseudoterminals, with no live-model requests. Source distributions include both READMEs, usage documentation, examples, tests and check scripts.

For joint local development, `uv add --editable ../aether` temporarily replaces the pinned dependency; restore the committed dependency and lockfile before submitting changes.
