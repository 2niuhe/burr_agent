from burr.core import ApplicationBuilder, when
from burr.integrations.pydantic import PydanticTypingSystem

from .state import ApplicationState
from .actions import (
    prompt,
    router,
    chat_response,
    vibe_planner,
    vibe_step_executor,
    human_confirm,
    execute_tools,
    vibe_result_analyzer,
    step_summarizer,
    exit_chat,
)


def build_application():
    return (
        ApplicationBuilder()
        .with_typing(PydanticTypingSystem(ApplicationState))
        .with_state(ApplicationState())
        .with_actions(
            prompt=prompt,
            router=router,
            chat_response=chat_response,
            vibe_planner=vibe_planner,
            vibe_step_executor=vibe_step_executor,
            human_confirm=human_confirm,
            execute_tools=execute_tools,
            vibe_result_analyzer=vibe_result_analyzer,
            step_summarizer=step_summarizer,
            exit_chat=exit_chat,
        )
        .with_transitions(
            ("prompt", "router"),
            ("prompt", "exit_chat", when(exit_chat=True)),

            # chat path
            ("router", "chat_response", when(route_target="chat_response")),
            ("chat_response", "human_confirm", when(tool_execution_needed=True)),
            ("chat_response", "prompt", when(tool_execution_needed=False)),
            ("human_confirm", "execute_tools", when(tool_execution_allowed=True)),
            ("human_confirm", "prompt", when(tool_execution_allowed=False)),

            # vibe path
            ("router", "vibe_planner", when(route_target="vibe_planner")),
            ("vibe_planner", "vibe_step_executor"),
            ("vibe_step_executor", "human_confirm", when(tool_execution_needed=True)),
            ("vibe_step_executor", "vibe_result_analyzer", when(tool_execution_needed=False)),
            ("human_confirm", "execute_tools", when(tool_execution_allowed=True)),
            ("human_confirm", "vibe_result_analyzer", when(tool_execution_allowed=False)),
            ("execute_tools", "vibe_result_analyzer"),
            ("vibe_result_analyzer", "step_summarizer"),
            ("step_summarizer", "prompt", when(active_step_id=None)),
            ("step_summarizer", "vibe_step_executor"),
        )
        .with_entrypoint("prompt")
        .with_tracker("local", project="burr_agent")
        .build()
    )


