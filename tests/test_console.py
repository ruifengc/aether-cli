from __future__ import annotations

import asyncio
import io
import json
import os
import pty
import sys
import tempfile
import termios
import unittest
from pathlib import Path
from unittest.mock import patch

from aether import Agent, Decision, Event
from tests_helper import ControlledModel

from aether_cli import app, console


def event(kind, **data):
    return Event("abcdef1234", 1, kind, data, 0)


class PresentationTests(unittest.TestCase):
    def test_answers_keep_newlines_and_tool_bodies_do_not_flood_normal_output(self):
        output = io.StringIO()
        with patch("sys.stdout", output):
            console.show(event("model.completed", usage={"prompt_tokens": 100}))
            console.show(event("tool.started", name="write_file", arguments={
                "path": "note.txt", "content": "large implementation " * 1000}))
            console.show(event("input.accepted", source="tool", name="read_file",
                               content={"content": "large result " * 1000}))
            console.show(event("output", content="第一行\n\n```python\nprint(42)\n```"))
            console.show(event("run.succeeded", output="不应重复展示"))
        text = output.getvalue()
        self.assertIn("第一行\n\n```python\nprint(42)\n```", text)
        self.assertIn("write_file · note.txt", text)
        for hidden in ("large implementation", "large result", "prompt_tokens", "run.succeeded",
                       "不应重复展示"):
            self.assertNotIn(hidden, text)
        self.assertLess(len(text), 300)

    def test_errors_waiting_cancellation_and_recovery_remain_visible(self):
        output = io.StringIO()
        with patch("sys.stdout", output):
            console.show(event("output", content="要读取哪个文件？"))
            console.show(event("input.accepted", source="tool", name="terminal",
                               content={"exit_code": 7, "truncated": True}))
            console.show(event("input.accepted", source="tool", name="read_file",
                               content={"error": "file not found"}))
            console.show(event("model.retrying", attempt=1, reason="model HTTP 503"))
            console.show(event("context.compacting", through=0))
            console.show(event("run.failed", error="recovery_exhausted"))
            console.show(event("run.cancelled"))
        text = output.getvalue()
        for expected in ("要读取哪个文件？", "退出码 7", "输出已限额", "file not found",
                         "重试", "整理", "recovery_exhausted", "已取消"):
            self.assertIn(expected, text)

    def test_debug_keeps_full_event_data_and_query_snapshot(self):
        snapshot = {"run_id": "abcdef", "output": "原文\n第二行", "usage": {"prompt_tokens": 10}}
        output = io.StringIO()
        with patch("sys.stdout", output):
            console.show(event("input.consumed", source="user", seq=9), debug=True)
            console.show_query(snapshot, debug=True)
        lines = output.getvalue().splitlines()
        self.assertIn("input.consumed", lines[0])
        self.assertEqual(json.loads(lines[1]), snapshot)


class ConsoleTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_subscription_replays_without_duplicate_answers(self):
        model = ControlledModel()
        async with Agent(model) as agent:
            receipt = await agent.submit("start")
            for i in range(100):
                await agent.submit(str(i), run_id=receipt.run_id)
            _, answer = await model.next()
            answer.set_result(Decision("done"))
            await agent.wait(receipt.run_id, timeout=1)
            events = []
            with patch.object(app, "show", side_effect=lambda item, **_: events.append(item)):
                await app.display(agent, receipt.run_id)
            self.assertEqual([e.seq for e in events], list(range(1, len(events) + 1)))
            self.assertEqual(sum(e.type == "run.succeeded" for e in events), 1)
            self.assertGreater(len(events), 128)

    async def test_human_query_is_read_only_and_does_not_dump_history(self):
        model = ControlledModel()
        async with Agent(model) as agent:
            receipt = await agent.submit("private history marker")
            _, answer = await model.next()
            answer.set_result(Decision("done"))
            result = await agent.wait(receipt.run_id, timeout=1)
            output = io.StringIO()
            with patch("sys.stdout", output):
                console.show_query(result)
            self.assertIn("已完成", output.getvalue())
            self.assertNotIn("private history marker", output.getvalue())
            self.assertEqual(agent.query(receipt.run_id)["model_calls"], result["model_calls"])

    async def test_tty_keeps_chinese_draft_across_async_output_and_restores_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory) / "inputs.jsonl"
            program = '''
import asyncio,json,sys
from pathlib import Path
from aether import Agent,Decision
from aether_cli import run
class Model:
    async def decide(self,snapshot,tools):
        text=snapshot['inputs'][-1]['content']
        with Path(sys.argv[1]).open('a') as stream:
            stream.write(json.dumps(text,ensure_ascii=False)+'\\n')
        if text=='first':
            await asyncio.sleep(.3)
            return Decision('FIRST_RESPONSE')
        return Decision('SECOND_RESPONSE')
async def main():
    async with Agent(Model()) as agent:
        await run(agent)
asyncio.run(main())
'''
            master, slave = pty.openpty()
            original = termios.tcgetattr(slave)
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-u", "-c", program, str(record), stdin=slave, stdout=slave,
                stderr=slave, env={**os.environ, "TERM": "xterm-256color",
                                  "PROMPT_TOOLKIT_NO_CPR": "1"})
            transcript = bytearray()
            loop = asyncio.get_running_loop()

            async def until(marker):
                try:
                    async with asyncio.timeout(5):
                        while marker not in transcript:
                            ready = loop.create_future()
                            loop.add_reader(master, lambda future=ready: not future.done()
                                            and future.set_result(None))
                            try:
                                await ready
                                transcript.extend(os.read(master, 65536))
                            finally:
                                loop.remove_reader(master)
                except TimeoutError:
                    self.fail(f"Missing {marker!r}; output: {bytes(transcript)!r}")

            try:
                await until(b">")
                os.write(master, b"first\r")
                await until("正在处理".encode())
                os.write(master, "项目你放到了".encode() + b"\x7f" + "哪个目录🙂".encode())
                await until(b"FIRST_RESPONSE")
                os.write(master, b"\x7f" + "？\r".encode())
                await until(b"SECOND_RESPONSE")
                # Interrupt an unfinished draft without closing the running view.
                os.write(master, b"unused\x03")
                await asyncio.sleep(.05)
                os.write(master, b"/quit\r")
                await asyncio.wait_for(process.wait(), 5)
                inputs = [json.loads(line) for line in record.read_text().splitlines()]
                self.assertEqual(inputs, ["first", "项目你放到哪个目录？"])
                self.assertEqual(process.returncode, 0)
                self.assertEqual(termios.tcgetattr(slave), original)
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
                os.close(master)
                os.close(slave)
