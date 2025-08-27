import asyncio
import os

from burr.core import ApplicationBuilder, State, action
from utils import llm

# 2. 定义Actions
# Actions现在直接与State对象交互，该对象表现得像一个字典。
@action(reads=["user_input", "chat_history"], writes=["chat_history"])
async def response(state: State) -> tuple[dict, State]:
    """调用LLM并获取响应，然后更新对话历史。"""
    # 检查API密钥
    if not os.getenv("DEEPSEEK_API_KEY"):
        error_msg = "错误：DEEPSEEK_API_KEY 环境变量未设置。请设置您的API密钥。"
        result = {"answer": error_msg}
        return result, state
    
    # 将用户的最新消息添加到历史记录中
    updated_chat_history = state["chat_history"] + [{"role": "user", "content": state["user_input"]}]
    # 调用LLM获取响应
    answer = await llm.get_llm_response(updated_chat_history)
    # 将模型的响应也添加到历史记录中
    updated_chat_history = updated_chat_history + [{"role": "assistant", "content": answer}]
    # 返回结果和更新后的状态
    result = {"answer": answer}
    return result, state.update(chat_history=updated_chat_history)

@action(reads=[], writes=["user_input"])
def prompt(state: State, user_input: str) -> tuple[dict, State]:
    """从用户处获取输入。"""
    return {"user_input": user_input}, state.update(user_input=user_input)


def main():
    """主函数，用于构建和运行Burr应用。"""
    # 检查API密钥
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("警告：DEEPSEEK_API_KEY 环境变量未设置。")
        print("请设置您的DeepSeek API密钥: export DEEPSEEK_API_KEY='your_api_key'")
        return
    
    # 3. 构建应用
    app = (
        ApplicationBuilder()
        # 直接用字典初始化状态，定义初始结构
        .with_state(chat_history=[], user_input="")
        .with_actions(
            prompt=prompt,
            response=response,
        )
        .with_transitions(
            ("prompt", "response"),
            ("response", "prompt"),  # 循环回到prompt，等待下一次输入
        )
        .with_entrypoint("prompt")
        .build()
    )

    # 4. 运行应用
    print("欢迎来到Burr驱动的异步聊天机器人！")
    print("输入 'exit' 或 'quit' 来结束对话。")
    
    while True:
        try:
            user_message = input("你: ")
            if user_message.lower() in ["exit", "quit"]:
                print("再见!")
                break
            
            # 直接运行应用的异步方法
            # 我们传入用户输入作为prompt action的参数
            result = asyncio.run(app.arun(halt_after=["response"], inputs={"user_input": user_message}))
            # result 是一个三元组: (action, result_dict, final_state)
            print(f"AI: {result[1]['answer']}")

        except KeyboardInterrupt:
            print("\n再见!")
            break
        except Exception as e:
            print(f"\n发生错误: {e}")
            print("程序将继续运行，或者输入 'exit' 或 'quit' 来结束对话。")

if __name__ == "__main__":
    main()