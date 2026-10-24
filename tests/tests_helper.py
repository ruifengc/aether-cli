import asyncio


class ControlledModel:
    def __init__(self):
        self.requests = asyncio.Queue()

    async def decide(self, snapshot, tools):
        future = asyncio.get_running_loop().create_future()
        self.requests.put_nowait((snapshot, future))
        return await future

    async def next(self):
        return await asyncio.wait_for(self.requests.get(), 1)
