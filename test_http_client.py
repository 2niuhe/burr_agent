import asyncio
import json
import os
import sys
import traceback
from typing import Dict, Any
from unittest import result
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


TOOL_TESTS = {
    "add": {"a": 5, "b": 3},
    "subtract": {"a": 10, "b": 4},
    "multiply": {"a": 6, "b": 7},
    "divide": {"a": 20, "b": 5},
    "factorial": {"a": 5},
    "log": {"a": 100, "base": 10},
    "remainder": {"a": 17, "b": 5},
    "sin": {"angle": 30, "degrees": True},
    "cos": {"angle": 60, "degrees": True},
    "tan": {"angle": 45, "degrees": True},
    "power": {"base": 2, "exponent": 8},
    "sqrt": {"a": 16}
}


class MCPClient:
    def __init__(self):
        self.session = None
        self.available_tools = []

    async def connect(self, server_url: str):
        print(f"Connecting to server {server_url}")

        try:
            print("Create SSE Client...")
            # Store the context managers but don't enter them yet
            self._transport_context = streamablehttp_client(url=server_url)
            transport = await self._transport_context.__aenter__()

            print("Create MCP Session...")
            self._session_context = ClientSession(transport[0], transport[1])
            self.session = await self._session_context.__aenter__()

            print("Init Session...")
            await self.session.initialize()
            
            print("Get Tool List...")
            response = await self.session.list_tools()
            self.available_tools = response.tools

            tool_names = [tool.name for tool in self.available_tools]
            print(f'Connect Successfully! Available Tools: {tool_names}')

            for tool in self.available_tools:
                print(f'Tool: {tool.name}')
                print(f'Tool Description: {tool.description}')
                print(f'Input Schema: {json.dumps(tool.inputSchema, indent=4)}')
                if tool.outputSchema:
                    print(f'Output Schema: {json.dumps(tool.outputSchema, indent=4)}')
                else:
                    print('Output Schema: None')
                print()
            return True
        except Exception as e:
            # If an error occurs during connection, clean up any partially initialized resources
            print(f'Connect Failed: {e}')
            print(traceback.format_exc())
            
            # Clean up any resources that might have been created
            await self.cleanup()
            return False
        
    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        if not self.session:
            print('Error: Not Connect to MCP server')
            return "Not Connect to MCP server"
        
        try:
            print(f'Call Tool: {tool_name}')
            print(f'Params: {parameters}')

            result = await self.session.call_tool(tool_name, parameters)
            print(result)


            if hasattr(result, 'content'):
                content_str = ""
                for item in result.content:
                    if hasattr(item, 'text'):
                        content_str += item.text + ", "
                content_str = content_str.rstrip(', ')
            else:
                content_str = str(result)
            
            output = content_str or "No Output"
            print(f"Tool Execute Result: {output}")
            return output
        except Exception as e:
            error_msg = f"Tool Execute Failed: {e}"
            print(error_msg)
            print(traceback.format_exc())
            return error_msg
    
    async def test_tools(self):
        if not self.session or not self.available_tools:
            print("Error: Not Connect to MCP server or Not Get Tool List")
            return False
        
        print("\n ===== Start Test Tools =====\n")

        available_tool_names = {tool.name for tool in self.available_tools}

        results = []

        for tool_name, test_params in TOOL_TESTS.items():
            if tool_name in available_tool_names:
                print(f"\nTest Tool: {tool_name}")
                result = await self.call_tool(tool_name, test_params)
                success = "Success" if "Fail" not in result else "Failed"
                results.append({"tool": tool_name, "result": result, "status": success})
            else:
                print(f"Skip Test, Tool {tool_name} Not available")
        
        print("\n ===== Test Summary =====")
        for result in results:
            print(f"{result['tool']} {result['status']}: {result['result']}")
        all_success = all([r['status'] == "Success" for r in results])
        print(f"\nAll Test {'Success' if all_success else 'Failed'}")

        return all_success


    async def cleanup(self):
        try:
            if hasattr(self, '_session_context') and self._session_context:
                await self._session_context.__aexit__(None, None, None)
                self._session_context = None
                self.session = None
            
            if hasattr(self, '_transport_context') and self._transport_context:
                await self._transport_context.__aexit__(None, None, None)
                self._transport_context = None
            
            print("Cleanup completed successfully")
        except Exception as e:
            print(f"Error during cleanup: {e}")
            print(traceback.format_exc())


async def main():
    if len(sys.argv) < 2:
        print("Usage: python test_mcp_client.py <MCP Server URL> (Such as http://localhost:8008/mcp)")
        sys.exit(1)
    
    server_url = sys.argv[1]
    client = MCPClient()

    try:
        if await client.connect(server_url):
            print('Connect Success')

            # 默认执行测试工具，不需要额外参数
            await client.test_tools()
            print("\nTests completed, exiting...")
        else:
            print("Connect Failed")
            sys.exit(1)
    
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, shutting down...")
    except asyncio.CancelledError:
        print("\nTask cancelled, shutting down...")
    except Exception as e:
        print('Execute Failed')
        print(traceback.format_exc())
        sys.exit(1)
    finally:
        print("\nCleaning up resources...")
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())


        