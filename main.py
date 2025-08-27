import asyncio
import os

from burr.core import ApplicationBuilder, State, action
from utils import llm

# 导入全局logger
from logger import logger

# 2. 定义Actions
# Actions现在直接与State对象交互，该对象表现得像一个字典。
@action(reads=["user_input", "chat_history"], writes=["chat_history"])
async def response(state: State) -> tuple[dict, State]:
    """调用LLM并获取响应，然后更新对话历史。"""
    # 检查API密钥
    if not os.getenv("DEEPSEEK_API_KEY"):
        error_msg = "错误：DEEPSEEK_API_KEY 环境变量未设置。请设置您的API密钥。"
        result = {"answer": error_msg}
        # 注意：这里不再直接修改 chat_history，而是通过 update 方法返回新状态
        return result, state.update(chat_history=state["chat_history"])
    
    # 将用户的最新消息添加到历史记录中
    # 使用 state.append 方法将新消息追加到聊天历史列表中
    new_user_message = {"role": "user", "content": state["user_input"]}
    state_with_user_message = state.append(chat_history=new_user_message)
    
    # 调用LLM获取响应（传入更新后的聊天历史）
    answer = await llm.get_llm_response(state_with_user_message["chat_history"])
    
    # 将模型的响应也添加到历史记录中
    new_assistant_message = {"role": "assistant", "content": answer}
    # 使用 state.append 方法将AI的回复追加到聊天历史列表中
    final_state = state_with_user_message.append(chat_history=new_assistant_message)
    
    # 返回结果和更新后的状态
    result = {"answer": answer}
    return result, final_state

@action(reads=[], writes=["user_input"])
def prompt(state: State, user_input: str) -> tuple[dict, State]:
    """从用户处获取输入。"""
    return {"user_input": user_input}, state.update(user_input=user_input)


def main():
    """主函数，用于构建和运行Burr应用。"""

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
    logger.info("欢迎来到Burr驱动的异步聊天机器人！")
    logger.info("输入 'exit' 或 'quit' 来结束对话。")
    
    while True:
        try:
            user_message = input("你: ")
            if user_message.lower() in ["exit", "quit"]:
                logger.info("用户选择退出对话")
                print("再见!")
                break
            
            # 直接运行应用的异步方法
            # 我们传入用户输入作为prompt action的参数
            result = asyncio.run(app.arun(halt_after=["response"], inputs={"user_input": user_message}))
            # result 是一个三元组: (action, result_dict, final_state)
            print(f"AI: {result[1]['answer']}")

        except KeyboardInterrupt:
            logger.info("用户通过键盘中断退出对话")
            print("\n再见!")
            break
        except Exception as e:
            logger.error(f"运行应用时发生错误: {e}")
            print(f"\n发生错误: {e}")
            print("程序将继续运行，或者输入 'exit' 或 'quit' 来结束对话。")

if __name__ == "__main__":
    main()