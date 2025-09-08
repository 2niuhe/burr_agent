from burr.core import action
from schema import BasicState, Role, Message

from logger import logger
from utils.prompts import COMPRESS_MEMORY_PROMPT
from utils.llm import ask

@action.pydantic(reads=["chat_history"], writes=["chat_history"])
async def compress_memory(state: BasicState) -> BasicState:
    """Compress the memory."""
    logger.info("Compressing memory...")
    compressed_memory = await ask(state.chat_history.get_messages_except_system(), stream=False, system_msgs=[Message.system_message(content=COMPRESS_MEMORY_PROMPT)])
    state.chat_history.clear(except_roles=[Role.SYSTEM])
    compressed_msg = Message.user_message(content=compressed_memory)
    state.chat_history.append(compressed_msg)
    return state
