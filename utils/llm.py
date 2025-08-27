import os
import dotenv
import asyncio
from openai import AsyncOpenAI

dotenv.load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")

# 初始化异步客户端
client = AsyncOpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)

async def get_llm_response(messages: list) -> str:
    """
    调用DeepSeek API获取聊天响应。

    :param messages: 对话历史列表，格式如 [{"role": "user", "content": "..."}]
    :return: 模型生成的字符串响应
    """
    if not api_key:
        return "错误：DEEPSEEK_API_KEY 环境变量未设置。"

    try:
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            stream=True
        )

        full_response = ""
        print("AI: ", end="", flush=True)
        async for chunk in response:
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                full_response += content
                print(content, end="", flush=True)
        print()  # 在结尾添加换行
        return full_response
    except Exception as e:
        error_message = f"调用API时出错: {e}"
        print(error_message)
        return error_message

if __name__ == '__main__':
    # 这是一个示例，展示如何直接运行此模块
    async def test():
        example_messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "你好，请介绍一下自己。"},
        ]
        await get_llm_response(example_messages)

    asyncio.run(test())