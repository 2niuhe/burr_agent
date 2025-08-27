import os
import dotenv
import asyncio
import json
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI

# 导入全局logger
from logger import logger
from utils.mcp import call_mcp_tool

dotenv.load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")

# 初始化异步客户端
client = AsyncOpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)





async def get_llm_response(messages: list, tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """
    调用DeepSeek API获取聊天响应，支持工具调用。

    :param messages: 对话历史列表，格式如 [{"role": "user", "content": "..."}]
    :param tools: 可选的工具列表
    :return: 模型生成的响应，可能包含工具调用
    """
    if not api_key:
        logger.error("DEEPSEEK_API_KEY 环境变量未设置")
        return {
            "type": "error",
            "content": "错误：DEEPSEEK_API_KEY 环境变量未设置。"
        }

    try:
        logger.info("开始调用DeepSeek API")
        
        # 准备API调用参数
        api_params = {
            "model": "deepseek-chat",
            "messages": messages,
            "stream": True
        }
        
        # 如果提供了工具定义，则添加到参数中
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = "auto"  # 自动选择工具
            
        response = await client.chat.completions.create(**api_params)

        full_response = ""
        tool_calls = []
        
        async for chunk in response:
            # 处理工具调用
            if chunk.choices[0].delta.tool_calls:
                for tool_call in chunk.choices[0].delta.tool_calls:
                    if len(tool_calls) <= tool_call.index:
                        tool_calls.append({
                            "id": tool_call.id,
                            "type": "function",
                            "function": {"name": "", "arguments": ""}
                        })
                    
                    if tool_call.function:
                        if tool_call.function.name:
                            tool_calls[tool_call.index]["function"]["name"] = tool_call.function.name
                        if tool_call.function.arguments:
                            tool_calls[tool_call.index]["function"]["arguments"] += tool_call.function.arguments
            # 处理普通文本响应
            elif chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                full_response += content
                # print(content, end="", flush=True)
                
        print()  # 在结尾添加换行
        logger.info("成功获取API响应")
        
        # 如果有工具调用，返回工具调用信息
        if tool_calls:
            return {
                "type": "tool_calls",
                "tool_calls": tool_calls
            }
        
        # 否则返回文本响应
        return {
            "type": "text",
            "content": full_response
        }
    except Exception as e:
        error_message = f"调用API时出错: {e}"
        logger.error(error_message)
        print(error_message)
        return {
            "type": "error",
            "content": error_message
        }



if __name__ == '__main__':
    # 这是一个示例，展示如何直接运行此模块
    async def test():
        example_messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "你好，请介绍一下自己。"},
        ]
        response = await get_llm_response(example_messages)
        print(f"响应类型: {response['type']}")
        if response['type'] == 'text':
            print(f"响应内容: {response['content']}")
        elif response['type'] == 'tool_calls':
            print("工具调用:")
            for tool_call in response['tool_calls']:
                print(f"  - {tool_call['function']['name']}")

    asyncio.run(test())