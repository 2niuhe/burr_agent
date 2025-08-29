#!/usr/bin/env python3
"""
Enhanced Calculator MCP服务器
使用FastMCP实现标准MCP协议，添加了文件操作和系统命令功能
"""

import logging
import subprocess
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("calculator-mcp-server")

# 初始化FastMCP服务器
mcp = FastMCP("Enhanced Calculator MCP Server")


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


@mcp.tool()
def execute_bash_command(command: str, timeout: int = 30) -> dict:
    """Execute a bash command and return the result(执行bash命令并返回结果)

    Parameters:
        command (str): The bash command to execute
        timeout (int): Command execution timeout in seconds (default: 30)

    Returns:
        dict: A dictionary containing stdout, stderr, and return code
    """
    try:
        logger.info(f"Executing command: {command}")
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd()
        )
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out: {command}")
        raise RuntimeError(f"Command execution timed out after {timeout} seconds")
    except Exception as e:
        logger.error(f"Failed to execute command: {e}")
        raise RuntimeError(f"Failed to execute command: {str(e)}")


@mcp.tool()
def read_file(file_path: str, encoding: str = "utf-8") -> str:
    """Read the content of a file(读取文件内容)

    Parameters:
        file_path (str): Path to the file to read
        encoding (str): File encoding (default: utf-8)

    Returns:
        str: The content of the file
    """
    try:
        logger.info(f"Reading file: {file_path}")
        with open(file_path, 'r', encoding=encoding) as file:
            content = file.read()
        return content
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise RuntimeError(f"File not found: {file_path}")
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        raise RuntimeError(f"Failed to read file: {str(e)}")


@mcp.tool()
def write_file(file_path: str, content: str, mode: str = "w", encoding: str = "utf-8") -> bool:
    """Write content to a file(写入内容到文件)

    Parameters:
        file_path (str): Path to the file to write
        content (str): Content to write to the file
        mode (str): Write mode ('w' for overwrite, 'a' for append) (default: 'w')
        encoding (str): File encoding (default: utf-8)

    Returns:
        bool: True if successful
    """
    try:
        logger.info(f"Writing to file: {file_path} with mode: {mode}")
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path) if os.path.dirname(file_path) else ".", exist_ok=True)
        
        with open(file_path, mode, encoding=encoding) as file:
            file.write(content)
        return True
    except Exception as e:
        logger.error(f"Failed to write file: {e}")
        raise RuntimeError(f"Failed to write file: {str(e)}")


@mcp.tool()
def list_directory(path: str = ".", include_hidden: bool = False) -> dict:
    """List contents of a directory(列出目录内容)

    Parameters:
        path (str): Path to the directory to list (default: current directory)
        include_hidden (bool): Whether to include hidden files (default: False)

    Returns:
        dict: A dictionary containing files and directories
    """
    try:
        logger.info(f"Listing directory: {path}")
        entries = os.listdir(path)
        
        if not include_hidden:
            entries = [entry for entry in entries if not entry.startswith('.')]
        
        files = []
        directories = []
        
        for entry in entries:
            full_path = os.path.join(path, entry)
            if os.path.isfile(full_path):
                files.append(entry)
            elif os.path.isdir(full_path):
                directories.append(entry)
        
        return {
            "files": sorted(files),
            "directories": sorted(directories)
        }
    except Exception as e:
        logger.error(f"Failed to list directory: {e}")
        raise RuntimeError(f"Failed to list directory: {str(e)}")


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
