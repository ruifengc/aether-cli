"""Terminal input and presentation; independent of model and runtime scheduling."""

from __future__ import annotations

import asyncio
import json
import os
import sys


async def read_lines():
    if sys.stdin.isatty() and sys.stdout.isatty():
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.patch_stdout import patch_stdout
        except ImportError:
            raise ImportError("交互终端需要 cli 扩展，请先运行 uv sync --all-extras") from None

        session = PromptSession()
        with patch_stdout():
            while True:
                try:
                    line = await session.prompt_async("> ")
                except EOFError:
                    return
                except KeyboardInterrupt:
                    continue  # Clear the draft; /cancel controls the running work.
                if any(0xD800 <= ord(char) <= 0xDFFF for char in line):
                    print("输入未接收：编码无效，请重新输入这一行。", file=sys.stderr, flush=True)
                    continue
                yield line
        return

    # Read bytes directly: TextIO read-ahead can hide batched pipe lines from add_reader.
    loop = asyncio.get_running_loop()
    descriptor = sys.stdin.fileno()
    encoding = sys.stdin.encoding or "utf-8"
    pending = b""
    while True:
        if b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            line += b"\n"
        else:
            ready = loop.create_future()

            def readable(future=ready):
                loop.remove_reader(descriptor)
                if not future.done():
                    future.set_result(None)

            loop.add_reader(descriptor, readable)
            try:
                await ready
            finally:
                loop.remove_reader(descriptor)
            chunk = os.read(descriptor, 4096)
            if chunk:
                pending += chunk
                continue
            if not pending:
                return
            line, pending = pending, b""
        try:
            decoded = line.decode(encoding)
        except UnicodeDecodeError:
            print(f"输入未接收：无法按 {encoding} 解码，请重新输入这一行。",
                  file=sys.stderr, flush=True)
            continue
        yield decoded


def brief(value, limit=120):
    text = " ".join("".join(c if c.isprintable() else " " for c in str(value)).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def show(event, *, debug=False):
    data, kind = event.data, event.type
    if debug:
        print(f"[{event.run_id[:8]} {event.seq} {kind}] "
              f"{json.dumps(data, ensure_ascii=False)}", flush=True)
        return
    label = event.run_id[:6]  # Distinguish an older run still finishing after /new.
    if kind == "output":
        print(f"\n助手 [{label}]：\n{data['content']}\n", flush=True)
    elif kind == "tool.started":
        args = data.get("arguments", {})
        target = next((args[key] for key in ("command", "path", "pattern") if key in args), "")
        print(f"工具 [{label}] {data['name']}" + (f" · {brief(target)}" if target else ""),
              flush=True)
    elif kind == "input.accepted" and data.get("source") == "tool":
        result = data["content"]
        status = "完成"
        if isinstance(result, dict):
            if "error" in result:
                status = f"失败：{brief(result['error'])}"
            elif result.get("timed_out"):
                status = "超时"
            elif result.get("no_matches"):
                status = "无匹配"
            elif result.get("exit_code") not in (None, 0):
                status = f"退出码 {result['exit_code']}"
                if result.get("stderr"):
                    status += f"：{brief(result['stderr'])}"
            if result.get("truncated"):
                status += "（输出已限额）"
        print(f"工具 [{label}] {data['name']} · {status}", flush=True)
    elif kind == "model.retrying":
        print(f"处理 [{label}] 正在重试模型请求（第 {data['attempt']} 次）："
              f"{brief(data['reason'])}", flush=True)
    elif kind == "context.compacting":
        print(f"处理 [{label}] 正在整理较早的对话…", flush=True)
    elif kind == "run.failed":
        print(f"处理 [{label}] 失败：{data.get('error') or '未知错误'}", flush=True)
    elif kind == "run.cancelled":
        print(f"处理 [{label}] 已取消。", flush=True)


def show_query(snapshot, *, debug=False):
    if debug:
        print(json.dumps(snapshot or {"run": None}, ensure_ascii=False), flush=True)
        return
    if snapshot is None:
        print("当前没有工作。", flush=True)
        return
    state = {"ready": "就绪", "running": "处理中", "waiting": "等待", "succeeded": "已完成",
             "failed": "失败", "cancelled": "已取消"}[snapshot["state"]]
    phase = {"deciding": "模型思考中", "compacting": "整理对话中", "retrying": "等待重试"}
    detail = phase.get(snapshot["phase"], "")
    if not detail and snapshot.get("waiting_for"):
        detail = f"等待 {len(snapshot['waiting_for'])} 个关键结果 · 共 {len(snapshot['pending'])} 个工具"
    elif not detail and snapshot["pending"]:
        detail = f"{len(snapshot['pending'])} 个工具运行中"
    if not detail and snapshot["state"] == "waiting":
        detail = "等待新消息"
    usage = snapshot["usage"]
    print(f"工作 {snapshot['run_id'][:6]} · {state}" + (f" · {detail}" if detail else ""),
          flush=True)
    print(f"模型 {snapshot['model_calls']} 次 · 工具 {snapshot['tool_calls']} 次 · "
          f"摘要 {snapshot['summary_calls']} 次 · 恢复 {snapshot['recoveries']} 次\n"
          f"输入 {usage['prompt_tokens']} / 输出 {usage['completion_tokens']} tokens"
          + ("（用量不完整）" if not usage["known"] else ""), flush=True)
    if snapshot["error"]:
        print(f"原因：{snapshot['error']}", flush=True)
