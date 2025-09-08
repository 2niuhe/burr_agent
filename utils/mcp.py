import json
from typing import Any, Dict, Optional

import aiohttp
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import Tool

from logger import logger

from config import CONFIG

if not CONFIG.mcp_urls:
    logger.error("mcp_urls not set")


class StreamableMCPClient:
    def __init__(self, disabled_tool_names: list[str] = []):
        self.session: Optional[ClientSession] = None
        self.available_tools: list[Tool] = []
        self.disabled_tools: list[str] = disabled_tool_names
        self._session_context = None
        self._transport_context = None

    async def connect(self, server_url: str) -> bool:
        try:
            logger.info(f"Testing server availability at {server_url}")

            # Simple HTTP health check before attempting MCP connection
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                try:
                    async with session.get(server_url) as response:
                        logger.info(f"Server responded with status: {response.status}")
                        if response.status >= 500:
                            logger.warning(
                                f"Server returned error status {response.status}"
                            )
                            return False
                except aiohttp.ClientError as e:
                    logger.warning(f"Server health check failed: {e}")
                    return False

            print(f"Server is reachable, attempting MCP connection to {server_url}")
            self._transport_context = streamablehttp_client(url=server_url)
            transport = await self._transport_context.__aenter__()
            self._session_context = ClientSession(transport[0], transport[1])
            self.session = await self._session_context.__aenter__()
            await self.session.initialize()
            response = await self.session.list_tools()
            self.available_tools = response.tools
            tool_names = [tool.name for tool in self.available_tools]
            print(f"Connected successfully! Available tools: {tool_names}")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            await self.cleanup()
            return False

    def get_tools_for_llm(self) -> list[dict]:
        tools = []
        for tool in self.available_tools:
            if tool.name in self.disabled_tools:
                continue
            tool_dict = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema,
                },
            }
            tools.append(tool_dict)
        return tools

    async def call_tool(
        self, tool_name: str, parameters: Optional[str | Dict[str, Any]] = None
    ) -> str:
        if not self.session:
            return "Not connected to MCP server"

        if isinstance(parameters, str):
            try:
                parameters = json.loads(parameters)
            except json.JSONDecodeError:
                logger.warning(
                    f"Failed to parse tool arguments: {parameters}, using empty dictionary"
                )
                parameters = {}

        try:
            print(f"Calling tool: {tool_name}")
            print(f"Parameters: {parameters}")
            result = await self.session.call_tool(tool_name, parameters)
            if hasattr(result, "content"):
                content_str = ""
                for item in result.content:
                    if hasattr(item, "text"):
                        content_str += item.text + ", "
                content_str = content_str.rstrip(", ")
            else:
                content_str = str(result)
            output = content_str or "No output"
            logger.info(f"Tool result: {output}")
            return output
        except Exception as e:
            error_msg = f"Tool execution failed: {e}"
            logger.warning(error_msg)
            return error_msg

    async def cleanup(self):
        try:
            if self._session_context:
                await self._session_context.__aexit__(None, None, None)
                self._session_context = None
                self.session = None
            if self._transport_context:
                await self._transport_context.__aexit__(None, None, None)
                self._transport_context = None
            print("Cleanup completed successfully")
        except Exception as e:
            print(f"Error during cleanup: {e}")


async def connect_to_mcp(server_url: str = None) -> Optional[StreamableMCPClient]:
    if server_url is None and CONFIG.mcp_urls:
        server_url = CONFIG.mcp_urls[0]
    if not server_url:
        print("mcp_urls not set in config.yaml")
        return None
    client = StreamableMCPClient()
    try:
        if await client.connect(server_url):
            return client
        else:
            logger.warning("Failed to connect to MCP server")
            return None
    except Exception as e:
        print(f"Error connecting to MCP server: {e}")
        return None


async def call_mcp_tool(tool_name: str, parameters: Dict[str, Any]) -> str:
    client = await connect_to_mcp()
    if not client:
        return "Failed to connect to MCP server"
    try:
        result = await client.call_tool(tool_name, parameters)
        return result
    finally:
        await client.cleanup()
