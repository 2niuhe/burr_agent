import asyncio

from burr.core import ApplicationBuilder, GraphBuilder, when

from actions import ask_llm, get_user_input
from schema import Role

# NOTE: with this graph, you can not use tools

system_prompt = """You are a helpful assistant.
"""


def graph():
    return (
        GraphBuilder()
        .with_actions(
            get_init_input=get_user_input.bind(system_prompt=system_prompt),
            get_fellow_input=get_user_input,
            ask_llm=ask_llm,
        )
        .with_transitions(
            ("get_init_input", "ask_llm", when(exit_chat=False)),
            ("get_fellow_input", "ask_llm", when(exit_chat=False)),
            ("ask_llm", "get_fellow_input", when(exit_chat=False)),
        )
        .build()
    )


def application():
    return (
        ApplicationBuilder()
        .with_graph(graph())
        .with_entrypoint("get_init_input")
        .with_tracker("local", project="burr_agent")
        .build()
    )


async def chat():
    app = application()

    current_role = Role.USER
    while True:
        prompt = input(f"{current_role.value}: ")

        if prompt.lower() in ["exit", "quit"]:
            break

        action, result_container = await app.astream_result(
            halt_after=["ask_llm"], inputs={"user_input": prompt}
        )

        print("AI: ", end="", flush=True)
        async for result in result_container:
            print(result["content"], end="", flush=True)

        print()


if __name__ == "__main__":
    asyncio.run(chat())
