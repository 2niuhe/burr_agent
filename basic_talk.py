import asyncio
import json
import os
from typing import List, Dict, Any

from burr.core import ApplicationBuilder, State, action
from utils import llm
from utils.mcp import StreamableMCPClient, call_mcp_tool

# 导入全局logger
from logger import logger

@action(reads=[], writes=["user_input"])
def prompt(state: State, user_input: str) -> tuple[dict, State]:
    """从用户处获取输入。"""
    return {"user_input": user_input}, state.update(user_input=user_input)


@action(reads=["user_input", "chat_history"], writes=["chat_history"])
async def response(state: State) -> tuple[dict, State]:
    """调用LLM并获取响应，然后更新对话历史。"""
    # 将用户的最新消息添加到历史记录中
    # 使用 state.append 方法将新消息追加到聊天历史列表中
    new_user_message = {"role": "user", "content": state["user_input"]}
    state_with_user_message = state.append(chat_history=new_user_message)
    
    # 获取MCP工具列表（假设MCP服务器始终可用）
    tools = None
    mcp_client = StreamableMCPClient()
    try:
        connected = await mcp_client.connect(os.getenv("MCP_SERVER_URL"))
        if connected:
            tools = mcp_client.get_tools_for_llm()
    except Exception as e:
        logger.error(f"获取MCP工具列表时出错: {e}")
    finally:
        await mcp_client.cleanup()
    
    # 调用LLM获取响应（传入更新后的聊天历史和工具列表）
    # 支持工具调用
    llm_response = await llm.get_llm_response(state_with_user_message["chat_history"], tools)
    
    # 处理工具调用
    if llm_response["type"] == "tool_calls":
        # 处理工具调用并获取结果
        new_messages, updated_chat_history = await handle_tool_calls(state_with_user_message["chat_history"], llm_response)
        
        # 获取最终回复
        final_response = await llm.get_llm_response(updated_chat_history)
        answer = final_response.get("content", "抱歉，我没有理解您的问题。")
    else:
        answer = llm_response.get("content", "抱歉，我没有理解您的问题。")
    
    # 将模型的响应也添加到历史记录中
    new_assistant_message = {"role": "assistant", "content": answer}
    # 使用 state.append 方法将AI的回复追加到聊天历史列表中
    final_state = state_with_user_message.append(chat_history=new_assistant_message)
    
    # 返回结果和更新后的状态
    result = {"answer": answer}
    return result, final_state


async def handle_tool_calls(messages: list, response: dict) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    处理工具调用并生成响应消息。

    :param messages: 对话历史列表
    :param response: LLM返回的包含工具调用的响应
    :return: (新消息列表, 更新后的完整消息历史)
    """
    new_messages = []
    updated_messages = messages.copy()
    
    if response["type"] == "tool_calls":
        # 添加工具调用到消息历史
        tool_call_message = {
            "role": "assistant",
            "tool_calls": response["tool_calls"]
        }
        new_messages.append(tool_call_message)
        updated_messages.append(tool_call_message)
        
        # 执行工具调用
        for tool_call in response["tool_calls"]:
            function_name = tool_call["function"]["name"]
            try:
                # 解析工具参数
                function_args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError as e:
                error_message = f"解析工具参数时出错: {e}"
                logger.error(error_message)
                tool_result = error_message
            else:
                # 调用工具 - 直接使用utils/mcp.py中的函数
                tool_result = await call_mcp_tool(function_name, function_args)
            
            # 添加工具调用结果到消息历史
            tool_result_message = {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "name": function_name,
                "content": tool_result
            }
            new_messages.append(tool_result_message)
            updated_messages.append(tool_result_message)
    
    return new_messages, updated_messages


def application():
    """构建Burr应用。"""
    return (
        ApplicationBuilder()
        .with_state(chat_history=[], user_input="")
        .with_actions(
            prompt=prompt,
            response=response,
        )
        .with_transitions(
            ("prompt", "response"),
            ("response", "prompt"),
        )
        .with_entrypoint("prompt")
        .with_tracker("local", project="burr_agent")
        .build()
    )


async def chat():
    """运行聊天应用。"""
    app = application()
    
    logger.info("欢迎来到Burr驱动的异步聊天机器人！")
    logger.info("输入 'exit' 或 'quit' 来结束对话。")
    
    while True:
        user_message = input("你: ")
        if user_message.lower() in ["exit", "quit"]:
            print("再见!")
            break
            
        # 运行应用
        action, result, state = await app.arun(
            halt_after=["response"], 
            inputs={"user_input": user_message}
        )
        print(f"AI: {result['answer']}")


if __name__ == "__main__":
    asyncio.run(chat())