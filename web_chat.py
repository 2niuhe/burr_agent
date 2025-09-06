#!/usr/bin/env python3
import asyncio
from typing import Dict, Any, List
from burr.core import GraphBuilder, ApplicationBuilder
from burr.core import when, expr
from actions import get_user_input, exit_chat, human_confirm, execute_tools, ask_llm
from utils.schema import Role, Message, HumanConfirmResult
from utils.mcp import connect_to_mcp, StreamableMCPClient
from nicegui import ui, app
import html
import json

# Global MCP client and tools
mcp_client: StreamableMCPClient = None
mcp_tools: list = []
tool_names = []

async def init_mcp_tools():
    global mcp_client, mcp_tools, tool_names
    try:
        mcp_client = await connect_to_mcp()
        if mcp_client:
            mcp_tools = mcp_client.get_tools_for_llm()
            tool_names = [tool["function"]["name"] for tool in mcp_tools]
            print(f"Initialized MCP tools: {tool_names}")
        return True
    except Exception as e:
        print(f"Failed to connect to MCP server: {e}")
        return False

def get_system_prompt():
    """Get system prompt with current tool names"""
    return f"""You are a helpful assistant. You can use the following tools: {tool_names}. Please use these tools to help the user when needed.
"""

class ChatInterface:
    def __init__(self):
        self.burr_app = None
        self.message_container = None
        self.text_input = None
        self.current_response_message = None
        self.send_button = None
        self.current_spinner = None
        self.chat_history: List[Dict[str, str]] = []
        self.pending_tool_confirmation = None
        self.current_pending_tools = []
        self.init_burr_application()
    
    def init_burr_application(self):
        """Initialize the Burr application with tool support"""
        system_prompt = get_system_prompt()
        
        graph = GraphBuilder().with_actions(
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
        
        self.burr_app = ApplicationBuilder().with_graph(
            graph).with_entrypoint("get_init_input").with_tracker("local", project="burr_agent_web").build()
    
    def clear_chat(self):
        """Clear chat history and reset the application"""
        self.chat_history.clear()
        self.message_container.clear()
        self.init_burr_application()
        ui.notify("Chat history cleared", type='info')
    
    def create_user_message(self, content: str):
        """Create a user message bubble with proper styling"""
        with ui.row().classes('w-full justify-end mb-3'):
            with ui.card().classes('user-message'):
                with ui.card_section().classes('py-2 px-3'):
                    ui.markdown(content).classes('text-white')
    
    def create_assistant_message(self, content: str = ""):
        """Create an assistant message bubble that can be updated"""
        with ui.row().classes('w-full justify-start mb-3'):
            card = ui.card().classes('assistant-message')
            with card:
                section = ui.card_section().classes('py-2 px-3')
                with section:
                    if content:
                        message_element = ui.markdown(content)
                    else:
                        message_element = ui.markdown("_Typing..._")
        return message_element
    
    def create_tool_confirmation_ui(self, pending_tools: List[Dict]):
        """Create UI for tool execution confirmation"""
        with ui.row().classes('w-full justify-center mb-3'):
            with ui.card().classes('tool-confirmation-card'):
                with ui.card_section().classes('py-3 px-4'):
                    ui.label('🔧 Tool Execution Request').classes('text-h6 mb-2')
                    ui.label(f'The assistant wants to execute {len(pending_tools)} tool(s):').classes('mb-3')
                    
                    # Display tool details
                    for i, tool_call in enumerate(pending_tools, 1):
                        with ui.expansion(f"{i}. {tool_call['name']}", icon='build').classes('w-full mb-2'):
                            ui.code(json.dumps(tool_call['arguments'], indent=2, ensure_ascii=False)).classes('text-xs')
                    
                    # Confirmation buttons
                    with ui.row().classes('w-full justify-center gap-4 mt-4'):
                        async def handle_allow():
                            await self.handle_tool_confirmation(True)
                        
                        async def handle_deny():
                            await self.handle_tool_confirmation(False)
                        
                        allow_btn = ui.button('✅ Allow', color='positive', on_click=handle_allow)
                        deny_btn = ui.button('❌ Deny', color='negative', on_click=handle_deny)
                    
                    return allow_btn, deny_btn
    
    
    async def handle_tool_confirmation(self, allowed: bool):
        """Handle user's tool execution confirmation"""
        print(f"Tool confirmation: {'allowed' if allowed else 'denied'}")  # Debug log
        
        # Remove the confirmation UI first
        if self.pending_tool_confirmation:
            try:
                self.pending_tool_confirmation.delete()
            except:
                pass  # Ignore if already deleted
            self.pending_tool_confirmation = None
        
        # Create new response message for tool execution results
        with self.message_container:
            self.current_response_message = self.create_assistant_message()
            
            # Add spinner for tool execution
            with ui.row().classes('w-full justify-center'):
                self.current_spinner = ui.spinner(type='dots', size='sm').classes('text-primary')
        
        # Continue with Burr application
        try:
            user_input = 'y' if allowed else 'n'
            action, result_container = await self.burr_app.astream_result(
                halt_after=["execute_tools", "get_fellow_input"], 
                halt_before=[],
                inputs={"user_input": user_input}
            )
            
            response_text = ""
            
            # Stream the response
            async for result in result_container:
                content = result.get("content", "")
                if content:
                    response_text += content
                    # Update the markdown content
                    if self.current_response_message:
                        self.current_response_message.content = response_text
                    
                    # Skip auto scroll during tool execution to avoid context issues
                    pass
            
            # Ensure we have content to display
            if not response_text:
                if not allowed:
                    response_text = "❌ Tool execution was denied by user. I cannot proceed with the requested operation."
                else:
                    response_text = "⚠️ No response received from the system."
                
                # Update the UI message
                if self.current_response_message:
                    self.current_response_message.content = response_text
            
            # Add assistant response to chat history
            if response_text:
                self.chat_history.append({"role": "assistant", "content": response_text})
            
        except Exception as e:
            error_message = f"❌ Error: {str(e)}"
            if self.current_response_message:
                self.current_response_message.content = error_message
            try:
                ui.notify(f"Error occurred: {str(e)}", type='negative')
            except:
                print(f"Error occurred: {str(e)}")  # Fallback to console
            # Add error to chat history
            self.chat_history.append({"role": "assistant", "content": error_message})
        
        finally:
            # Remove spinner and re-enable send button
            if self.current_spinner:
                try:
                    self.current_spinner.delete()
                except:
                    pass  # Ignore if already deleted
                self.current_spinner = None
            
            # Ensure message is not stuck in "Typing..." state
            if self.current_response_message and self.current_response_message.content == "_Typing..._":
                self.current_response_message.content = "❌ Operation completed."
            
            if self.send_button:
                try:
                    self.send_button.props(remove='disable')
                except:
                    pass  # Ignore if send button is not available
    
    async def send_message(self) -> None:
        """Send a message and handle the streaming response"""
        if not self.text_input.value.strip():
            return
            
        question = self.text_input.value.strip()
        self.text_input.value = ''
        
        # Disable send button during processing
        if self.send_button:
            self.send_button.props('disable')
        
        # Add user message to chat history
        self.chat_history.append({"role": "user", "content": question})
        
        # Add user message to UI with custom styling
        with self.message_container:
            self.create_user_message(question)
            
            # Add assistant message placeholder
            self.current_response_message = self.create_assistant_message()
            
            # Add spinner
            with ui.row().classes('w-full justify-center'):
                self.current_spinner = ui.spinner(type='dots', size='sm').classes('text-primary')
        
        try:
            # Get the action and result container from Burr
            action, result_container = await self.burr_app.astream_result(
                halt_after=["ask_llm_with_tool"], 
                inputs={"user_input": question}
            )
            
            response_text = ""
            detected_tool_calls = []
            
            # Stream the response
            async for result in result_container:
                # Handle different types of result objects
                if hasattr(result, 'get'):
                    content = result.get("content", "")
                elif hasattr(result, 'content'):
                    content = result.content
                else:
                    content = ""
                
                if content:
                    response_text += content
                    # Update the markdown content
                    self.current_response_message.content = response_text
                    
                    # Auto scroll to bottom
                    ui.run_javascript('window.scrollTo(0, document.body.scrollHeight)')
                
                # Check if tool calls are detected in the stream message
                if hasattr(result, 'tool_calls') and result.tool_calls:
                    try:
                        # Ensure tool_calls is iterable and contains valid objects
                        if isinstance(result.tool_calls, list):
                            detected_tool_calls.extend(result.tool_calls)
                            print(f"Tool calls detected in stream: {len(result.tool_calls)} tools")  # Debug log
                        else:
                            print(f"Tool calls is not a list: {type(result.tool_calls)}")  # Debug log
                    except Exception as e:
                        print(f"Error processing tool calls: {e}")  # Debug log
            
            # Check if we need to handle tool confirmation
            next_action = self.burr_app.get_next_action()
            print(f"Next action: {next_action.name if next_action else 'None'}")  # Debug log
            print(f"Detected tool calls in stream: {len(detected_tool_calls)} tools")  # Debug log
            
            if (next_action and next_action.name == "human_confirm") or detected_tool_calls:
                pending_tools = []
                
                # First, try to use tool calls from the stream
                if detected_tool_calls:
                    print(f"Using tool calls from stream: {len(detected_tool_calls)} tools")  # Debug log
                    for tool_call in detected_tool_calls:
                        try:
                            # Extract tool information from ToolCall object
                            arguments = tool_call.function.arguments
                            if isinstance(arguments, str):
                                arguments = json.loads(arguments)
                            
                            pending_tools.append({
                                'name': tool_call.function.name,
                                'arguments': arguments
                            })
                            print(f"Added tool from stream: {tool_call.function.name} with args: {arguments}")  # Debug log
                        except Exception as e:
                            print(f"Error processing tool call from stream: {e}")  # Debug log
                
                # If no tools from stream, try application state as fallback
                if not pending_tools:
                    app_state = self.burr_app.state
                    print(f"App state has pending_tool_calls: {hasattr(app_state, 'pending_tool_calls')}")  # Debug log
                    if hasattr(app_state, 'pending_tool_calls') and app_state.pending_tool_calls:
                        print(f"Pending tool calls from state: {len(app_state.pending_tool_calls)}")  # Debug log
                        for tool_call in app_state.pending_tool_calls:
                            try:
                                arguments = tool_call.function.arguments
                                if isinstance(arguments, str):
                                    arguments = json.loads(arguments)
                                
                                pending_tools.append({
                                    'name': tool_call.function.name,
                                    'arguments': arguments
                                })
                            except Exception as e:
                                print(f"Error processing tool call from state: {e}")  # Debug log
                
                if pending_tools:
                    print(f"Creating tool confirmation UI for {len(pending_tools)} tools")  # Debug log
                    try:
                        # Create tool confirmation UI
                        with self.message_container:
                            self.pending_tool_confirmation = ui.column().classes('w-full')
                            with self.pending_tool_confirmation:
                                self.create_tool_confirmation_ui(pending_tools)
                        
                        # Remove spinner when showing confirmation UI
                        if self.current_spinner:
                            self.current_spinner.delete()
                            self.current_spinner = None
                        
                        print("Tool confirmation UI created successfully")  # Debug log
                        # Don't continue processing - wait for user confirmation
                        return
                    except Exception as e:
                        print(f"Error creating tool confirmation UI: {e}")  # Debug log
                else:
                    print("No pending tools found")  # Debug log
            
            # Add assistant response to chat history
            if response_text:
                self.chat_history.append({"role": "assistant", "content": response_text})
            
        except Exception as e:
            # Handle errors
            error_message = f"❌ Error: {str(e)}"
            self.current_response_message.content = error_message
            
            # Add error to chat history
            self.chat_history.append({"role": "assistant", "content": error_message})
            ui.notify(f"Error occurred: {str(e)}", type='negative')
            
        finally:
            # Remove spinner and re-enable send button
            if self.current_spinner:
                self.current_spinner.delete()
                self.current_spinner = None
            if self.send_button:
                self.send_button.props(remove='disable')
    
    def export_chat_history(self):
        """Export chat history as text"""
        if not self.chat_history:
            ui.notify("No chat history to export", type='warning')
            return
        
        history_text = "# Chat History\n\n"
        for message in self.chat_history:
            role = message["role"].title()
            content = message["content"]
            history_text += f"**{role}:** {content}\n\n"
        
        # Create a downloadable file
        ui.download(history_text.encode(), filename="chat_history.md")
        ui.notify("Chat history exported", type='positive')
    
    def create_ui(self):
        """Create the NiceGUI interface"""
        ui.add_css(r'''
            a:link, a:visited {color: inherit !important; text-decoration: none; font-weight: 500}
            .chat-container {
                max-height: 75vh; 
                overflow-y: auto;
                padding: 1rem 2rem;
                background: #f8f9fa;
            }
            .message-input {background: white; border-radius: 20px;}
            .user-message {
                background: #1976d2 !important;
                color: white !important;
                margin-left: 15%;
                max-width: 70% !important;
                border-radius: 18px 18px 4px 18px !important;
            }
            .assistant-message {
                background: white !important;
                border: 1px solid #e0e0e0 !important;
                margin-right: 15%;
                max-width: 70% !important;
                border-radius: 18px 18px 18px 4px !important;
            }
            .q-card {
                box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
            }
            .chat-layout {
                max-width: 100% !important;
                width: 100% !important;
                margin: 0 !important;
                padding: 0 1rem !important;
            }
            .history-container {
                max-height: 75vh;
                overflow-y: auto;
                padding: 1rem;
            }
            .tool-confirmation-card {
                background: #fff3cd !important;
                border: 2px solid #ffc107 !important;
                border-radius: 12px !important;
                box-shadow: 0 4px 12px rgba(255, 193, 7, 0.3) !important;
                max-width: 80% !important;
            }
            .tool-confirmation-card .q-card__section {
                border-radius: 12px !important;
            }
        ''')
        
        # Layout setup for full height
        ui.query('.q-page').classes('flex')
        ui.query('.nicegui-content').classes('w-full')
        
        # Header
        with ui.header().classes('bg-primary text-white shadow-2'):
            with ui.row().classes('w-full items-center justify-between px-4'):
                ui.label('Burr Agent Web Chat').classes('text-h6')
                with ui.row():
                    ui.button('Clear Chat', icon='clear', on_click=self.clear_chat) \
                        .props('flat color=white')
                    ui.button('Export', icon='download', on_click=self.export_chat_history) \
                        .props('flat color=white')
        
        with ui.tabs().classes('w-full') as tabs:
            chat_tab = ui.tab('Chat')
            history_tab = ui.tab('History')
        
        with ui.tab_panels(tabs, value=chat_tab).classes('w-full chat-layout flex-grow items-stretch'):
            # Chat panel - 主要聊天区域
            self.message_container = ui.tab_panel(chat_tab).classes('items-stretch chat-container')
            
            # History panel - 聊天历史
            with ui.tab_panel(history_tab).classes('history-container'):
                ui.label('Chat History').classes('text-h6 mb-4')
                
                def refresh_history():
                    history_display.clear()
                    if not self.chat_history:
                        with history_display:
                            ui.label('No chat history yet.').classes('text-grey-6 text-center')
                    else:
                        with history_display:
                            for i, message in enumerate(self.chat_history):
                                role = message["role"]
                                content = message["content"]
                                
                                if role == 'user':
                                    with ui.row().classes('w-full justify-end mb-3'):
                                        with ui.card().classes('user-message'):
                                            with ui.card_section().classes('py-2 px-3'):
                                                ui.markdown(content).classes('text-white')
                                else:
                                    with ui.row().classes('w-full justify-start mb-3'):
                                        with ui.card().classes('assistant-message'):
                                            with ui.card_section().classes('py-2 px-3'):
                                                ui.markdown(content)
                
                history_display = ui.column().classes('w-full')
                refresh_history()
                
                ui.button('Refresh', icon='refresh', on_click=refresh_history) \
                    .props('color=primary') \
                    .classes('mt-4')
        
        # Footer with input - 全宽度布局
        with ui.footer().classes('bg-white border-t'), ui.column().classes('w-full my-4 px-4'):
            with ui.row().classes('w-full no-wrap items-center gap-2 max-w-6xl mx-auto'):
                self.text_input = ui.input(placeholder='Type your message here...') \
                    .props('rounded outlined dense') \
                    .classes('flex-grow message-input') \
                    .on('keydown.enter', self.send_message)
                
                self.send_button = ui.button('Send', icon='send', on_click=self.send_message) \
                    .props('color=primary rounded')
            
            ui.markdown('Built with [Burr](https://github.com/DAGWorks-Inc/burr) and [NiceGUI](https://nicegui.io)') \
                .classes('text-xs self-center mt-2 text-grey-6')


@ui.page('/')
async def main():
    """Main page setup"""
    # Initialize MCP tools first
    await init_mcp_tools()
    
    chat_interface = ChatInterface()
    # Re-initialize Burr application after MCP tools are loaded
    chat_interface.init_burr_application()
    chat_interface.create_ui()


if __name__ == "__main__":
    # Enable async support in NiceGUI
    ui.run(
        title='Burr Agent Web Chat with Tools',
        port=8080,
        host='0.0.0.0',
        show=True,
        reload=False
    )
