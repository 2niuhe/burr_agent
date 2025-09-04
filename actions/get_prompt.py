from burr.core import action
from state import ApplicationState
from logger import logger


@action.pydantic(reads=["chat_history"], writes=["user_input", "exit_chat"])
def prompt(state: ApplicationState, user_input: str) -> ApplicationState:
    """Get input from the user and handle internal commands."""
    logger.info(f"User input: {user_input}")
    if user_input.lower() in ["exit", "quit"]:
        state.exit_chat = True
        return state

    state.user_input = user_input
    
    return state