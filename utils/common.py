import asyncio
import json
from typing import Dict, Awaitable, Any, List

from .schema import ToolCall

async def run_concurrrently(tasks: Dict[str, Awaitable], return_exceptions: bool = True) -> Dict[str, Any]:
    """Run a dictionary of tasks concurrently and return the results."""
    keys = list(tasks.keys())
    coroutines = [tasks[key] for key in keys]
    results = await asyncio.gather(*coroutines, return_exceptions=return_exceptions)
    return {k: r for k, r in zip(keys, results)}


def get_tool_call_markdown(tool_calls: List[ToolCall]) -> str:
    tool_calls_list = []
    for tool_call in tool_calls:
        d = tool_call.function.to_dict()
        if isinstance(d.get("arguments"), str):
            d["arguments"] = json.loads(d["arguments"])
        tool_calls_list.append(d)
    return f"```json\n{json.dumps(tool_calls_list, indent=4, ensure_ascii=False)}\n```"
