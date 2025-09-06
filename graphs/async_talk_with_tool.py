import asyncio
from burr.core import GraphBuilder, ApplicationBuilder
from burr.core import when, expr
from actions import get_user_input, exit_chat, human_confirm, execute_tools, ask_llm

from utils.schema import Role, ActionStreamMessage, HumanConfirmResult
from utils.mcp import connect_to_mcp, StreamableMCPClient

# NOTE: with this graph, you can use tools

mcp_client: StreamableMCPClient = None
mcp_tools: list = []
tool_names = []

async def init_mcp_tools():
    global mcp_client, mcp_tools, tool_names
    try:
        mcp_client = await connect_to_mcp()
        mcp_tools = mcp_client.get_tools_for_llm()
        tool_names = [tool["function"]["name"] for tool in mcp_tools]
    except Exception as e:
        print(f"Failed to connect to MCP server: {e}")


system_prompt = """You are a helpful assistant. You can use the following tools: {tool_names}. Please use these tools to help the user when needed.
"""

def graph():
    return GraphBuilder().with_actions(
        get_init_input=get_user_input.bind(system_prompt=system_prompt),
        get_fellow_input=get_user_input,
        ask_llm_with_tool=ask_llm.bind(mcp_tools=mcp_tools),
        execute_tools=execute_tools.bind(mcp_client=mcp_client),
        human_confirm=human_confirm,
    ).with_transitions(
        ("get_init_input", "ask_llm_with_tool"),
        ("get_fellow_input", "ask_llm_with_tool"),
        ("ask_llm_with_tool", "human_confirm", ~when(pending_tool_calls=[])),
        ("human_confirm", "execute_tools", when(tool_execution_allowed=True)),
        ("human_confirm", "get_fellow_input", when(tool_execution_allowed=False)),
        ("execute_tools", "get_fellow_input"),
        ("ask_llm_with_tool", "get_fellow_input", when(pending_tool_calls=[])),
    ).build()


def application():
    return ApplicationBuilder().with_graph(
        graph()).with_entrypoint("get_init_input").with_tracker("local", project="burr_agent").build()


async def chat():

    try:
        await init_mcp_tools()
        app = application()
        
        while True:

            if app.get_next_action().name == "human_confirm":
                prompt = input(f"{Role.USER.value}: Allow tool execution? (y/n): ")
                _, result, _ = await app.astep(inputs={"user_input": prompt})
                result: HumanConfirmResult = result
                print(result)
                if not result.allowed:
                    print(f"{Role.ASSISTANT.value}: {result.content}")
 
                    # get next user input
                    prompt =input(f"{Role.USER.value}: ")
                    if prompt.lower() in ["exit", "quit"]:
                        break
            else:
                prompt = input(f"{Role.USER.value}: ")
                if prompt.lower() in ["exit", "quit"]:
                    break

            _, result_container = await app.astream_result(halt_after=["ask_llm_with_tool", "execute_tools"], inputs={"user_input": prompt})
            
            print(f"{Role.ASSISTANT.value}: ", end="", flush=True)
            async for result in result_container:
                print(result.content, end="", flush=True)

            print()
    except KeyboardInterrupt:
        print("\nGoodbye!")
    finally:
        if mcp_client:
            await mcp_client.cleanup()

if __name__ == "__main__":
    asyncio.run(chat())
