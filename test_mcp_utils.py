import asyncio
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from utils.mcp import call_mcp_tool


async def test_mcp_tool_call():
    """Test calling a simple MCP tool"""
    # This assumes you have an MCP server running at the URL specified in .env
    result = await call_mcp_tool("add", {"a": 5, "b": 3})
    print(f"Add tool result: {result}")


async def main():
    print("Testing MCP tool calls...")
    
    # Test regular tool call
    await test_mcp_tool_call()


if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    asyncio.run(main())
