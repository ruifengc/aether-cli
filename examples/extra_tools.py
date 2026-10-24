"""User-owned tools: --tools examples.extra_tools:make_tools (from the project root)."""

from aether import Tool


def make_tools():
    def multiply(left: int, right: int):
        return {"product": left * right}

    return [Tool("multiply", "计算两个整数的乘积。", {"type": "object", "properties": {
        "left": {"type": "integer"}, "right": {"type": "integer"}},
        "required": ["left", "right"], "additionalProperties": False}, multiply)]
