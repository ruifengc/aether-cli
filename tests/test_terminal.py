from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from aether import Agent, Call, Decision, Tool
from aether.chat import Settings
from tests_helper import ControlledModel

from aether_cli import app as terminal


class TerminalTests(unittest.IsolatedAsyncioTestCase):
    async def test_cli_can_disable_builtins_and_keeps_custom_tools(self):
        captured = []
        provider = types.ModuleType("test_selected_tools")
        provider.make_tools = lambda: [Tool("custom", "", {}, lambda: 1)]

        async def view(agent, **kwargs):
            captured.extend(agent.tools)

        with (patch.object(terminal, "run", view), patch.object(terminal, "load_settings"),
              patch.object(terminal, "ChatModel"), patch("builtins.print"),
              patch.dict(sys.modules, {provider.__name__: provider})):
            await terminal.main(SimpleNamespace(live=True, demo=False, provider="tencent", model=None,
                reasoning="high", no_builtin_tools=True, cwd=".",
                tools=["test_selected_tools:make_tools"], debug=False))
        self.assertEqual(captured, ["custom"])

    async def test_live_context_budget_uses_known_route_and_preserves_explicit_override(self):
        for model_name, override, expected in (
                ("deepseek/deepseek-flash", None, 800000),
                ("deepseek/deepseek-flash", 70000, 70000),
                ("unknown-small-model", None, None)):
            with self.subTest(model=model_name, override=override):
                args = argparse.Namespace(live=True, provider="tencent", model=model_name,
                    reasoning="high", demo=False, debug=False, tools=[], cwd=".",
                    no_builtin_tools=True, context_bytes=override)

                async def quit_immediately():
                    yield "/quit\n"

                with (patch.object(terminal, "load_settings", return_value=Settings(
                        "test-credential", "https://model.invalid/v1", model_name, "tencent")),
                      patch.object(terminal, "ChatModel", return_value=ControlledModel()),
                      patch.object(terminal, "Agent", wraps=Agent) as construct,
                      patch.object(terminal, "read_lines", quit_immediately), patch("builtins.print")):
                    await terminal.main(args)
                    policy = construct.call_args.kwargs["context"]
                    self.assertEqual(policy.input_bytes if policy else None, expected)

    async def test_invalid_input_line_is_rejected_and_later_lines_survive(self):
        for errors in ("strict", "surrogateescape"):
            with self.subTest(errors=errors):
                descriptor, writer = os.pipe()
                with (os.fdopen(descriptor, encoding="utf-8", errors=errors) as stream,
                      patch("sys.stdin", stream), patch("sys.stderr") as diagnostics):
                    reader = terminal.read_lines()
                    try:
                        os.write(writer, b"broken\xe4\xba\n" + "项目在哪？\n/query\n/quit\n".encode())
                        for expected in ("项目在哪？\n", "/query\n", "/quit\n"):
                            self.assertEqual(await asyncio.wait_for(anext(reader), 1), expected)
                        self.assertIn("输入未接收", "".join(
                            call.args[0] for call in diagnostics.write.call_args_list))
                    finally:
                        await reader.aclose()
                        os.close(writer)

    async def test_invalid_unterminated_eof_line_is_rejected_without_crashing(self):
        descriptor, writer = os.pipe()
        with (os.fdopen(descriptor, encoding="utf-8") as stream, patch("sys.stdin", stream),
              patch("sys.stderr") as diagnostics):
            reader = terminal.read_lines()
            os.write(writer, b"broken\xe4\xba")
            os.close(writer)
            try:
                with self.assertRaises(StopAsyncIteration):
                    await asyncio.wait_for(anext(reader), 1)
                self.assertTrue(diagnostics.write.called)
            finally:
                await reader.aclose()

    async def test_invalid_line_between_turns_keeps_conversation_and_accepts_retry(self):
        descriptor, writer = os.pipe()
        events = asyncio.Queue()
        model = ControlledModel()
        with (os.fdopen(descriptor, encoding="utf-8", errors="surrogateescape") as stream,
              patch("sys.stdin", stream),
              patch.object(terminal, "show", side_effect=lambda event, **_: events.put_nowait(event)),
              patch("builtins.print")):
            async with Agent(model) as agent:
                task = asyncio.create_task(terminal.run(agent))
                try:
                    os.write(writer, "生成 LRU\n".encode())
                    first, answer = await model.next()
                    answer.set_result(Decision("created in /tmp/example-lru"))
                    async with asyncio.timeout(1):
                        while (await events.get()).type != "run.succeeded":
                            pass
                    os.write(writer, b"bad\xe4\xba\n" + "项目放到哪个目录？\n".encode())
                    second, answer = await model.next()
                    self.assertEqual(second["conversation_id"], first["conversation_id"])
                    self.assertEqual(second["inputs"][0]["content"], "项目放到哪个目录？")
                    self.assertEqual(len(second["context"]["messages"]), 3)
                    self.assertIn("/tmp/example-lru", second["context"]["messages"][-2]["content"])
                    answer.set_result(Decision("/tmp/example-lru"))
                    async with asyncio.timeout(1):
                        while (await events.get()).type != "run.succeeded":
                            pass
                    os.write(writer, b"/quit\n")
                    await asyncio.wait_for(task, 1)
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    os.close(writer)

    async def test_batched_pipe_lines_are_available_without_closing_writer(self):
        descriptor, writer = os.pipe()
        with os.fdopen(descriptor, encoding="utf-8") as stream, patch("sys.stdin", stream):
            reader = terminal.read_lines()
            try:
                os.write(writer, "/query\n中文🙂\n/quit\n".encode())
                for expected in ("/query\n", "中文🙂\n", "/quit\n"):
                    self.assertEqual(await asyncio.wait_for(anext(reader), 1), expected)
                await reader.aclose()
                os.fstat(stream.fileno())  # The caller still owns stdin.
            finally:
                await reader.aclose()
                os.close(writer)

    async def test_multibyte_input_across_chunks_and_final_unterminated_line(self):
        descriptor, writer = os.pipe()
        with os.fdopen(descriptor, encoding="utf-8") as stream, patch("sys.stdin", stream):
            reader = terminal.read_lines()
            line = "x" * 4095 + "🙂资料\n"
            try:
                os.write(writer, (line + "tail").encode())
                os.close(writer)
                writer = None
                self.assertEqual(await asyncio.wait_for(anext(reader), 1), line)
                self.assertEqual(await asyncio.wait_for(anext(reader), 1), "tail")
                with self.assertRaises(StopAsyncIteration):
                    await anext(reader)
            finally:
                await reader.aclose()
                if writer is not None:
                    os.close(writer)

    async def test_followup_keeps_history_and_new_starts_an_independent_conversation(self):
        lines, events = asyncio.Queue(), asyncio.Queue()
        model = ControlledModel()

        async def read_lines():
            while True:
                yield await lines.get()

        async def next_success():
            async with asyncio.timeout(1):
                while True:
                    event = await events.get()
                    if event.type == "run.succeeded":
                        return

        with (patch.object(terminal, "read_lines", read_lines),
              patch.object(terminal, "show", side_effect=lambda event, **_: events.put_nowait(event)),
              patch("builtins.print")):
            async with Agent(model) as agent:
                task = asyncio.create_task(terminal.run(agent))
                try:
                    lines.put_nowait("remember A\n")
                    first, answer = await model.next()
                    answer.set_result(Decision("A is lighter"))
                    await next_success()
                    lines.put_nowait("choose the lighter one\n")
                    second, answer = await model.next()
                    self.assertEqual(first["conversation_id"], second["conversation_id"])
                    self.assertEqual(second["context"]["messages"][-2]["content"], "A is lighter")
                    answer.set_result(Decision("A"))
                    await next_success()
                    lines.put_nowait("/new\n")
                    lines.put_nowait("fresh\n")
                    third, answer = await model.next()
                    self.assertNotEqual(third["conversation_id"], first["conversation_id"])
                    self.assertEqual(len(third["context"]["messages"]), 1)
                    answer.set_result(Decision("fresh answer"))
                    await next_success()
                    lines.put_nowait("/quit\n")
                    await asyncio.wait_for(task, 1)
                    # Closing the view must not close an application-owned Agent.
                    receipt = await agent.submit("after terminal exit")
                    _, answer = await model.next()
                    answer.set_result(Decision("still usable"))
                    result = await agent.wait(receipt.run_id, timeout=1)
                    self.assertEqual(result["output"], "still usable")
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

    async def test_live_cli_registers_user_tools_and_has_no_demo_tools(self):
        lines, events = asyncio.Queue(), asyncio.Queue()
        calls = []
        schemas = []

        class Model(ControlledModel):
            async def decide(self, snapshot, tools):
                schemas.append(tools)
                return await super().decide(snapshot, tools)

        model = Model()
        provider = types.ModuleType("test_user_tools")

        def make_tools():
            return [Tool("user_lookup", "user business tool", {"type": "object"},
                         lambda: calls.append("called") or {"stock": 7})]

        provider.make_tools = make_tools
        extra = Tool("another", "application provided", {"type": "object"}, lambda: 0)
        args = argparse.Namespace(live=True, provider="tencent", model="test", reasoning="high",
                                  demo=False, debug=False, tools=["test_user_tools:make_tools"],
                                  cwd=".", no_builtin_tools=False)

        async def read_lines():
            while True:
                yield await lines.get()

        with (patch.dict(sys.modules, {provider.__name__: provider}),
              patch.object(terminal, "read_lines", read_lines),
              patch.object(terminal, "load_settings"),
              patch.object(terminal, "ChatModel", return_value=model),
              patch.object(terminal, "show", side_effect=lambda event, **_: events.put_nowait(event)),
              patch("builtins.print")):
            task = asyncio.create_task(terminal.main(args, tools=[extra]))
            try:
                lines.put_nowait("stock?\n")
                _, answer = await model.next()
                self.assertEqual({s["function"]["name"] for s in schemas[0]},
                                 {"user_lookup", "another", "terminal", "read_file",
                                  "write_file", "edit_file", "search_files"})
                answer.set_result(Decision(calls=(Call("user_lookup"),)))
                view, answer = await model.next()
                self.assertEqual(view["inputs"][-1]["content"], {"stock": 7})
                answer.set_result(Decision("7"))
                async with asyncio.timeout(1):
                    while (await events.get()).type != "run.succeeded":
                        pass
                lines.put_nowait("/quit\n")
                await asyncio.wait_for(task, 1)
                self.assertEqual(calls, ["called"])
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


