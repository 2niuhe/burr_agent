import asyncio
from typing import Dict, Awaitable, Any

async def run_concurrrently(tasks: Dict[str, Awaitable], return_exceptions: bool = True) -> Dict[str, Any]:
    """Run a dictionary of tasks concurrently and return the results."""
    keys = list(tasks.keys())
    coroutines = [tasks[key] for key in keys]
    results = await asyncio.gather(*coroutines, return_exceptions=return_exceptions)
    return {k: r for k, r in zip(keys, results)}
