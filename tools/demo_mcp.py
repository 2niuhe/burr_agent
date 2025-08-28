#!/usr/bin/env python3
"""
Calculator MCP服务器
使用FastMCP实现标准MCP协议
"""

import logging
from mcp.server.fastmcp import FastMCP

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("calculator-mcp-server")

# 初始化FastMCP服务器
mcp = FastMCP("Calculator MCP Server")


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers(两个数字相加)

    Parameters:
        a (float): First number to add
        b (float): Second number to add

    Returns:
        float: The sum of a and b.
    """
    try:
        result = a + b
        logger.info(f"Addition: {a} + {b} = {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to add numbers: {e}")
        raise RuntimeError(f"Failed to add numbers: {str(e)}")


def main_stdio():
    """STDIO传输模式入口点"""
    logger.info("启动Calculator MCP服务器 (STDIO传输模式)")
    mcp.run(transport="stdio")


def main_remote(host: str = "127.0.0.1", port: int = 8008, transport: str = "http"):
    """HTTP传输模式入口点"""
    import uvicorn

    logger.info(
        f"启动Calculator MCP服务器 ({transport.upper()}传输模式) - {host}:{port}"
    )
    if transport == "sse":
        app = mcp.sse_app()
    else:
        app = mcp.streamable_http_app()
    uvicorn.run(app, host=host, port=port)


def main_http_with_args():
    """带命令行参数解析的HTTP服务器启动器"""
    import argparse
    import sys

    # 如果从主脚本调用，需要过滤掉 --http 参数
    argv = sys.argv[1:]
    if argv and argv[0] == "--http":
        argv = argv[1:]

    parser = argparse.ArgumentParser(description="Calculator MCP服务器 - HTTP传输模式")
    parser.add_argument("--host", default="127.0.0.1", help="绑定的主机地址")
    parser.add_argument("--port", type=int, default=8008, help="绑定的端口号")

    args = parser.parse_args(argv)
    main_remote(args.host, args.port)


def main_sse_with_args():
    """带命令行参数解析的SSE服务器启动器"""
    import argparse
    import sys

    # 如果从主脚本调用，需要过滤掉 --sse 参数
    argv = sys.argv[1:]
    if argv and argv[0] == "--sse":
        argv = argv[1:]

    parser = argparse.ArgumentParser(description="Calculator MCP服务器 - SSE传输模式")
    parser.add_argument("--host", default="127.0.0.1", help="绑定的主机地址")
    parser.add_argument("--port", type=int, default=8008, help="绑定的端口号")

    args = parser.parse_args(argv)
    main_remote(args.host, args.port, transport="sse")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        # HTTP模式：python calculator.py --http [--host HOST] [--port PORT]
        main_http_with_args()
    elif len(sys.argv) > 1 and sys.argv[1] == "--sse":
        # SSE模式：python calculator.py --sse [--host HOST] [--port PORT]
        main_sse_with_args()
    else:
        # 默认使用STDIO模式
        main_stdio()
