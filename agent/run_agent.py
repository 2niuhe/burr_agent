import asyncio

from logger import logger
from .app import build_application
from .tools_manager import ToolsManager


async def run():
    await ToolsManager.ensure_initialized()
    app = build_application()

    logger.info("Welcome to the Burr V4-style agent!")
    logger.info("Commands: /mode [interactive|yolo], /workflow [chat|vibe|ops], /goal <text>")
    logger.info("Enter 'exit' or 'quit' to end.")

    try:
        while True:
            action, result_container = await app.astream_result(
                halt_after=[
                    "chat_response",
                    "vibe_step_executor",
                    "execute_tools",
                    "step_summarizer",
                ]
            )
            async for _ in result_container:
                pass
            # loop continues until user exits via prompt
    except KeyboardInterrupt:
        print("\nGoodbye!")
    finally:
        await ToolsManager.cleanup()


if __name__ == "__main__":
    asyncio.run(run())


