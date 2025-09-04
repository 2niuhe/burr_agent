import asyncio
from typing import List, Optional

from logger import logger
from utils.mcp import StreamableMCPClient, connect_to_mcp


class ToolsManager:
    """Singleton-like facade for MCP tool discovery and invocation."""

    _client: Optional[StreamableMCPClient] = None
    _tools_for_llm: List[dict] = []
    _init_lock = asyncio.Lock()

    @classmethod
    async def ensure_initialized(cls) -> None:
        if cls._client is not None:
            return
        async with cls._init_lock:
            if cls._client is not None:
                return
            client = await connect_to_mcp()
            if client is None:
                logger.warning("MCP client not available; tools will be empty")
                cls._client = None
                cls._tools_for_llm = []
                return
            cls._client = client
            try:
                cls._tools_for_llm = cls._client.get_tools_for_llm()
            except Exception as exc:
                logger.exception(f"Failed to fetch tools for LLM: {exc}")
                cls._tools_for_llm = []

    @classmethod
    def get_tools_for_llm(cls) -> List[dict]:
        return cls._tools_for_llm or []

    @classmethod
    def get_client(cls) -> Optional[StreamableMCPClient]:
        return cls._client

    @classmethod
    async def cleanup(cls) -> None:
        if cls._client is not None:
            try:
                await cls._client.cleanup()
            finally:
                cls._client = None
                cls._tools_for_llm = []


