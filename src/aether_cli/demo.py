"""Scripted fixtures and scenario owned by the demo application."""

from __future__ import annotations

import asyncio

from aether import Call, Decision, Tool

CATALOG = [
    {"id": "ALPHA", "mass_g": 180, "runtime_h": 12},
    {"id": "BETA", "mass_g": 120, "runtime_h": 8},
    {"id": "GAMMA", "mass_g": 140, "runtime_h": 10},
]


class DemoModel:
    async def decide(self, snapshot, tools):
        await asyncio.sleep(.1)
        facts = [i for i in snapshot["inputs"] if i["source"] == "tool"]
        if not facts:
            if snapshot["pending"]:
                return Decision("正在等待设备资料；你可以继续补充条件。", wait=True)
            return Decision(calls=(Call("catalog"),))
        narrow = any("150" in str(i["content"]) for i in snapshot["inputs"]
                     if i["source"] == "user")
        return Decision("GAMMA" if narrow else "ALPHA")


def make_tools():
    async def catalog():
        await asyncio.sleep(2)
        return CATALOG

    return [Tool("catalog", "获取虚构设备资料：编号、重量克数、续航小时。",
                 {"type": "object", "properties": {}, "additionalProperties": False}, catalog)]


async def demonstrate(agent, observe):
    receipt = await agent.submit("查设备资料，选续航最长的设备，只回答编号。")
    watcher = asyncio.create_task(observe(receipt.run_id))
    try:
        await asyncio.sleep(.5)
        await agent.submit("新增条件：重量不超过150克。", run_id=receipt.run_id)
        result = await agent.wait(receipt.run_id, timeout=240)
        await watcher
        if result["state"] != "succeeded":
            raise SystemExit(1)
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