class CompositionTests(unittest.TestCase):
    def test_kernel_import_does_not_load_cli_or_demo_application(self):
        result = subprocess.run([sys.executable, "-c", "import sys; import aether; "
                                 "assert not any(n.startswith('aether_cli') "
                                 "for n in sys.modules); "
                                 "assert not hasattr(aether, 'CATALOG')"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_multiple_explicit_tool_factories_can_be_appended(self):
        provider = types.ModuleType("test_user_tools")
        first = Tool("first", "", {}, lambda: 1)
        second = Tool("second", "", {}, lambda: 2)
        provider.first = lambda: [first]
        provider.second = lambda: (second,)
        with patch.dict(sys.modules, {provider.__name__: provider}):
            self.assertEqual(terminal.load_tools(["test_user_tools:first", "test_user_tools:second"]),
                             [first, second])

    def test_invalid_tool_factories_and_duplicate_names_are_rejected(self):
        provider = types.ModuleType("test_user_tools")
        provider.invalid = lambda: ["not a Tool"]
        tool = Tool("same", "", {}, lambda: 0)
        provider.valid = lambda: [tool]
        with patch.dict(sys.modules, {provider.__name__: provider}):
            with self.assertRaisesRegex(ValueError, "MODULE:FACTORY"):
                terminal.load_tools(["test_user_tools"])
            with self.assertRaisesRegex(TypeError, "Tool"):
                terminal.load_tools(["test_user_tools:invalid"])
            with self.assertRaisesRegex(ValueError, "unique"):
                Agent(ControlledModel(), terminal.load_tools([
                    "test_user_tools:valid", "test_user_tools:valid"]))
