import asyncio
import traceback
import os
from typing import Dict, Any, Optional
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import Tool, TextContent


class StreamableMCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.available_tools: list[Tool] = []
        self._session_context = None
        self._transport_context = None

    async def connect(self, server_url: str) -> bool:
        """
        Connect to an MCP server via HTTP streaming.
        """
        try:
            print(f"Connecting to MCP server {server_url}")
            
            # Store the context managers but don't enter them yet
            self._transport_context = streamablehttp_client(url=server_url)
            transport = await self._transport_context.__aenter__()

            # Create MCP session
            self._session_context = ClientSession(transport[0], transport[1])
            self.session = await self._session_context.__aenter__()

            # Initialize session
            await self.session.initialize()
            
            # Get tool list
            response = await self.session.list_tools()
            self.available_tools = response.tools

            tool_names = [tool.name for tool in self.available_tools]
            print(f'Connected successfully! Available tools: {tool_names}')
            
            return True
        except Exception as e:
            print(f'Connection failed: {e}')
            print(traceback.format_exc())
            await self.cleanup()
            return False

    def get_tools_for_llm(self) -> list[dict]:
        """
        Convert available MCP tools to the format required by LLM APIs.
        
        Returns:
            List of tools in the format expected by LLM APIs.
        """
        tools = []
        for tool in self.available_tools:
            # 根据LLM API的要求格式化工具
            tool_dict = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema
                }
            }
            tools.append(tool_dict)
        
        return tools

    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """
        Call a tool with parameters and return the result.
        """
        if not self.session:
            return "Not connected to MCP server"
        
        try:
            print(f'Calling tool: {tool_name}')
            print(f'Parameters: {parameters}')

            result = await self.session.call_tool(tool_name, parameters)

            if hasattr(result, 'content'):
                content_str = ""
                for item in result.content:
                    if hasattr(item, 'text'):
                        content_str += item.text + ", "
                content_str = content_str.rstrip(', ')
            else:
                content_str = str(result)
            
            output = content_str or "No output"
            print(f"Tool result: {output}")
            return output
        except Exception as e:
            error_msg = f"Tool execution failed: {e}"
            print(error_msg)
            print(traceback.format_exc())
            return error_msg

    async def cleanup(self):
        """
        Clean up resources.
        """
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
            print(traceback.format_exc())


# Utility functions for connecting to MCP and calling tools
async def connect_to_mcp() -> Optional[StreamableMCPClient]:
    """
    Connect to MCP server using URL from environment variables.
    
    Expects MCP_SERVER_URL environment variable to be set.
    """
    server_url = os.getenv('MCP_SERVER_URL')
    if not server_url:
        print("MCP_SERVER_URL environment variable not set")
        return None
    
    client = StreamableMCPClient()
    if await client.connect(server_url):
        return client
    else:
        print("Failed to connect to MCP server")
        return None


async def call_mcp_tool(tool_name: str, parameters: Dict[str, Any]) -> str:
    """
    Connect to MCP server and call a tool with parameters.
    
    Expects MCP_SERVER_URL environment variable to be set.
    """
    client = await connect_to_mcp()
    if not client:
        return "Failed to connect to MCP server"
    
    try:
        result = await client.call_tool(tool_name, parameters)
        return result
    finally:
        await client.cleanup()