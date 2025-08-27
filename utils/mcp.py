import asyncio
import traceback
from typing import Dict, Any, Optional, AsyncGenerator
import httpx
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from mcp.types import Tool, TextContent


class StreamableMCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.available_tools: list[Tool] = []
        self._session_context = None
        self._streams_context = None

    async def connect(self, server_url: str) -> bool:
        """
        Connect to an MCP server via HTTP streaming.
        """
        try:
            # Create HTTP streaming client
            self._streams_context = httpx_client(url=server_url)
            streams = await self._streams_context.__aenter__()

            # Create MCP session
            self._session_context = ClientSession(*streams)
            self.session = await self._session_context.__aenter__()

            # Initialize session
            await self.session.initialize()
            
            # Get tool list
            response = await self.session.list_tools()
            self.available_tools = response.tools

            return True
        except Exception as e:
            print(f'Connection failed: {e}')
            print(traceback.format_exc())
            await self.cleanup()
            return False

    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """
        Call a tool with parameters and return the result.
        """
        if not self.session:
            return "Not connected to MCP server"
        
        try:
            result = await self.session.call_tool(tool_name, parameters)

            if hasattr(result, 'content'):
                content_str = ""
                for item in result.content:
                    if hasattr(item, 'text'):
                        content_str += item.text + ", "
                content_str = content_str.rstrip(', ')
            else:
                content_str = str(result)
            
            return content_str or "No output"
        except Exception as e:
            error_msg = f"Tool execution failed: {e}"
            print(error_msg)
            print(traceback.format_exc())
            return error_msg

    async def call_tool_streaming(self, tool_name: str, parameters: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """
        Call a tool with parameters and stream the result.
        """
        if not self.session:
            yield "Not connected to MCP server"
            return
        
        try:
            result = await self.session.call_tool(tool_name, parameters)
            
            if hasattr(result, 'content'):
                for item in result.content:
                    if hasattr(item, 'text'):
                        yield item.text
            else:
                yield str(result)
        except Exception as e:
            error_msg = f"Tool execution failed: {e}"
            print(error_msg)
            print(traceback.format_exc())
            yield error_msg

    async def cleanup(self):
        """
        Clean up resources.
        """
        try:
            if self._session_context:
                await self._session_context.__aexit__(None, None, None)
                self._session_context = None
                self.session = None
            
            if self._streams_context:
                await self._streams_context.__aexit__(None, None, None)
                self._streams_context = None
        except Exception as e:
            print(f"Error during cleanup: {e}")
            print(traceback.format_exc())


def httpx_client(url: str):
    """
    Create an HTTP streaming client for MCP.
    This is a context manager that yields send and receive streams.
    """
    class HTTPXClientContextManager:
        def __init__(self, url: str):
            self.url = url
            self.client: Optional[httpx.AsyncClient] = None
            
        async def __aenter__(self):
            self.client = httpx.AsyncClient(timeout=None)
            
            # Create send stream (POST requests)
            async def send_stream():
                async def send_message(message: str):
                    response = await self.client.post(
                        self.url,
                        content=message,
                        headers={"Content-Type": "application/json"}
                    )
                    response.raise_for_status()
                return send_message
            
            # Create receive stream (Server-Sent Events)
            async def receive_stream():
                async with self.client.stream("GET", f"{self.url}/stream") as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            yield line[6:]  # Remove "data: " prefix
                            
            return (await send_stream(), receive_stream())
        
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            if self.client:
                await self.client.aclose()
    
    return HTTPXClientContextManager(url)