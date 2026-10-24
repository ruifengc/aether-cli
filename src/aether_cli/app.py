"""Terminal I/O and application composition; the kernel does not import this package."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect

from aether import Agent, ContextPolicy, Limits, SubscriptionOverflow, Tool
from aether.chat import ChatModel
from aether.tools import MAX_TIMEOUT, local_tools

from .console import read_lines, show, show_query
from .settings import load_settings


def load_tools(specs):
    """Load explicit, ordinary Python factories; each returns an iterable of Tool."""
    tools = []
    for spec in specs:
        module_name, separator, attribute = spec.partition(":")
        if not separator or not module_name or not attribute:
            raise ValueError("tool provider must be MODULE:FACTORY")
        factory = getattr(importlib.import_module(module_name), attribute)
        if not callable(factory) or inspect.iscoroutinefunction(factory):
            raise TypeError("tool factory must be a synchronous callable returning Tool objects")
        provided = list(factory())
        if not all(isinstance(tool, Tool) for tool in provided):
            raise TypeError("tool factory must return an iterable of Tool objects")
        tools.extend(provided)
    return tools


async def display(agent, run_id, *, debug=False):
    cursor = 0
    while True:
        sub = agent.subscribe(run_id, after=cursor)
        try:
            async for event in sub:
                show(event, debug=debug)
                cursor = event.seq
        except SubscriptionOverflow:
            snapshot = agent.query(run_id, after=cursor)
            for event in snapshot["events"]:
                show(event, debug=debug)
            cursor = snapshot["cursor"]
            if snapshot["state"] in {"succeeded", "failed", "cancelled"}:
                return
        else:
            return
        finally:
            sub.close()


async def run(agent: Agent, *, debug: bool = False):
    """Use an application-owned Agent; this function never builds or closes it."""
    help_text = "/query 查看状态 · /cancel 取消当前工作 · /new 新会话 · /quit 退出"
    print(f"输入消息连续对话；{help_text}。", flush=True)
    current = conversation = None
    watchers = set()
    reader = read_lines()
    try:
        async for line in reader:
            text = line.strip()
            if not text:
                continue
            if text == "/quit":
                break
            if text == "/help":
                print(help_text, flush=True)
                continue
            if text == "/new":
                current = conversation = None
                print("已开始新会话。", flush=True)
                continue
            if text == "/query":
                show_query(agent.query(current) if current else None, debug=debug)
                continue
            if text == "/cancel":
                if current:
                    await agent.cancel(current)
                else:
                    print("当前没有工作。", flush=True)
                continue
            try:
                receipt = await agent.submit(text, conversation_id=conversation)
            except ValueError as exc:
                print(f"提交未接收：{exc}", flush=True)
                continue
            conversation = receipt.conversation_id
            if current != receipt.run_id:
                current = receipt.run_id
                task = asyncio.create_task(display(agent, current, debug=debug))
                watchers.add(task)
                task.add_done_callback(watchers.discard)
                if not debug:
                    print("正在处理…", flush=True)
            elif not debug:
                print("已收到补充。", flush=True)
            if debug:
                print(f"accepted run={receipt.run_id} input={receipt.input_version}", flush=True)
    finally:
        await reader.aclose()
        for task in watchers:
            task.cancel()
        await asyncio.gather(*watchers, return_exceptions=True)


async def main(args, *, tools=()):
    """Compose this CLI's model and tools through public library interfaces."""
    registered = [*tools, *load_tools(args.tools)]
    input_bytes = getattr(args, "context_bytes", None)
    if args.demo or not args.live:
        from .demo import DemoModel, demonstrate, make_tools

        registered = [*make_tools(), *registered]
    if args.live:
        if not args.no_builtin_tools:
            registered = [*local_tools(args.cwd), *registered]
        settings = load_settings(provider=args.provider, model=args.model, reasoning=args.reasoning)
        # These routes advertise 1M tokens; the application keeps a conservative byte cap.
        if input_bytes is None and (settings.provider, settings.model) in {
            ("tencent", "deepseek/deepseek-flash"),
            ("tencent", "deepseek-v4.1-flash"),
            ("tencent", "deepseek-v4.1-flash-1017"),
            ("deepseek", "deepseek-flash"),
        }:
            input_bytes = 800000
        model = ChatModel(settings)
        print(f"模型：{settings.model} · {settings.reasoning or '默认档位'}", flush=True)
    else:
        model = DemoModel()
        print("离线演示：工具运行期间可补充150克重量条件。", flush=True)
    context = ContextPolicy(input_bytes=input_bytes) if input_bytes is not None else None
    async with Agent(model, registered, limits=Limits(tool_timeout=MAX_TIMEOUT + 10),
                     context=context, system_prompt="Answer concisely.") as agent:
        if args.demo:
            await demonstrate(agent, lambda run_id: display(agent, run_id, debug=args.debug))
        else:
            await run(agent, debug=args.debug)


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Use configured real model")
    parser.add_argument("--demo", action="store_true", help="Run a bounded demonstration and exit")
    parser.add_argument("--debug", action="store_true", help="Print full events and query snapshots")
    parser.add_argument("--provider", choices=("tencent", "deepseek"))
    parser.add_argument("--model")
    parser.add_argument("--reasoning", default="high")
    parser.add_argument("--cwd", default=".", help="Base directory for built-in local tools")
    parser.add_argument("--context-bytes", type=int,
                        help="Conservative input byte budget; known DeepSeek Flash 1M routes use 800000")
    parser.add_argument("--no-builtin-tools", action="store_true",
                        help="Register only explicitly provided tools")
    parser.add_argument("--tools", action="append", default=[], metavar="MODULE:FACTORY",
                        help="Append tools from an importable Python factory; repeatable")
    args = parser.parse_args(argv)
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        pass
    except (ImportError, AttributeError, TypeError, ValueError) as exc:
        parser.error(str(exc))
